import asyncio
import typing

from background_process.base_service import BaseService
from dependencies.database.database import Database
from dependencies.webnovel import classes
from dependencies.webnovel.web import book


class NewChapterFinder(BaseService):
    def __init__(self, database: Database):
        super().__init__(name='Updated Chapter Finder Service', loop_time=10)
        self.database = database
        self.retrieving_books_tasks: typing.List[typing.Tuple[asyncio.Task, classes.SimpleBook]] = []

    async def compare_qi_book_to_db_book(self, book_obj: classes.SimpleBook):
        chapter_objs = []
        complete_qi_book = await book.full_book_retriever(book_obj)
        db_book = await self.database.retrieve_complete_book(book_id=book_obj.id)

        new_ids = (complete_qi_book != db_book)[0]

        for chapter_id in new_ids:
            chapter_objs.append(complete_qi_book.retrieve_chapter_by_id(chapter_id))

        return chapter_objs

    async def main(self):
        cache_content = self._retrieve_input_queue()
        cache_content: typing.List[classes.SimpleBook]

        # Commented as proxies aren't working  # TODO fix proxies
        # working_proxy = await self.database.retrieve_proxy()
        # while True:
        #     proxy_status = await working_proxy.test()
        #     if proxy_status:
        #         break
        #     else:
        #         working_proxy = await self.database.retrieve_proxy()

        for updated_book in cache_content:
            # full_book = await book.full_book_retriever(updated_book)
            self.retrieving_books_tasks.append((asyncio.create_task(self.compare_qi_book_to_db_book(updated_book)),
                                                updated_book))

        finished_tasks = []

        for book_task_tuple in self.retrieving_books_tasks:
            tuple_book = book_task_tuple[1]
            tuple_task = book_task_tuple[0]
            if tuple_task.done():
                if tuple_task.exception() is None:
                    chapter_objs = tuple_task.result()
                    self._output_queue.extend(chapter_objs)

                else:
                    finished_tasks.append(book_task_tuple)
                    self.retrieving_books_tasks.append((asyncio.create_task(self.compare_qi_book_to_db_book(tuple_book))
                                                        , tuple_book))

        for finished_task in finished_tasks:
            self.retrieving_books_tasks.remove(finished_task)
