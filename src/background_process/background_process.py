import time
import typing
import asyncio
import traceback

from queue import Empty
from multiprocessing.queues import Queue

from operator import attrgetter

from background_process.base_service import BaseService
from background_process.update_checking_service import BooksLibraryChecker
from background_process.new_chapter_finder import NewChapterFinder
from background_process.buyer_service import BuyerService
from background_process.paste_service import PasteCreator, PasteRequest, MultiPasteRequest, Paste
from background_process.background_objects import Ping, Command, ProcessCommand, ServiceCommand, ErrorReport, ErrorList

from dependencies.database import Database
from dependencies.webnovel import classes

from ..config import Settings


class BackgroundProcess:
    def __init__(self, input_queue: Queue, output_queue: Queue, settings: Settings, database: Database,
                 loop: asyncio.AbstractEventLoop = None):
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.settings = settings
        self.running = True
        self.commands_to_execute = []
        self.database = database
        self.services: typing.Dict[int, BaseService] = {1: BooksLibraryChecker(self.database),
                                                        2: NewChapterFinder(self.database),
                                                        3: BuyerService(self.database),
                                                        4: PasteCreator()}

        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            assert issubclass(type(loop), asyncio.AbstractEventLoop)
            self.loop = loop

        self.services.tasks = {id_: self.loop.create_task(service.run()) for id_, service in self.services.items()}
        self.command_handler_task = self.loop.create_task(self.command_handler())
        self._main_loop_task = self.loop.create_task(self.run())
        self.queue_history = {}

    def __return_data(self, data):
        self.output_queue.put(data, block=False)

    async def main_loop(self):
        """The main loop of the process

        This is where all the interactions among all the services will be handled, and any exception the services queue
        will be handled here too
        """

        # checking if there are new updated books from the library checker
        updated_book = []
        possible_new_books = []
        try:
            possible_new_books.extend(self.services[1].retrieve_completed_cache())
        except (ErrorReport, ErrorList) as e:
            self.__return_data(e)

        # checking if they aren't already in process
        for book in possible_new_books:
            book: classes.SimpleBook
            if book.id in self.queue_history:
                if book != self.queue_history[book.id]['obj']:
                    self.queue_history[book.id]['obj'] = book
                    self.queue_history[book.id]['_'] = time.time()
                    updated_book.append(book)
            else:
                self.queue_history[book.id] = {'obj': book, 'chs': {}, '_': time.time()}
                updated_book.append(book)

        # adding to the queue of the new chapters finder
        self.services[2].add_to_queue(*updated_book)

        # checking if there are new chapters in the output queue
        possible_new_chapters = []
        new_chapters = []

        try:
            possible_new_chapters.extend(self.services[2].retrieve_completed_cache())
        except (ErrorReport, ErrorList) as e:
            self.__return_data(e)

        for possible_chapter in possible_new_chapters:
            possible_chapter: classes.SimpleChapter
            if possible_chapter.id not in self.queue_history[possible_chapter.parent_id]['chs']:
                self.queue_history[possible_chapter.parent_id]['chs'][possible_chapter.id] = {'obj': possible_chapter,
                                                                                              '_': time.time(),
                                                                                              'done': False,
                                                                                              'in_paste': False,
                                                                                              'paste': False}
                new_chapters.append(possible_chapter)

        # TODO add the ping checker around here

        # adding to the queue of the chapter buyer
        self.services[3].add_to_queue(*new_chapters)

        # checking if there are new bought chapters in the output queue of the buyer service
        possible_new_bought_chapters = []
        new_bought_chapters = []
        try:
            possible_new_bought_chapters.extend(self.services[3].retrieve_completed_cache())
        except (ErrorReport, ErrorList) as e:
            self.__return_data(e)

        for possible_bought_chapter in possible_new_bought_chapters:
            possible_bought_chapter: classes.Chapter
            parent_id = possible_bought_chapter.parent_id
            id_ = possible_bought_chapter.id
            if self.queue_history[parent_id]['chs'][id_]['done'] is False:
                self.queue_history[parent_id]['chs'][id_]['done'] = True
                self.queue_history[parent_id]['chs'][id_]['in_paste'] = True
                self.queue_history[parent_id]['chs'][id_]['obj'] = possible_bought_chapter
                new_bought_chapters.append(possible_bought_chapter)

        # organizing the groups that are for pastes
        organized_chapters = {}
        for chapter in new_bought_chapters:
            if chapter.parent_id in organized_chapters:
                organized_chapters[chapter.parent_id].append(chapter)
            else:
                organized_chapters[chapter.parent_id] = [chapter]

        pastes_requests = []
        for book_id, chapter_list in organized_chapters.items():
            book_obj = self.queue_history[book_id]['obj']
            if len(chapter_list) > 1:
                chapter_list = sorted(chapter_list, key=attrgetter('index'))
                expected_index = chapter_list[0].index
                groups = []
                single_group = []
                for chapter in chapter_list:
                    if chapter.index == expected_index:
                        single_group.append(chapter)
                        expected_index += 1
                    else:
                        if len(single_group) >= 1:
                            groups.append(single_group)
                        single_group = [chapter]
                        expected_index = chapter.index + 1
                if len(single_group) >= 1:
                    groups.append(single_group)

                for group in groups:
                    if len(group) == 1:
                        pastes_requests.append(PasteRequest(group[0], book_obj))
                    else:
                        pastes_requests.append(MultiPasteRequest(*group, book=book_obj))
            else:
                pastes_requests.append(PasteRequest(chapter_list[0], book_obj))

        # adding to the paste creator service
        self.services[4].add_to_queue(*pastes_requests)

        # checking if there are new pastes from the paste creator
        possible_new_pastes = []
        try:
            possible_new_pastes.extend(self.services[4].retrieve_completed_cache())
        except (ErrorReport, ErrorList) as e:
            self.__return_data(e)

        for possible_paste in possible_new_pastes:
            possible_paste: Paste
            new_paste = False
            book_id = possible_paste.book_id
            for chapter_id in possible_paste.chapters_ids:
                if self.queue_history[book_id]['chs'][chapter_id]['paste'] is False:
                    self.queue_history[book_id]['chs'][chapter_id]['paste'] = True
                    new_paste = True
            if new_paste:
                self.__return_data(possible_paste)

        # clean up of queue history
        book_ids_to_delete = []
        for book_id, data_dict in self.queue_history.items():
            done = False
            for chapter_id, chapter_dict in data_dict['chs']:
                if chapter_dict['done'] is False:
                    break
                if chapter_dict['in_paste'] is False:
                    break
                if chapter_dict['paste'] is False:
                    break
            else:
                done = True

            # checking if it already passed 5 min after the book was detected as new
            if done:
                if time.time() - data_dict['_'] > 300:
                    book_ids_to_delete.append(book_id)

        # data should be saved to db around here using the ids that will be deleted
        # TODO

        # cleaning up
        for book_id in book_ids_to_delete:
            del self.queue_history[book_id]

    async def run(self):
        while self.running:
            await self.main_loop()
            await asyncio.sleep(5)

    async def command_handler(self):
        pending_commands: typing.List[typing.Tuple[asyncio.tasks.Task, int]] = []
        while self.running:
            # extracts objects from the queue
            objects = []
            try:
                while True:
                    received_object = self.input_queue.get(block=False)
                    objects.append(received_object)
            except Empty:
                pass

            # will analyze the received objects
            for received_object in objects:
                if isinstance(received_object, Ping):
                    self.__return_data(received_object.generate_return_time())
                if issubclass(received_object, Command):
                    if isinstance(received_object, ProcessCommand):
                        pass
                    elif isinstance(received_object, ServiceCommand):
                        service = self.services[received_object.name]
                    else:
                        self.__return_data(ErrorReport(ValueError, "Invalid data type received at background process",
                                                       traceback.format_exc(), error_object=received_object))

            # will check if a command is done
            commands_to_be_cleared = []
            for command_tuple in pending_commands:
                command = command_tuple[0]
                started_at = command_tuple[1]
                if command.done():
                    pass
                else:
                    if time.time() - started_at > 20:
                        pass
                    else:
                        pass
