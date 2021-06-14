import asyncio
import time
import typing
from operator import attrgetter

from dependencies.privatebin import upload_to_privatebin
from dependencies.webnovel import classes
from dependencies.webnovel.web.book import full_book_retriever
from .base_service import BaseService
from ..background_objects import ErrorList

paste_metadata = '<h3 data-book-Id="%s" data-chapter-Id="%s" data-almost-unix="%s" data-SS-Price="%s" data-index="%s"' \
                 ' data-is-Vip="%s" data-source="qi_latest" data-from="%s" >Chapter %s:  %s</h3>'
data_from = ['qi', 'waka-waka']


class Paste:
    def __init__(self, paste_id: str, paste_full_url: str, paste_delete_token: str, paste_passcode: str, status: int,
                 book: classes.Book, chapters_id: typing.List[int], ranges: typing.Tuple[int, int]):
        if type(paste_id) != str:
            self.id = str(paste_id)
        else:
            self.id = paste_id
        self.full_url = paste_full_url
        self.delete_token = paste_delete_token
        self.passcode = paste_passcode
        self.status_code = status
        self.book_obj = book
        self.chapters_ids = chapters_id
        self.ranges = ranges


class MultiPasteRequest:
    def __init__(self, *chapters: classes.Chapter, book: classes.SimpleBook):
        self.chapters = sorted(chapters, key=attrgetter('index'))
        self.request_time = time.time()
        self.book = book
        self.range = (self.chapters[0].index, self.chapters[-1].index)

    def return_paste_content(self):
        chapters_str = []
        for chapter in self.chapters:
            metadata = paste_metadata % (chapter.parent_id, chapter.id, self.request_time, chapter.price, chapter.index,
                                         chapter.is_vip, data_from[chapter.is_privilege], chapter.index, chapter.name)
            chapters_str.append('\n'.join((metadata, chapter.content)))
        return '\n'.join(chapters_str)


class PasteRequest:
    def __init__(self, chapter: classes.Chapter, book: classes.SimpleBook):
        self.chapter = chapter
        self.request_time = time.time()
        self.book = book

    def return_paste_content(self):
        chapter = self.chapter
        metadata = paste_metadata % (chapter.parent_id, chapter.id, self.request_time, chapter.price, chapter.index,
                                     chapter.is_vip, data_from[chapter.is_privilege], chapter.index, chapter.name)
        return '\n'.join((metadata, chapter.content))


async def paste_builder(paste_request: typing.Union[PasteRequest, MultiPasteRequest]):
    # paste_dict = await privatebinapi.send_async('https://vim.cx/', text=paste_request.return_paste_content(),
    #                                             formatting='markdown')
    paste_url = await upload_to_privatebin(paste_request.return_paste_content())
    complete_book = await full_book_retriever(paste_request.book)
    if isinstance(paste_request, PasteRequest):
        # return Paste(paste_dict['id'], paste_dict['full_url'], paste_dict['deletetoken'], paste_dict['passcode'],
        #              paste_dict['status'], complete_book, [paste_request.chapter.id],
        #              (paste_request.chapter.index, paste_request.chapter.index))
        return Paste('', paste_url, '', '', 0, complete_book, [paste_request.chapter.id],
                     (paste_request.chapter.index, paste_request.chapter.index))
    elif isinstance(paste_request, MultiPasteRequest):
        # return Paste(paste_dict['id'], paste_dict['full_url'], paste_dict['deletetoken'], paste_dict['passcode'],
        #              paste_dict['status'], complete_book, [chapter.id for chapter in paste_request.chapters],
        #              (paste_request.chapters[0].index, paste_request.chapters[-1].index))
        return Paste('', paste_url, '', '', 0, complete_book, [chapter.id for chapter in paste_request.chapters],
                     (paste_request.chapters[0].index, paste_request.chapters[-1].index))
    else:
        # should an error be raised here in case an unknown object is passed?
        pass


class PasteCreator(BaseService):
    def __init__(self):
        super().__init__('Paste Creator Service', loop_time=5)
        self.pastes_tasks = []

    async def main(self):
        completed_tasks = []
        exceptions = []
        input_content = self._retrieve_input_queue()
        input_content: typing.List[typing.Union[PasteRequest, MultiPasteRequest]]
        for item in input_content:
            self.pastes_tasks.append(asyncio.create_task(paste_builder(item)))

        # maybe write a wrapper here to catch the exceptions and retry
        # results = await asyncio.gather(*pastes, return_exceptions=True)
        for paste_task in self.pastes_tasks:
            paste_task: asyncio.Task
            if paste_task.done():
                if paste_task.cancelled():
                    completed_tasks.append(paste_task)
                else:
                    try:
                        self._output_queue.append(paste_task.result())
                        completed_tasks.append(paste_task)
                    except asyncio.CancelledError as e:
                        raise e
                    except Exception as e:
                        exceptions.append(e)
                        completed_tasks.append(paste_task)

        for completed_task in completed_tasks:
            self.pastes_tasks.remove(completed_task)

        if len(exceptions) > 1:
            raise ErrorList(*exceptions)
        elif len(exceptions) == 1:
            raise exceptions[0]
