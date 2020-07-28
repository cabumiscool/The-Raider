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
        self.db_pool: aiomysql.Pool
        self.running = False
        self.database_data = {'minsize': min_conns, 'maxsize': max_conns, 'host': database_host, 'user': database_user,
                              'password': database_password, 'db': database_name, 'port': database_port,
                              'autocommit': True}
        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop
        self.__async_init_task = self.loop.create_task(self.__pool_starter__())

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
            self.db_pool = await aiomysql.create_pool(**self.database_data)
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
        await self.__init_check__()
        connection: aiomysql.Connection = self.db_connections[cursor]
        self.db_pool.release(connection)
        del self.db_connections[cursor]
        return

    async def permission_retriever(self, *ids, with_name=False):
        if len(ids) == 0:
            raise database_exceptions.DatabaseMissingArguments(f'Missing arguments at the permission retriever')
        cursor = await self.__cursor_creator__()
        if with_name:
            query = f'SELECT MAX(USER_AUTH.`LEVEL`), NAME FROM USER_AUTH, PERMISSIONS_NAMES WHERE ITEM_ID IN ' \
                    f'({", ".join(["%s"] * len(ids))}) AND USER_AUTH.`LEVEL` = PERMISSIONS_NAMES.`LEVEL`'
        else:
            query = f'SELECT MAX(LEVEL) FROM USER_AUTH WHERE ITEM_ID IN ({", ".join(["%s"] * len(ids))})'
        await cursor.execute(query, ids)
        data = await cursor.fetchone()
        permission = data[0]
        self.tasks.append(self.loop.create_task(self.__cursor_recycle__(cursor)))
        if permission is None:
            return 0
        else:
            if with_name:
                return permission, data[1]
            else:
                return permission

    async def auth_retriever(self, roles: bool = False):
        cursor = await self.__cursor_creator__()
        query = 'SELECT USER_AUTH.`ITEM_ID`, USER_AUTH.`LEVEL`, PERMISSIONS_NAMES.`Name`, USER_AUTH.`ROLE` ' \
                'FROM USER_AUTH, PERMISSIONS_NAMES WHERE USER_AUTH.`LEVEL` = PERMISSIONS_NAMES.`LEVEL`'
        if roles is False:
            query = ' '.join((query, 'AND USER_AUTH.`ROLE` = 0'))
        await cursor.execute(query)
        data = await cursor.fetchall()
        self.tasks.append(self.loop.create_task(self.__cursor_recycle__(cursor)))
        return ({'id': item[0], 'level': item[1], 'nick': item[2], 'role': bool(item[3])} for item in data)

    async def auth_adder(self, item_id: int, level: int, role: bool = False):
        query = 'INSERT INTO USER_AUTH (ITEM_ID, LEVEL, ROLE) VALUES (%s, %s, %s)'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (item_id, level, int(role)))
        except Exception as e:
            print(e)
        finally:
            self.tasks.append(self.loop.create_task(self.__cursor_recycle__(cursor)))
        return
