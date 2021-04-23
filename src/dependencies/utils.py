import asyncio
import time
from operator import attrgetter

from .webnovel.classes import SimpleBook, SimpleChapter
from .webnovel.waka import book as waka_book
from .webnovel.web import book
from .database import Database
from .privatebin import upload_to_privatebin

paste_metadata = '<h3 data-book-Id="%s" data-chapter-Id="%s" data-almost-unix="%s" ' \
                 'data-SS-Price="%s" data-index="%s" data-is-Vip="%s" data-source="qi_latest" data-from="%s" ' \
                 '>Chapter %s:  %s</h3>'
data_from = ['qi', 'waka-waka']


async def generic_buyer(db: Database, book_: SimpleBook, *chapters: SimpleChapter):
    waka_proxy = await db.retrieve_proxy(1)

    async def individual_buyer(chapter: SimpleChapter):
        buyer_account = await db.retrieve_buyer_account()
        while True:
            working = await buyer_account.async_check_valid()
            if working:
                break
            buyer_account = await db.retrieve_buyer_account()

        if chapter.is_privilege:
            chapter_obj = await waka_book.chapter_retriever(book_id=chapter.parent_id, chapter_id=chapter.id,
                                                            volume_index=chapter.volume_index, proxy=waka_proxy)
        else:
            chapter_obj = await book.chapter_buyer(book_id=chapter.parent_id, chapter_id=chapter.id,
                                                   account=buyer_account)

        await db.release_account(buyer_account)

        return chapter_obj

    async_tasks = [asyncio.create_task(individual_buyer(chapter)) for chapter in chapters]
    ranges = [chapter.index for chapter in chapters]
    ranges.sort()
    chapters = await asyncio.gather(*async_tasks)
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
