import typing
import time
import asyncio
from operator import attrgetter
import privatebinapi
from background_process.base_service import BaseService
from background_process import background_objects
from dependencies.webnovel import classes


paste_metadata = '<h3 data-book-Id="%s" data-chapter-Id="%s" data-almost-unix="%s" ' \
                 'data-SS-Price="%s" data-index="%s" data-is-Vip="%s" data-source="qi_latest" data-from="%s" ' \
                 '>Chapter %s:  %s</h3>'
data_from = ['qi', 'waka-waka']


class Paste:
    def __init__(self, paste_id: int, paste_full_url: str, paste_delete_token: str, paste_passcode: str, status: int,
                 name: str):
        if type(paste_id) != int:
            self.id = int(paste_id)
        else:
            self.id = paste_id
        self.full_url = paste_full_url
        self.delete_token = paste_delete_token
        self.passcode = paste_passcode
        self.status_code = status
        self.name = name


class MultiPasteRequest:
    def __init__(self, *chapters: classes.Chapter, book: classes.Book):
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
    def __init__(self, chapter: classes.Chapter, book: classes.Book):
        self.chapter = chapter
        self.request_time = time.time()
        self.book = book

    def return_paste_content(self):
        chapter = self.chapter
        metadata = paste_metadata % (chapter.parent_id, chapter.id, self.request_time, chapter.price, chapter.index,
                                     chapter.is_vip, data_from[chapter.is_privilege], chapter.index, chapter.name)
        return '\n'.join((metadata, chapter.content))


async def paste_builder(paste_request: typing.Union[PasteRequest, MultiPasteRequest]):
    paste_dict = await privatebinapi.send_async('https://vim.cx/', text=paste_request.return_paste_content(),
                                                formatting='markdown')
    if isinstance(paste_request, PasteRequest):
        return Paste(paste_dict['id'], paste_dict['full_url'], paste_dict['deletetoken'], paste_dict['passcode'],
                     paste_dict['status'], f"{paste_request.book.name} - {paste_request.chapter.index}")
    elif isinstance(paste_request, MultiPasteRequest):
        return Paste(paste_dict['id'], paste_dict['full_url'], paste_dict['deletetoken'], paste_dict['passcode'],
                     paste_dict['status'], f"{paste_request.book.name} - {paste_request.range[0]}-{paste_request.range[1]}")
    else:
        # should an error be raised here in case an unknown object is passed?
        pass


class PasteCreator(BaseService):
    def __init__(self):
        super().__init__('Paste Creator Module', loop_time=5)

    async def main(self):
        pastes = []
        exceptions = []
        input_content = self._retrieve_input_queue()
        input_content: typing.List[typing.Union[PasteRequest, MultiPasteRequest]]
        for item in input_content:
            pastes.append(asyncio.create_task(paste_builder(item)))

        results = await asyncio.gather(*pastes, return_exceptions=True)
        for paste in results:
            if issubclass(type(paste), Exception):
                exceptions.append(paste)
            else:
                self._output_queue.append(paste)

        if len(exceptions) > 1:
            raise background_objects.ErrorList(*exceptions)
        elif len(exceptions) == 1:
            raise exceptions[0]

