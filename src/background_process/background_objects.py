import time
# import typing
from dependencies.webnovel.classes import *


class ErrorReport(Exception):
    def __init__(self, error: typing.Type[BaseException], error_comment: str, traceback: str, error_object=None):
        self.error = error
        self.comment = error_comment
        self.traceback = traceback
        self.error_object = error_object


class ProxyErrorReport(ErrorReport):
    def __init__(self, error: typing.Type[BaseException], error_comment: str, traceback: str, proxy_id: int,
                 error_object=None):
        super().__init__(error, error_comment, traceback, error_object)
        self.proxy_id = proxy_id


class NoAvailableBuyerAccountFoundError(Exception):
    """Raised when no buyer account either valid or with enough fps is found"""


class ErrorList(Exception):
    def __init__(self, *errors):
        self.errors = errors


class AlreadyRunningProcessError(Exception):
    pass


class ProcessNotRunningError(Exception):
    pass


class AlreadyRunningServiceError(Exception):
    pass


class ServiceIsNotRunningError(Exception):
    pass


class LibraryRetrievalError(BaseException):
    pass


class Ping:
    def __init__(self, command_id: int):
        self.id = command_id
        self.created = time.time()
        self.received = 0

    def generate_return_time(self):
        self.received = time.time()


class Command:
    """"Base class for all the background process command objects"""
    _command_status = ['Unknown', 'Failed', 'Completed']

    def __init__(self, command_id: int):
        self.id = command_id
        self.command_status = 0
        self.text_status = ''

    def completed_status(self):
        self.command_status = 2
        self.text_status = self._command_status[self.command_status]

    def unknown_status(self, *, comment: str):
        self.text_status = f'{self._command_status[self.command_status]} status, return value:  {comment}'

    def failed_status(self, *, comment: str = None):
        self.command_status = 1
        if comment:
            self.text_status = comment
        else:
            self.text_status = self._command_status[self.command_status]


class ProcessCommand(Command):
    pass


class StartProcess(ProcessCommand):
    pass


class StopProcess(ProcessCommand):
    pass


class RestartProcess(ProcessCommand):
    pass


class HardRestartProcess(ProcessCommand):
    pass


# Might be deleted
class ProcessReturnData:
    def __init__(self, data_id: int, data):
        self.id = data_id
        self.data = data


class ServiceCommand(Command):
    def __init__(self, command_id: int, service_id: int):
        super().__init__(command_id)
        self.service_id = service_id


class StartService(ServiceCommand):
    pass


class StopService(ServiceCommand):
    pass


class RestartService(ServiceCommand):
    pass


class ForceQueueUpdate(Command):
    pass

# class ServiceStatus(ServiceCommand):
#   def __init__(self, command_id: int, service_name: str):
#       super().__init__(command_id, service_name)


class ServiceStatus:
    def __init__(self, service_id: int, service_name: str, last_execution: int):
        self.service_id = service_id
        self.service_name = service_name
        self.service_last_execution = last_execution


class ChapterStatus:
    status_dict = {0: 'Unknown', 1: 'in buy', 2: 'buy done', 3: 'in paste', 4: 'paste', 5: 'Extra loop at analyze'}

    def __init__(self, last_modified_time: float, chapter_obj: SimpleChapter, last_status: int):
        self.last_modified_time = last_modified_time
        self.base_obj = chapter_obj
        self.status = last_status
        self.status_str = self.status_dict[last_status]
        if self.status == 4:
            self.done = True
        else:
            self.done = False


class BookStatus:
    def __init__(self, last_modified_time: float, book_obj: SimpleBook, *chapter_status_tuple: ChapterStatus):
        self.last_modified_time = last_modified_time
        self.base_obj = book_obj
        self.chapters = chapter_status_tuple
        self.chapters_status_dict = {}
        self.ready_to_clean = True
        for chapter in self.chapters:
            if chapter.done is False:
                self.ready_to_clean = False
            if chapter.status_str in self.chapters_status_dict:
                self.chapters_status_dict[chapter.status_str] += 1
            else:
                self.chapters_status_dict[chapter.status_str] = 1
        if time.time() - self.last_modified_time < 300:
            self.ready_to_clean = False


class StatusRequest(Command):
    """The base class for the status requests"""


class QueueHistoryStatusRequest(StatusRequest):
    """Will request a status report on the history queue"""
    def __init__(self, command_id: int):
        super().__init__(command_id)
        self.books_status_list: typing.List[BookStatus] = []


class AllServicesStatus(StatusRequest):
    def __init__(self, command_id: int):
        super().__init__(command_id)
        self.services: typing.List[ServiceStatus] = []


class ProcessStatus(StatusRequest):
    def __init__(self, command_id: int):
        super().__init__(command_id)
        self.last_main_loop_execution = 0


class ChapterPing:
    def __init__(self, book_obj: SimpleBook, chapters_range: typing.List[typing.Tuple[int, int]], *users: int):
        self.book_obj = book_obj
        self.ranges = chapters_range
        self.users = users
