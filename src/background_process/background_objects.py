import time
import typing


class ErrorReport(BaseException):
    def __init__(self, error: typing.Type[BaseException], error_comment: str, traceback: str, error_object=None):
        self.error = error
        self.comment = error_comment
        self.traceback = traceback
        self.error_object = error_object


class ErrorList(BaseException):
    def __init__(self, *errors):
        self.errors = errors


class Command:
    def __init__(self, command_id: int):
        self.id = command_id
    """base class for all the background process command objects"""


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
    def __init__(self, command_id: int, service_name: str):
        self.name = service_name
        super().__init__(command_id)


class StartService(ServiceCommand):
    def __init__(self, command_id: int, service_name: str):
        super().__init__(command_id, service_name)


class StopService(ServiceCommand):
    def __init__(self, command_id: int, service_name: str):
        super().__init__(command_id, service_name)


class RestartService(ServiceCommand):
    def __init__(self, command_id: int, service_name: str):
        super().__init__(command_id, service_name)


# class ServiceStatus(ServiceCommand):
#     pass


class AllServicesStatus(Command):
    pass
