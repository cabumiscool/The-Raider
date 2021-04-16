import typing

from operator import attrgetter

from background_process.base_service import BaseService
from background_process.background_objects import ChapterPing

from dependencies.database.database import Database

from dependencies.webnovel.classes import SimpleChapter


def build_chapters_ranges(chapters: typing.List[SimpleChapter]) -> typing.List[typing.Tuple[int, int]]:
    if len(chapters) == 1:
        return_list = [(chapters[0].index, chapters[0].index)]
        return return_list
    chapters.sort(key=attrgetter('index'))
    ranges = []
    starting_range = chapters[0].index
    expected_index = starting_range + 1
    for chapter in chapters:
        if expected_index == chapter.index:
            expected_index += 1
        else:
            ranges.append((starting_range, expected_index - 1))
            starting_range = chapter.index
            expected_index = starting_range + 1

    if len(ranges) == 0:
        ranges.append((chapters[0], chapters[-1]))
    else:
        if ranges[-1][0] != starting_range:
            ranges.append((starting_range, expected_index-1))

    return ranges


class PingService(BaseService):
    def __init__(self, database: Database):
        super().__init__(name='Update ping management service')
        self.db = database

    async def main(self):
        input_cache = self._retrieve_input_queue()
        input_cache: typing.List[SimpleChapter]

        if len(input_cache) == 0:
            return

        ping_requests_dict = await self.db.retrieve_all_books_pings()
        if ping_requests_dict is None:
            return

        books_to_retrieve = {}
        for released_chapter in input_cache:
            if released_chapter.id in ping_requests_dict:
                if released_chapter.parent_id not in books_to_retrieve:
                    books_to_retrieve[released_chapter.parent_id] = [released_chapter]
                else:
                    books_to_retrieve[released_chapter.parent_id].append(released_chapter)

        if len(books_to_retrieve) == 0:
            return

        for book_id, released_chapters in books_to_retrieve.items():
            books_obj = await self.db.retrieve_simple_book(book_id)
            self._output_queue.append(ChapterPing(books_obj, build_chapters_ranges(released_chapters),
                                                  *ping_requests_dict[book_id]))
