import asyncio
import time
import typing
from operator import attrgetter

from .database import Database
from .database.database_exceptions import NoAccountFound
from .privatebin import upload_to_privatebin
from .webnovel.classes import SimpleBook, SimpleChapter, QiAccount, Chapter
from .webnovel.waka import book as waka_book
from .webnovel.web import book

paste_metadata = '<h3 data-book-Id="%s" data-chapter-Id="%s" data-almost-unix="%s" ' \
                 'data-SS-Price="%s" data-index="%s" data-is-Vip="%s" data-source="qi_latest" data-from="%s" ' \
                 '>Chapter %s:  %s</h3>'
data_from = ['qi', 'waka-waka']


async def paste_generator(book_name: str, chapter: Chapter):
    """
    Takes a chapter object and returns a string that contains the chapter's metadata and content, and
    uploads it to PrivateBin
    
    :param book_name: str
    :type book_name: str
    :param chapter: Chapter
    :type chapter: Chapter
    :return: The paste_url is being returned.
    """
    metadata = paste_metadata % (
        chapter.parent_id, chapter.id, time.time(), chapter.price, chapter.index,
        chapter.is_vip, data_from[chapter.is_privilege], chapter.index, chapter.name)
    chapter_content = '\n'.join((metadata, chapter.content))
    paste_response = await upload_to_privatebin(chapter_content)
    paste_url = f"!paste {book_name} - {chapter.index} <{paste_response}>"
    return paste_url


async def generic_buyer(db: Database, book_: SimpleBook, *chapters: SimpleChapter) -> Chapter:
    """
    Takes a book and a list of chapters, and returns a string that contains the chapters' content
    
    :param db: Database
    :type db: Database
    :param book_: SimpleBook
    :type book_: SimpleBook
    :param : db: Database
    :type : SimpleChapter
    :return: A coroutine object.
    """
    async def individual_buyer(inner_chapter: SimpleChapter, buyer_account: QiAccount = None):
        """
        If the chapter is a privilege chapter, then use a proxy to retrieve the chapter, otherwise use
        the buyer account to buy the chapter.
        
        :param inner_chapter: SimpleChapter
        :type inner_chapter: SimpleChapter
        :param buyer_account: QiAccount = None
        :type buyer_account: QiAccount
        :return: A chapter object
        """
        if inner_chapter.is_privilege:
            waka_proxy = await db.retrieve_proxy(1)
            chapter_obj = await waka_book.chapter_retriever(book_id=inner_chapter.parent_id,
                                                            chapter_id=inner_chapter.id,
                                                            volume_index=inner_chapter.volume_index, proxy=waka_proxy)
        else:
            if None:
                raise ValueError("No buyer account was given for a non priv chapter")
            chapter_obj = await book.chapter_buyer(book_id=inner_chapter.parent_id, chapter_id=inner_chapter.id,
                                                   account=buyer_account)

        return chapter_obj

    async def account_retriever() -> QiAccount:
        """
        Retrieves a buyer account from the database, checks if it's valid, and if it's not, it
        retrieves another one
        :return: The return value is a coroutine object.
        """
        buyer_account = await db.retrieve_buyer_account()
        while True:
            working = await buyer_account.async_check_valid()
            if working:
                break
            buyer_account = await db.retrieve_buyer_account()
        return buyer_account

    enough_fp_count = len(chapters)
    accounts_to_use = []
    accounts_used = []
    use_account = False
    while True:
        for chapter in chapters:
            if not chapter.is_privilege:
                use_account = True
                break
        if use_account is False:
            break
        try:
            account = await account_retriever()
        except NoAccountFound:
            if len(accounts_to_use) != 0:
                for account in accounts_to_use:
                    await db.release_account(account)
            return f"Couldn't retrieve a valid account to buy the chapter for {book_.name}, please try again...."
        db_fp_count = account.fast_pass_count
        await account.async_check_valid()
        qi_fp_count = account.fast_pass_count
        if qi_fp_count == 0:
            if db_fp_count != qi_fp_count:
                await db.update_account_fp_count(0, account)
            continue
        else:
            if db_fp_count != qi_fp_count:
                await db.update_account_fp_count(qi_fp_count, account)
            accounts_to_use.append(account)
            enough_fp_count = enough_fp_count - account.fast_pass_count
            if enough_fp_count <= 0:
                break

    async_tasks = []
    for chapter in chapters:
        if use_account:
            async_tasks.append(asyncio.create_task(individual_buyer(chapter, accounts_to_use[0])))
            accounts_to_use[0].fast_pass_count -= 1
            if accounts_to_use[0].fast_pass_count == 0:
                used_account = accounts_to_use.pop(0)
                accounts_used.append(used_account)
        else:
            async_tasks.append(asyncio.create_task(individual_buyer(chapter)))

    ranges = [chapter.index for chapter in chapters]
    ranges.sort()
    chapters = await asyncio.gather(*async_tasks)
    for used_account in accounts_used:
        await used_account.async_check_valid()
        await db.update_account_fp_count(used_account.fast_pass_count, used_account)
        await db.release_account(used_account)
    chapters.sort(key=attrgetter('index'))
    chapters_strings = []
    for chapter in chapters:
        metadata = paste_metadata % (
            chapter.parent_id, chapter.id, time.time(), chapter.price, chapter.index,
            chapter.is_vip, data_from[chapter.is_privilege], chapter.index, chapter.name)
        chapters_strings.append('\n'.join((metadata, chapter.content)))

    complete_string = '\n'.join(chapters_strings)

    paste_response = await upload_to_privatebin(complete_string)
    # paste_response = await privatebinapi.send_async(server='https://vim.cx/', text=complete_string,
    #                                                 formatting="markdown")
    if ranges[0] == ranges[-1]:
        range_str = f'{ranges[0]}'
    else:
        range_str = f'{ranges[0]}-{ranges[-1]}'

    book_name = book_.name
    if book_name.strip()[-1].isdigit():
        book_name = f'"{book_name}"'
    paste_url = f"!paste {book_name} - {range_str} <{paste_response}>"

    return paste_url


