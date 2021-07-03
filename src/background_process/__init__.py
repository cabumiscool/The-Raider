import asyncio
import sys
from multiprocessing import Queue, Process
from queue import Empty

from config import ConfigReader
from .background_objects import *
from .background_process import BackgroundProcess
from .services.paste_service import Paste


# process = BackgroundProcess(queue.Queue(), queue.Queue(), ConfigReader())
# print(process)


def background_starter(input_queue: Queue, output_queue: Queue, config: ConfigReader):
    policy = asyncio.get_event_loop_policy()
    # policy.set_event_loop(policy.new_event_loop())
    policy.set_event_loop(asyncio.SelectorEventLoop())
    loop = policy.get_event_loop()

    if sys.gettrace():  # checks if the code is running in debug mode and if it is it sets the loop in debug mode.
        # This is done as for some reason the pycharm debugger doesn't work otherwise
        loop.set_debug(True)

    BackgroundProcess(input_queue, output_queue, config, loop)
    loop.run_forever()


class BackgroundProcessInterface:
    def __init__(self, config: ConfigReader):
        self.config = config
        self.toward_background = Queue()
        self.from_background = Queue()
        self.process: Process = Process()
        self._data_counter = 0
        self._data_returns = {}
        self._errors = []
        self._pastes = []
        self._pings = []
        self.loop = asyncio.get_event_loop()
        self._data_receiver_task = self.loop.create_task(self.__data_receiver())
        self.start_process()

    def start_process(self):
        if self.process.is_alive():
            raise background_objects.ProcessAlreadyRunningException
        else:
            self.toward_background = Queue()
            self.from_background = Queue()
            self.process = Process(target=background_starter, args=(self.toward_background, self.from_background,
                                                                    self.config), daemon=True)
            self.process.start()

    def is_alive(self):
        return self.process.is_alive()

    async def stop_process(self, *, graceful: bool = True):
        if self.process.is_alive():
            # TODO write a shutdown procedure
            if not graceful:
                self.__send_data(HardStopProcess)
                for x in range(0,5):
                    await asyncio.sleep(2)
                    if not self.is_alive():
                        return True
                self.process.kill()
                return True
        else:
            raise background_objects.ProcessNotRunningException

    def __generate_data_id(self):
        self._data_counter += 1
        return self._data_counter

    def __send_data(self, data):
        self.toward_background.put(data, block=False)

    async def __data_receiver(self):
        while self.process.is_alive():
            try:
                data: background_objects.Command = self.from_background.get(block=False)
                if isinstance(data, (ErrorReport, ErrorList)):
                    if isinstance(data, ErrorList):
                        self._errors.extend(data.errors)
                    else:
                        self._errors.append(data)
                elif isinstance(data, Paste):
                    self._pastes.append(data)
                elif isinstance(data, ChapterPing):
                    self._pings.append(data)
                else:
                    self._data_returns[data.id] = data
            except Empty:
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"Critical exception at data receiver in background manager.... error:  {e} | type:  {type(e)}")

    async def wait_data_return(self, data_id: int, *, timeout: int = 30):
        start_time = time.time()
        while True:
            try:
                data = self._data_returns[data_id]
                del self._data_returns[data_id]
                return data
            except KeyError:
                pass
            await asyncio.sleep(3)
            if time.time() - start_time > timeout - 3:
                raise TimeoutError

    async def send_ping(self) -> background_objects.Ping:
        data_id = self.__generate_data_id()
        ping = Ping(data_id)
        self.toward_background.put(ping)
        return await self.wait_data_return(data_id)

    def return_all_chapters_pings(self) -> typing.List[ChapterPing]:
        pastes = self._pings.copy()
        self._pings.clear()
        return pastes

    async def request_all_services_status(self) -> AllServicesStatus:
        data_id = self.__generate_data_id()
        request_object = AllServicesStatus(data_id)
        self.toward_background.put(request_object)
        return await self.wait_data_return(data_id)

    def return_all_exceptions(self) -> typing.List[ErrorReport]:
        errors = self._errors.copy()
        self._errors.clear()
        return errors

    def return_all_pastes(self) -> typing.List[Paste]:
        pastes_list = self._pastes.copy()
        self._pastes.clear()
        return pastes_list

    async def request_queue_status(self) -> QueueHistoryStatusRequest:
        data_id = self.__generate_data_id()
        request_object = QueueHistoryStatusRequest(data_id)
        self.toward_background.put(request_object)
        return await self.wait_data_return(data_id)

    async def force_queue_update(self) -> ForceQueueUpdate:
        data_id = self.__generate_data_id()
        request_object = ForceQueueUpdate(data_id)
        self.toward_background.put(request_object)
        return await self.wait_data_return(data_id)

    async def start_service(self, service_id: int) -> StartService:
        data_id = self.__generate_data_id()
        request_object = StartService(data_id, service_id)
        self.toward_background.put(request_object)
        return await self.wait_data_return(data_id)

    async def stop_service(self, service_id: int) -> StopService:
        data_id = self.__generate_data_id()
        request_object = StopService(data_id, service_id)
        self.toward_background.put(request_object)
        return await self.wait_data_return(data_id)

    async def restart_service(self, service_id: int) -> RestartService:
        data_id = self.__generate_data_id()
        request_object = RestartService(data_id, service_id)
        self.toward_background.put(request_object)
        return await self.wait_data_return(data_id)
