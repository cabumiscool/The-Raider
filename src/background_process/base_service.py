import typing
import time
import asyncio
import traceback

import background_objects


class BaseService:
    """The base class from where all the services will inherit"""
    def __init__(self, name: str = None, loop_time: int = 20):
        if name is None:
            self.name = self.__class__.__name__
        else:
            self.name = name
        self._input_queue = []
        self._output_queue = []
        self._encountered_errors = []
        self._running = False
        self._loop_interval = loop_time
        self.last_loop = 0

    def add_to_queue(self, *input_data):
        self._input_queue.extend(input_data)

    def _retrieve_input_queue(self) -> list:
        queue_content = self._input_queue.copy()
        self._input_queue.clear()
        return queue_content

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

    async def run(self):
        if self._running:
            raise background_objects.AlreadyRunningServiceError()
        else:
            self._running = True
        while self._running:
            try:
                await self.main()
            except asyncio.CancelledError:
                error = background_objects.ErrorReport(asyncio.CancelledError, f'Service {self.name} received a cancel '
                                                                               f'command and was executed',
                                                       traceback.format_exc())
                self._encountered_errors.append(error)
                raise asyncio.CancelledError
            except Exception as e:
                error = background_objects.ErrorReport(Exception, 'error caught at top level execution of service',
                                                       traceback.format_exc(), e)
                self._encountered_errors.append(error)
            finally:
                self.last_loop = time.time()
            await asyncio.sleep(self._loop_interval)

    async def stop(self):
        if self._running:
            self._running = False
        else:
            raise background_objects.ServiceIsNotRunningError(f"service '{self.name}' was attempted to be made to stop "
                                                              f"when it isn't running")