async def generic_buyer_obj(db: Database, book_: SimpleBook, *chapters: SimpleChapter):
    """
    Buys chapters for a book
    
    :param db: Database
    :type db: Database
    :param book_: SimpleBook
    :type book_: SimpleBook
    :param : param db: Database
    :type : SimpleChapter
    :return: A list of Chapter objects
    """
    async def individual_buyer(inner_chapter: SimpleChapter, buyer_account: QiAccount = None):
        """
        If the chapter is a privilege chapter, then use a proxy to retrieve the chapter, otherwise use
        the buyer account to buy the chapter.
        
        :param inner_chapter: SimpleChapter
        :type inner_chapter: SimpleChapter
        :param buyer_account: QiAccount = None
        :type buyer_account: QiAccount
        :return: A chapter object
        """
        if inner_chapter.is_privilege:
            waka_proxy = await db.retrieve_proxy(1)
            chapter_obj = await waka_book.chapter_retriever(book_id=inner_chapter.parent_id,
                                                            chapter_id=inner_chapter.id,
                                                            volume_index=inner_chapter.volume_index, proxy=waka_proxy)
        else:
            if None:
                raise ValueError("No buyer account was given for a non priv chapter")
            chapter_obj = await book.chapter_buyer(book_id=inner_chapter.parent_id, chapter_id=inner_chapter.id,
                                                   account=buyer_account)

        return chapter_obj

    async def account_retriever() -> QiAccount:
        """
        Retrieves a QiAccount from the database, checks if it's valid, and if it's not, it retrieves
        another QiAccount from the database
        :return: The return value is a coroutine object.
        """
        buyer_account = await db.retrieve_buyer_account()
        while True:
            working = await buyer_account.async_check_valid()
            if working:
                break
            buyer_account = await db.retrieve_buyer_account()
        return buyer_account

    enough_fp_count = len(chapters)
    accounts_to_use = []
    accounts_used = []
    use_account = False
    while True:
        for chapter in chapters:
            if not chapter.is_privilege:
                use_account = True
                break
        if use_account is False:
            break
        try:
            account = await account_retriever()
        except NoAccountFound:
            if len(accounts_to_use) != 0:
                for account in accounts_to_use:
                    await db.release_account(account)
            return f"Couldn't retrieve a valid account to buy the chapter for {book_.name}, please try again...."
        db_fp_count = account.fast_pass_count
        await account.async_check_valid()
        qi_fp_count = account.fast_pass_count
        if qi_fp_count == 0:
            if db_fp_count != qi_fp_count:
                await db.update_account_fp_count(0, account)
            continue
        else:
            if db_fp_count != qi_fp_count:
                await db.update_account_fp_count(qi_fp_count, account)
            accounts_to_use.append(account)
            enough_fp_count = enough_fp_count - account.fast_pass_count
            if enough_fp_count <= 0:
                break

    async_tasks = []
    for chapter in chapters:
        if use_account:
            async_tasks.append(asyncio.create_task(individual_buyer(chapter, accounts_to_use[0])))
            accounts_to_use[0].fast_pass_count -= 1
            if accounts_to_use[0].fast_pass_count == 0:
                used_account = accounts_to_use.pop(0)
            accounts_used.append(accounts_to_use[0])
        else:
            async_tasks.append(asyncio.create_task(individual_buyer(chapter)))

    ranges = [chapter.index for chapter in chapters]
    ranges.sort()
    chapters = await asyncio.gather(*async_tasks)
    chapters: typing.List[Chapter]
    for used_account in accounts_used:
        await used_account.async_check_valid()
        await db.update_account_fp_count(used_account.fast_pass_count, used_account)
        await db.release_account(used_account)
    chapters.sort(key=attrgetter('index'))



    ###
    # chapters_strings = []
    # for chapter in chapters:
    #     metadata = paste_metadata % (
    #         chapter.parent_id, chapter.id, time.time(), chapter.price, chapter.index,
    #         chapter.is_vip, data_from[chapter.is_privilege], chapter.index, chapter.name)
    #     chapters_strings.append('\n'.join((metadata, chapter.content)))
    #
    # complete_string = '\n'.join(chapters_strings)
    #
    # paste_response = await upload_to_privatebin(complete_string)
    # # paste_response = await privatebinapi.send_async(server='https://vim.cx/', text=complete_string,
    # #                                                 formatting="markdown")
    # if ranges[0] == ranges[-1]:
    #     range_str = f'{ranges[0]}'
    # else:
    #     range_str = f'{ranges[0]}-{ranges[-1]}'
    #
    # book_name = book_.name
    # if book_name.strip()[-1].isdigit():
    #     book_name = f'"{book_name}"'
    # paste_url = f"!paste {book_name} - {range_str} <{paste_response}>"
    ###

    return chapters
