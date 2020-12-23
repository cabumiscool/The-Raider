import asyncio
import typing

from background_process.base_service import BaseService
from dependencies.database.database import Database
from dependencies.webnovel import classes
from dependencies.webnovel.web import book


class NewChapterFinder(BaseService):
    def __init__(self, database: Database):
        super().__init__(name='Updated Chapter Finder Module')
        self.database = database

    async def main(self):
        cache_content = self._retrieve_input_queue()
        cache_content: typing.List[classes.SimpleBook]

        working_proxy = await self.database.retrieve_proxy()
        while True:
            proxy_status = await working_proxy.test()
            if proxy_status:
                break
            else:
                working_proxy = await self.database.retrieve_proxy()

        for updated_book in cache_content:
            chapter_objs = []

            full_book = await book.full_book_retriever(updated_book, proxy=working_proxy)

            database_book = await self.database.retrieve_complete_book(updated_book.id)

            new_ids = full_book != database_book

            for chapter_id in new_ids:
                chapter_objs.append(full_book.retrieve_chapter_by_id(chapter_id))

            self._output_queue.extend(chapter_objs)
