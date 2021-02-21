import time
import typing


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
    def __init__(self, command_id: int):
        self.id = command_id


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
    _services_status = ['Unknown', 'Failed', 'Completed']

    def __init__(self, command_id: int, service_id: int):
        super().__init__(command_id)
        self.service_id = service_id
        self.command_status = 0
        self.text_status = ''

    def completed_status(self):
        self.command_status = 2
        self.text_status = self._services_status[self.command_status]

    def unknown_status(self, *, comment: str):
        self.text_status = f'{self._services_status[self.command_status]} status, return value:  {comment}'

    def failed_status(self, *, comment: str = None):
        self.command_status = 1
        if comment:
            self.text_status = comment
        else:
            self.text_status = self._services_status[self.command_status]


class StartService(ServiceCommand):
    pass


class StopService(ServiceCommand):
    pass


class RestartService(ServiceCommand):
    pass


# class ServiceStatus(ServiceCommand):
#   def __init__(self, command_id: int, service_name: str):
#       super().__init__(command_id, service_name)

class StatusRequest(Command):
    """The base class for the status requests"""


class AllServicesStatus(StatusRequest):
    def __init__(self, command_id: int):
        super().__init__(command_id)
        self.services: typing.List[ServiceStatus] = []


class ServiceStatus:
    def __init__(self, service_id: int, service_name: str, last_execution: int):
        self.service_id = service_id
        self.service_name = service_name
        self.service_last_execution = last_execution


class ProcessStatus(StatusRequest):
    def __init__(self, command_id: int):
        super().__init__(command_id)
        self.last_main_loop_execution = 0

