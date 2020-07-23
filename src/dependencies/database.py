import asyncio
import json
import time
from random import randint

import aiomysql

from . import database_exceptions


class Database:
    def __init__(self, database_host: str, database_name: str, database_user: str, database_password,
                 database_port: int = 3306, min_conns: int = 3, max_conns: int = 10,
                 loop: asyncio.AbstractEventLoop = None):
        self.tasks = []
        self.db_connections = {}
        self.db_pool: aiomysql.Pool = None
        self.running = False
        self.database_data = {'minsize': min_conns, 'maxsize': max_conns, 'host': database_host, 'user': database_user,
                              'password': database_password, 'db': database_name, 'port': database_port,
                              'autocommit': True}
        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop
        self.__async_init_task = asyncio.create_task(self.__pool_starter__())

    async def __task_handler__(self):
        while self.running:
            try:
                if len(self.tasks) > 0:
                    task: asyncio.Task = self.tasks.pop()
                    await task
                else:
                    await asyncio.sleep(1)
            except Exception as e:
                # TODO: log this somehow
                pass
        return

    async def __pool_starter__(self):
        try:
            self.db_pool = aiomysql.create_pool(**self.database_data)
            self.running = True
            self.loop.create_task(self.__task_handler__())
            print('Database successfully connected')
            return True
        except Exception as e:
            raise database_exceptions.DatabaseInitError(f'Databased failed to start with error:  {e}, type:  {type(e)}')

    async def __init_check__(self):
        if self.running:
            return
        else:
            await self.__async_init_task
            return

    async def __cursor_creator__(self):
        await self.__init_check__()
        connection: aiomysql.Connection = await self.db_pool.acquire()
        cursor: aiomysql.Cursor = await connection.cursor()
        self.db_connections[cursor] = connection
        return cursor

    async def __cursor_recycle__(self, cursor: aiomysql.Cursor):
        pass
