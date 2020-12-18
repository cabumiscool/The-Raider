import typing
import asyncio
from background_process.base_service import BaseService
from background_process.background_objects import LibraryRetrievalError
from dependencies.database.database import PgDatabase
from dependencies.webnovel.web import library
from dependencies.webnovel.classes import Account, SimpleBook
from dependencies.proxy_manager import Proxy


async def retrieve_library_accounts(database: PgDatabase) -> typing.List[Account]:
    tasks = []
    for library_type in range(1, 11):
        tasks.append(asyncio.create_task(database.retrieve_library_account(library_type)))
    accounts = await asyncio.gather(*tasks)
    accounts: typing.List[Account]
    return accounts


async def test_account(account: Account):
    account_status = await account.async_check_valid()
    return account_status, account


async def retrieve_library_content(account: Account, proxy: Proxy):
    await library.retrieve_all_library_pages(account=account, proxy=Proxy)


class BooksLibraryChecker(BaseService):
    def __init__(self, database: PgDatabase):
        super().__init__('Book Checker Module')
        self.database = database

    async def main(self):
        accounts = await retrieve_library_accounts(self.database)
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
                    accounts.append(await self.database.retrieve_library_account(account.library_type))
            if len(working_accounts) == 10:
                break
            else:
                run_count += 1
            if run_count >= 3:
                raise LibraryRetrievalError

        # retrieves the books and orders them in the expected accounts groups
        simple_books_list = await self.database.retrieve_all_simple_books()
        books_dict = {}
        for simple_book in simple_books_list:
            if simple_book.library_number in books_dict:
                books_dict[simple_book.library_number][simple_book.id] = simple_book
            else:
                books_dict[simple_book.library_number] = {simple_book.id: simple_book}

        # retrieves a proxy to be used for the library check
        while True:
            proxy = await self.database.retrieve_proxy()
            working_proxy = await proxy.test()
            if working_proxy:
                break
            else:
                await self.database.expired_proxy(proxy)
                proxy = await self.database.retrieve_proxy()

        tasks = [asyncio.create_task(retrieve_library_content(account)) for account in working_accounts]
        results = await asyncio.gather(*tasks)
