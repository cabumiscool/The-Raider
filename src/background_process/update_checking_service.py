import typing
import asyncio
from background_process.base_service import BaseService
from background_process.background_objects import LibraryRetrievalError
from dependencies.database.database import Database
from dependencies.webnovel.web import library
from dependencies.webnovel.classes import QiAccount, SimpleBook, SimpleComic
from dependencies.proxy_classes import Proxy


async def retrieve_library_accounts(database: Database) -> typing.List[QiAccount]:
    tasks = []
    for library_type in range(1, 11):
        tasks.append(asyncio.create_task(database.retrieve_specific_library_type_number_account(library_type)))
    accounts = await asyncio.gather(*tasks)
    accounts: typing.List[QiAccount]
    return accounts


async def test_account(account: QiAccount):
    account_status = await account.async_check_valid()
    return account_status, account


async def retrieve_library_content(account: QiAccount, proxy: Proxy = None):
    library_items, pages_in_library = await library.retrieve_all_library_pages(account=account, proxy=proxy)
    return library_items, pages_in_library, account


class BooksLibraryChecker(BaseService):
    def __init__(self, database: Database):
        super().__init__('Library Checker Module')
        self.database = database

    async def main(self):
        # accounts = await retrieve_library_accounts(self.database)
        accounts = await self.database.retrieve_all_library_type_number_accounts(1)
        expected_accounts_count = len(accounts)
        working_accounts = []
        # working_accounts_number = []
        run_count = 0

        # this retrieves accounts and check if they are working before using them
        while True:
            account_tests = [asyncio.create_task(test_account(account)) for account in accounts]
            results = await asyncio.gather(*account_tests)
            accounts = []
            for check_result, account in results:
                if check_result:
                    working_accounts.append(account)
                    # working_accounts_number.append(account.library_type)
                else:
                    await self.database.expired_account(account)
                    accounts.append(await self.database.retrieve_specific_library_type_number_account(
                        account.library_type))
            if len(working_accounts) == expected_accounts_count:
                break
            run_count += 1
            if run_count >= 3:
                raise LibraryRetrievalError

        accounts_number_dict = {account.library_type: account for account in working_accounts}

        # retrieves the books and orders them in the expected accounts groups
        simple_books_list = await self.database.retrieve_all_simple_books()
        books_dict = {}
        for simple_book in simple_books_list:
            if simple_book.library_number in books_dict:
                books_dict[simple_book.library_number][simple_book.id] = simple_book
            else:
                books_dict[simple_book.library_number] = {simple_book.id: simple_book}

        # retrieves a proxy to be used for the library check

        # while True:
        #     proxy = await self.database.retrieve_proxy()
        #     working_proxy = await proxy.test()
        #     if working_proxy:
        #         break
        #     await self.database.expired_proxy(proxy.id)
        #     proxy = await self.database.retrieve_proxy()

        # will retrieve the library content and order them
        library_books = []
        tasks = [asyncio.create_task(retrieve_library_content(account)) for account in working_accounts]
        results = await asyncio.gather(*tasks)
        for library_items, all_library_pages_count, account in results:
            library_items: typing.List[typing.Union[SimpleBook, SimpleComic]]
            all_library_pages_count: int
            account: QiAccount
            library_books.append((account.library_type, library_items))
            if account.library_pages != all_library_pages_count:
                await self.database.set_library_pages_number(account, all_library_pages_count)

        # will compare the library books with the db books
        extra_books_in_library = {}
        missing_book_from_library = {}
        changed_books = []
        for library_type_number, account_library_content_list in library_books:
            db_library_books = books_dict.get(library_type_number, dict())
            for book in account_library_content_list:
                if book.id in db_library_books:
                    db_book = db_library_books[book.id]
                    if book != db_book:
                        changed_books.append(book)
                    del db_library_books[book.id]
                else:
                    if library_type_number in extra_books_in_library:
                        extra_books_in_library[library_type_number].append(book)
                    else:
                        extra_books_in_library[library_type_number] = [book]

            if len(db_library_books) != 0:
                for book_id, book_obj in db_library_books.items():
                    if library_type_number in missing_book_from_library:
                        missing_book_from_library[library_type_number].append(book_obj)
                    else:
                        missing_book_from_library[library_type_number] = [book_obj]

        # adding to output queue
        self._output_queue.extend(changed_books)

        # adds any missing book to the accounts libs
        if len(missing_book_from_library) != 0:
            tasks = []
            for library_type_number, missing_books in missing_book_from_library.items():
                account_obj: QiAccount = accounts_number_dict[library_type_number]
                for missing_book in missing_books:
                    tasks.append(asyncio.create_task(library.add_item_to_library(missing_book, account=account_obj)))
            await asyncio.gather(*tasks)

        # will remove unchecked items from the library
        if len(extra_books_in_library) != 0:
            tasks = []
            for library_type_number, extra_books in extra_books_in_library.items():
                account_obj: QiAccount = accounts_number_dict[library_type_number]
                tasks.append(asyncio.create_task(library.batch_remove_books_from_library(*extra_books,
                                                                                         account=account_obj)))
            await asyncio.gather(*tasks)
