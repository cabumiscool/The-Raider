import typing
import background_objects
import traceback
import asyncio


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
        elif len(self._encountered_errors) == 1:
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
        while self._running:
            try:
                await self.main()
            except Exception as e:
                error = background_objects.ErrorReport(Exception, 'error caught at top level execution of service',
                                                       traceback.format_exc(), e)
                self._encountered_errors.append(error)
            await asyncio.sleep(self._loop_interval)
