import asyncio
import time
from operator import attrgetter

from .webnovel.classes import SimpleBook, SimpleChapter, QiAccount
from .webnovel.waka import book as waka_book
from .webnovel.web import book
from .database import Database
from .privatebin import upload_to_privatebin

paste_metadata = '<h3 data-book-Id="%s" data-chapter-Id="%s" data-almost-unix="%s" ' \
                 'data-SS-Price="%s" data-index="%s" data-is-Vip="%s" data-source="qi_latest" data-from="%s" ' \
                 '>Chapter %s:  %s</h3>'
data_from = ['qi', 'waka-waka']


async def generic_buyer(db: Database, book_: SimpleBook, *chapters: SimpleChapter):

    async def individual_buyer(buyer_account: QiAccount, chapter: SimpleChapter):
        if chapter.is_privilege:
            waka_proxy = await db.retrieve_proxy(1)
            chapter_obj = await waka_book.chapter_retriever(book_id=chapter.parent_id, chapter_id=chapter.id,
                                                            volume_index=chapter.volume_index, proxy=waka_proxy)
        else:
            chapter_obj = await book.chapter_buyer(book_id=chapter.parent_id, chapter_id=chapter.id,
                                                   account=buyer_account)

        return chapter_obj

    async def account_retriever() -> QiAccount:
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
    while True:
        account = await account_retriever()
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
        async_tasks.append(asyncio.create_task(individual_buyer(accounts_to_use[0], chapter)))
        accounts_to_use[0].fast_pass_count -= 1
        if accounts_to_use[0].fast_pass_count == 0:
            used_account = accounts_to_use.pop(0)
            accounts_used.append(used_account)

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
