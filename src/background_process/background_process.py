import asyncio
# import typing
# from multiprocessing.queues import Queue
from queue import Empty, Full
from .base_service import BaseService
from . import *
import typing
import traceback


class BackgroundProcess:
    def __init__(self, input_queue: Queue, output_queue: Queue, settings: Settings,
                 loop: asyncio.AbstractEventLoop = None):
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.settings = settings
        self.running = True
        self.commands_to_execute = []
        self.services: typing.Dict[str, BaseService] = {}
        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            assert issubclass(type(loop), asyncio.AbstractEventLoop)
            self.loop = loop
        self.command_handler_task = self.loop.create_task(self.command_handler())

    def __return_data(self, data):
        self.output_queue.put(data, block=False)

    async def main_loop(self):
        """The main loop of the process

        This is where all the interactions among all the services will be handled, and any exception the services queue
        will be handled here too
        """

    async def command_handler(self):
        pending_commands: typing.List[typing.Tuple[asyncio.tasks.Task, int]] = []
        while self.running:
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
                    self.__return_data(received_object.generate_return_time())
                if issubclass(received_object, Command):
                    if issubclass(received_object, ProcessCommand):
                        pass
                    elif issubclass(received_object, ServiceCommand):
                        service = self.services[received_object.name]
                    else:
                        self.__return_data(ErrorReport(ValueError, f"Invalid data type received at background process",
                                                       traceback.format_exc(), error_object=received_object))

            # will check if a command is done
            commands_to_be_cleared = []
            for command_tuple in pending_commands:
                command = command_tuple[0]
                started_at = command_tuple[1]
                if command.done():
                    pass
                else:
                    if time.time() - started_at > 20:
                        pass
                    else:
                        pass



