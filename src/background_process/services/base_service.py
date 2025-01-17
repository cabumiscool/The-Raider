import typing
import time
import asyncio
import traceback

from .. import background_objects


class BaseService:
    """The base class from where all the services will inherit"""

    def __init__(self, name: str = None, loop_time: int = 20, *, output_service: bool = True):
        if name is None:
            self.name = self.__class__.__name__
        else:
            self.name = name
        self._input_queue = []
        self._output_queue = []
        self._encountered_errors = []
        self._running = False
        self._is_a_restart = False
        self._loop_interval = loop_time
        self.last_loop = 0
        self.output_service = output_service
        self._main_loop_task = None
        self._main_loop_task: asyncio.Task
        self._loop = asyncio.get_event_loop_policy().get_event_loop()

    def add_to_queue(self, *input_data):
        self._input_queue.extend(input_data)

    def _retrieve_input_queue(self) -> list:
        queue_content = self._input_queue.copy()
        self._input_queue.clear()
        return queue_content

    def add_to_error_queue(self, error: BaseException):
        self._encountered_errors.append(error)

    def retrieve_completed_cache(self) -> typing.Iterable:
        if len(self._encountered_errors) == 0:
            return_data = self._output_queue.copy()
            self._output_queue.clear()
            return return_data
        if len(self._encountered_errors) == 1:
            error_report = self._encountered_errors[0]
            self._encountered_errors.clear()
            raise error_report
        else:
            error_list = background_objects.ErrorList(*self._encountered_errors)
            self._encountered_errors.clear()
            raise error_list

    async def main(self):
        """This func will be the main logic of the service. it should be redeclared in every service and must not
        be the actual loop only the logic. The loop will be taken care of by the run func"""

    async def inner_error_handler(self):
        try:
            await self.main()
            return True
        except asyncio.CancelledError:
            error = background_objects.ErrorReport(asyncio.CancelledError, f'Service {self.name} received a cancel '
                                                                           f'command and was executed',
                                                   traceback.format_exc())
            self._encountered_errors.append(error)
            raise asyncio.CancelledError
        except Exception as e:
            error = background_objects.ErrorReport(type(e), 'error caught at top level execution of service',
                                                   traceback.format_exc(), str(e))
            self._encountered_errors.append(error)
            return False

    async def inner_loop_manager(self):
        while self._running:
            successful_run = await self.inner_error_handler()
            if successful_run:
                self.last_loop = time.time()
                self._is_a_restart = False
            await asyncio.sleep(self._loop_interval)

    def start(self):
        if self._running:
            raise background_objects.ServiceAlreadyRunningException(f"service '{self.name}' was attempted to be made to"
                                                                    f" start when it is already running")
        else:
            self._main_loop_task = self._loop.create_task(self.inner_loop_manager())
            self._running = True
            if self.last_loop == 0:
                self.last_loop = 1

    async def stop(self, *, timeout=30):
        timeout += 1
        if self._running:
            self._main_loop_task.cancel()
            starting_time = time.time()
            if self._main_loop_task.done():
                self._running = False
                self.last_loop = -1
                return True
            else:
                while True:
                    await asyncio.sleep(timeout / 3)
                    if self._main_loop_task.done():
                        self._running = False
                        self.last_loop = -1
                        return True
                    if (time.time() - starting_time) > timeout or time.time() - starting_time < timeout / 3:
                        raise TimeoutError
        else:
            raise background_objects.ServiceIsNotRunningException(
                f"service '{self.name}' was attempted to be made to stop "
                f"when it isn't running")

    def mark_restart(self):
        self._is_a_restart = True
