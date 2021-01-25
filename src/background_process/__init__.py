import sys

from config import Settings

from background_process.background_objects import *
from background_process.background_process import BackgroundProcess

from dependencies.database.database import Database

import asyncio
from multiprocessing import Queue, Process
from queue import Empty


# process = BackgroundProcess(queue.Queue(), queue.Queue(), Settings())
# print(process)


def background_starter(input_queue: Queue, output_queue: Queue, config: Settings):
    policy = asyncio.get_event_loop_policy()
    policy.set_event_loop(policy.new_event_loop())
    loop = policy.get_event_loop()

    if sys.gettrace():  # checks if the code is running in debug mode and if it is it sets the loop in debug mode.
        # This is done as for some reason the pycharm debugger doesn't work otherwise
        loop.set_debug(True)

    BackgroundProcess(input_queue, output_queue, config, loop)
    loop.run_forever()


class BackgroundProcessInterface:
    def __init__(self, config: Settings):
        self.config = config
        self.toward_background = Queue()
        self.from_background = Queue()
        self.process: Process = Process()
        self._data_counter = 0
        self._data_returns = {}
        self.loop = asyncio.get_event_loop()
        self._data_receiver_task = self.loop.create_task(self.__data_receiver())
        self.start_process()

    def start_process(self):
        if self.process.is_alive():
            raise background_objects.AlreadyRunningProcessError
        else:
            self.toward_background = Queue()
            self.from_background = Queue()
            self.process = Process(target=background_starter, args=(self.toward_background, self.from_background,
                                                                    self.config), daemon=True)
            self.process.start()

    def is_alive(self):
        return self.process.is_alive()

    def stop_process(self):
        if self.process.is_alive():
            # TODO write a shutdown procedure
            pass
        else:
            raise background_objects.ProcessNotRunningError

    def __generate_data_id(self):
        self._data_counter += 1
        return self._data_counter

    def __send_data(self, data):
        self.toward_background.put(data, block=False)

    async def __data_receiver(self):
        while self.process.is_alive():
            try:
                data: background_objects.Command = self.from_background.get(block=False)
                self._data_returns[data.id] = data
            except Empty:
                await asyncio.sleep(3)

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
