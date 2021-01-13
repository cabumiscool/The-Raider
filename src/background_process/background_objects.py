import time
import typing


class ErrorReport(Exception):
    def __init__(self, error: typing.Type[BaseException], error_comment: str, traceback: str, error_object=None):
        self.error = error
        self.comment = error_comment
        self.traceback = traceback
        self.error_object = error_object
        super().__init__()


class ProxyErrorReport(ErrorReport):
    def __init__(self, error: typing.Type[BaseException], error_comment: str, traceback: str, proxy_id: int,
                 error_object=None):
        super().__init__(error, error_comment, traceback, error_object)


class ErrorList(Exception):
    def __init__(self, *errors):
        self.errors = errors
        super().__init__()


class AlreadyRunningServiceError(Exception):
    pass


class ServiceIsNotRunningError(Exception):
    pass


class LibraryRetrievalError(BaseException):
    pass


class Command:
    """"Base class for all the background process command objects"""
    def __init__(self, command_id: int):
        self.id = command_id


class Ping:
    def __init__(self, command_id: int):
        self.id = command_id
        self.created = time.time()
        self.return_time = 0

    def generate_return_time(self):
        self.return_time = time.time()


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


class ProcessReturnData:
    def __init__(self, data_id: int, data):
        self.id = data_id
        self.data = data


class ServiceCommand(Command):
    def __init__(self, command_id: int, service_id: int):
        self.id = service_id
        super().__init__(command_id)


class StartService(ServiceCommand):
    pass


class StopService(ServiceCommand):
    pass


class RestartService(ServiceCommand):
    pass


# class ServiceStatus(ServiceCommand):
#   def __init__(self, command_id: int, service_name: str):
#       super().__init__(command_id, service_name)


class AllServicesStatus(Command):
    pass
