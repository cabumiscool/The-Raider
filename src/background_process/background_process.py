import time
import typing
import asyncio
import traceback

from queue import Empty
from multiprocessing.queues import Queue

# from operator import attrgetter

from background_process.base_service import BaseService
from background_process.update_checking_service import BooksLibraryChecker
from background_process.new_chapter_finder import NewChapterFinder
from background_process.buyer_service import BuyerService
from background_process.paste_service import PasteCreator, PasteRequest, MultiPasteRequest, Paste
# from background_process.proxy_manager_service import ProxyManager
from background_process.cookie_maintainer_service import CookieMaintainerService
from background_process.farmer_service import CurrencyFarmerService
from background_process.background_objects import *

from dependencies.database.database import Database
from dependencies.database.database_exceptions import DatabaseDuplicateEntry
from dependencies.webnovel import classes

from config import Settings


class BackgroundProcess:
    def __init__(self, input_queue: Queue, output_queue: Queue, config: Settings,
                 loop: asyncio.AbstractEventLoop = None):
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.settings = config
        self.running = True
        self.services_commands: typing.List[asyncio.Task] = []
        self.database = Database(database_host=config.db_host, database_name=config.db_name,
                                 database_user=config.db_user,
                                 database_password=config.db_password, database_port=config.db_port,
                                 min_conns=config.min_db_conns, max_conns=config.max_db_conns)
        self.services: typing.Dict[int: BaseService] = {1: BooksLibraryChecker(self.database),
                                                        2: NewChapterFinder(self.database),
                                                        3: BuyerService(self.database),
                                                        4: PasteCreator(),
                                                        # 5: ProxyManager(self.database)
                                                        5: CookieMaintainerService(self.database),
                                                        6: CurrencyFarmerService(self.database)
                                                        }

        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            assert issubclass(type(loop), asyncio.AbstractEventLoop)
            self.loop = loop

        for id_, service in self.services.items():
            service.start()
        # self.services[1].start()
        # self.services[2].start()
        # self.services[4].start()
        # self.services[5].start()
        # self.services[6].start()

        self.queue_history = {}
        self.last_main_loop = 0
        self.command_handler_task = self.loop.create_task(self.command_handler())
        self._main_loop_task = self.loop.create_task(self.run())

    def __return_data(self, data):
        # print("adding the next object to the output queue:  ", type(data), "  data:  ", data)
        # if type(data) != Ping and type(data) != Paste:
        #     print(f"sending data to the main proc obj:   {data},   type:  {data}")
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
        except ErrorReport as e:
            self.__return_data(e)
        except ErrorList as e:
            for error in e.errors:
                self.__return_data(error)

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
        except ErrorReport as e:
            self.__return_data(e)
        except ErrorList as e:
            for error in e.errors:
                self.__return_data(error)

        for possible_chapter in possible_new_chapters:
            possible_chapter: classes.SimpleChapter
            if possible_chapter.parent_id in self.queue_history:
                if possible_chapter.id not in self.queue_history[possible_chapter.parent_id]['chs']:
                    self.queue_history[possible_chapter.parent_id]['chs'][possible_chapter.id] = {'obj': possible_chapter,
                                                                                                  '_': time.time(),
                                                                                                  'in buy': True,
                                                                                                  'buy_done': False,
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
        except ErrorReport as e:
            self.__return_data(e)
        except ErrorList as e:
            for error in e.errors:
                self.__return_data(error)

        for possible_bought_chapter in possible_new_bought_chapters:
            possible_bought_chapter: classes.Chapter
            parent_id = possible_bought_chapter.parent_id
            id_ = possible_bought_chapter.id
            if self.queue_history[parent_id]['chs'][id_]['buy_done'] is False:
                self.queue_history[parent_id]['chs'][id_]['buy_done'] = True
                self.queue_history[parent_id]['chs'][id_]['in_paste'] = True
                self.queue_history[parent_id]['chs'][id_]['obj'] = possible_bought_chapter
                self.queue_history[parent_id]['chs'][id_]['_'] = time.time()
                new_bought_chapters.append(possible_bought_chapter)

        # organizing the groups that are for pastes
        organized_chapters = {}
        for chapter in new_bought_chapters:
            if chapter.parent_id in organized_chapters:
                organized_chapters[chapter.parent_id].append(chapter)
            else:
                organized_chapters[chapter.parent_id] = [chapter]

        # creating the paste request objects
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
        except ErrorReport as e:
            self.__return_data(e)
        except ErrorList as e:
            for error in e.errors:
                self.__return_data(error)

        for possible_paste in possible_new_pastes:
            possible_paste: Paste
            new_paste = False
            book_id = possible_paste.book_obj.id
            for chapter_id in possible_paste.chapters_ids:
                if self.queue_history[book_id]['chs'][chapter_id]['paste'] is False:
                    self.queue_history[book_id]['chs'][chapter_id]['paste'] = True
                    self.queue_history[book_id]['chs'][chapter_id]['_'] = time.time()
                    new_paste = True
            if new_paste:
                self.__return_data(possible_paste)

        await self.no_output_services_error_retrieval()
        await self.clean_queue()

    async def no_output_services_error_retrieval(self):
        for id_, service in self.services.items():
            if service.output_service is False:
                try:
                    service.retrieve_completed_cache()
                except ErrorReport as e:
                    self.__return_data(e)
                except ErrorList as e:
                    for error in e.errors:
                        self.__return_data(error)

    async def clean_queue(self):
        # clean up of queue history
        book_ids_to_delete = []
        for book_id, data_dict in self.queue_history.items():
            done = False
            if len(data_dict['chs']) == 0:
                if time.time() - data_dict['_'] == 60:
                    self.__return_data(
                        ErrorReport(Exception, f'book "{data_dict["obj"].name}" was found at the background '
                                               f'queue with no chapters in queue', "at the clean queue func"))
                continue  # TODO deal with this case better in case it fails to catch any new chapter as it
                # shouldn't even happen in the first place
            for chapter_id, chapter_dict in data_dict['chs'].items():
                if chapter_dict['buy_done'] is False:
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

        # saving data to db
        async_tasks = [asyncio.create_task(self.update_book_to_db_and_delete_local(book_id)) for
                       book_id in book_ids_to_delete]
        # for book_id in book_ids_to_delete:
        #     await self.database.update_book(self.queue_history[book_id]['obj'])
        #     chapters: typing.List[typing.Union[classes.Chapter, classes.SimpleChapter]] = []
        #     for chapter_id, chapter_data in self.queue_history[book_id]['chs'].items():
        #         chapter_id: int
        #         chapter_data: dict
        #         chapters.append(chapter_data['obj'])
        #     await self.database.batch_add_chapters(*chapters)
        #     del self.queue_history[book_id]

        await asyncio.gather(*async_tasks)

    async def update_book_to_db_and_delete_local(self, book_id: int):
        async_tasks = [asyncio.create_task(self.database.update_book(self.queue_history[book_id]['obj']))]

        chapters: typing.List[typing.Union[classes.Chapter, classes.SimpleChapter]] = []

        for chapter_id, chapter_data in self.queue_history[book_id]['chs'].items():
            chapter_id: int
            chapter_data: dict
            chapters.append(chapter_data['obj'])
        async_tasks.append(asyncio.create_task(self.database.batch_add_chapters(*chapters)))
        try:
            await asyncio.gather(*async_tasks)
        except DatabaseDuplicateEntry:
            for chapter_id, chapter_data in self.queue_history[book_id]['chs'].items():
                try:
                    await self.database.insert_new_chapter(chapter_data['obj'])
                except DatabaseDuplicateEntry:
                    pass
        del self.queue_history[book_id]

    async def force_queue_update(self, command: ForceQueueUpdate) -> ForceQueueUpdate:
        for book_id, data_dict in self.queue_history.items():
            self.queue_history[book_id]['_'] = data_dict['_'] - 300
            for chapter_id, chapter_data in data_dict['chs'].items():
                self.queue_history[book_id]['chs'][chapter_id]['buy_done'] = True
                self.queue_history[book_id]['chs'][chapter_id]['in_paste'] = True
                self.queue_history[book_id]['chs'][chapter_id]['paste'] = True

        # await self.clean_queue()

        command.unknown_status(comment="Result couldn't be verified")
        return command

    async def run(self):
        while self.running:
            try:
                await self.main_loop()
                self.last_main_loop = time.time()
                await asyncio.sleep(5)
            except Exception as e:
                self.__return_data(ErrorReport(type(e), f'found exception at the top in the background process',
                                               traceback.format_exc(), e))

    def unknown_received_object(self, object_, *, where: str = None):
        # traceback.format_exc()
        self.__return_data(ErrorReport(ValueError, f"Invalid data type received at background process, type:  "
                                                   f"{type(object_)}",
                                       f"at command handler on background process, exactly where:   {where}",
                                       error_object=object_))

    def read_history_queue(self) -> typing.List[BookStatus]:
        data_to_return = []
        for book_id, data_dict in self.queue_history.items():
            book_obj = data_dict['obj']
            if isinstance(book_obj, classes.Book):
                book_obj = book_obj.return_simple_book()
            # new_book_dict = {'book': book_obj, '_': data_dict['_'], 'chs': []}
            chapters_list = []
            for chapter_id, chapter_data in data_dict['chs'].items():
                chapter_id: int
                chapter_data: dict
                chapter_obj = chapter_data['obj']
                if isinstance(chapter_obj, classes.Chapter):
                    chapter_obj = chapter_obj.return_simple_chapter()
                # key = 'Unknown'
                # value = True
                status_int = 0
                for key, value in chapter_data.items():
                    if not isinstance(value, bool):
                        continue
                    if value is False:
                        break
                    status_int += 1

                # new_book_dict['chs'].append({'chapter': chapter_obj, '_': chapter_data['_'], 'status': (key, value)})
                chapters_list.append(ChapterStatus(chapter_data['_'], chapter_obj, status_int))
            data_to_return.append(BookStatus(data_dict['_'], book_obj, *chapters_list))
            # data_to_return.append(new_book_dict)
        return data_to_return

    async def service_stopper(self, service_command: ServiceCommand) -> ServiceCommand:
        service_to_use = self.services[service_command.service_id]
        try:
            await service_to_use.stop()
        except TimeoutError:
            service_command.failed_status()
        except ServiceIsNotRunningError:
            service_command.failed_status(comment=f'Service "{service_to_use.name}" is not running')
        except asyncio.CancelledError as e:
            raise e
        except Exception as e:
            service_command.unknown_status(comment=f"The following error was found when attempting to stop the "
                                                   f"{service_to_use.name}, error:  {e},  error type:   {type(e)}")
        else:
            service_command.completed_status()
        return service_command

    def service_starter(self, service_command: ServiceCommand) -> ServiceCommand:
        service_to_use = self.services[service_command.service_id]
        try:
            service_to_use.start()
        except AlreadyRunningServiceError:
            service_command.failed_status(comment=f"service {service_to_use.name} is already running")
        except asyncio.CancelledError as e:
            raise e
        except Exception as e:
            service_command.unknown_status(comment=f'The following error was found when attempting to '
                                                   f'stop service "{service_to_use.name}", '
                                                   f'error:  {e},  error type:  {type(e)}')
        return service_command

    async def service_restarter(self, service_command: ServiceCommand) -> ServiceCommand:
        service_to_use = self.services[service_command.service_id]

        successful_stop = False

        try:
            await service_to_use.stop()
        except ServiceIsNotRunningError:
            successful_stop = True
        except asyncio.CancelledError as e:
            raise e
        except TimeoutError:
            pass
        else:
            successful_stop = True

        if successful_stop is False:
            service_command.failed_status(comment=f"service {service_to_use.name} failed to stop successfully")
            return service_command

        try:
            service_to_use.start()
        except AlreadyRunningServiceError:
            service_command.failed_status(comment=f"service {service_to_use.name} failed to start")
            return service_command
        else:
            service_command.completed_status()
            return service_command

    async def command_handler(self):
        while self.running:
            try:
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
                        received_object.generate_return_time()
                        self.__return_data(received_object)
                    if issubclass(type(received_object), Command):
                        if isinstance(received_object, ForceQueueUpdate):
                            self.services_commands.append(asyncio.create_task(self.force_queue_update(received_object)))
                        elif isinstance(received_object, ProcessCommand):
                            pass  # TODO do this
                        elif issubclass(type(received_object), ServiceCommand):
                            if isinstance(received_object, StartService):
                                service_command = self.service_starter(received_object)
                                self.__return_data(service_command)
                            elif isinstance(received_object, StopService):
                                self.services_commands.append(asyncio.create_task(self.service_stopper(
                                    received_object)))

                            elif isinstance(received_object, RestartService):
                                self.services_commands.append(asyncio.create_task(self.service_restarter(
                                    received_object)))

                            else:
                                self.unknown_received_object(received_object, where='deciding what type of service '
                                                                                    'command it is')
                        elif issubclass(type(received_object), StatusRequest):
                            if isinstance(received_object, AllServicesStatus):
                                for service_id, service in self.services.items():
                                    received_object.services.append(ServiceStatus(service_id, service.name,
                                                                                  service.last_loop))
                                received_object.services.append(ServiceStatus(0, 'Main loop', self.last_main_loop))
                                self.__return_data(received_object)
                            if isinstance(received_object, QueueHistoryStatusRequest):
                                books_queue_status_list = self.read_history_queue()
                                received_object.books_status_list.extend(books_queue_status_list)
                                self.__return_data(received_object)
                        else:
                            self.unknown_received_object(received_object, where='deciding what type of command it is')
                            # self.__return_data(ErrorReport(ValueError, "Invalid data type received at background
                            # process", traceback.format_exc(), error_object=received_object))

                # will check if a service command is done
                task_to_be_cleared = []
                # for command_task, command_request in self.services_commands:
                for command_task in self.services_commands:
                    if command_task.done():
                        service_command = command_task.result()
                        task_to_be_cleared.append(command_task)
                        self.__return_data(service_command)
                    else:
                        pass
                for command_to_be_cleared in task_to_be_cleared:
                    self.services_commands.remove(command_to_be_cleared)

                await asyncio.sleep(1.5)
            except asyncio.CancelledError as e:
                raise e
            except Exception as e:
                self.__return_data(ErrorReport(type(e), 'error found at the command handler on the background',
                                               traceback.format_exc(), e))
