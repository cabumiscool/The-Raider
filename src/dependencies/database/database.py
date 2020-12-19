import asyncio

import aiomysql
import asyncpg
import typing

from dependencies.webnovel.classes import *
from dependencies.proxy_manager import Proxy

# from . import database_exceptions
try:
    from . import *
except ImportError:
    from dependencies.database.database_exceptions import *


class PgDatabase:
    def __init__(self, database_host: str, database_name: str, database_user: str, database_password,
                 database_port: int = 5432, min_conns: int = 3, max_conns: int = 10,
                 loop: asyncio.AbstractEventLoop = None):
        self.db_connections = {}
        self.db_pool: asyncpg.pool.Pool
        self.running = False
        self._database_data = {'dsn': f'postgres://{database_user}:{database_password}'
                                      f'@{database_host}:{database_port}/{database_name}', 'min_size': min_conns,
                               'max_size': max_conns}

        self.loop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

        self.__async_init_task = self.loop.create_task(self.__pool_starter__())

    async def __pool_starter__(self):
        try:
            self.db_pool: asyncpg.pool.Pool = await asyncpg.create_pool(**self._database_data)
            self.running = True
            return True
        except Exception as e:
            raise database_exceptions.DatabaseInitError(f'Databased failed to start with error:  {e}, type:  {type(e)}')

    async def __init_check__(self):
        if self.running:
            return
        else:
            await self.__async_init_task
            return

    async def test(self):
        await self.__init_check__()
        async with self.db_pool.acquire() as connection:
            connection: asyncpg.Connection
            data = await connection.fetch('SELECT version();')
            print(data)

    async def permission_retriever(self, *ids, with_name=False):
        # TODO check if the sql works from mysql to postgres
        if len(ids) == 0:
            raise database_exceptions.DatabaseMissingArguments(f'Missing arguments at the permission retriever')
        # cursor = await self.__cursor_creator__()
        if with_name:
            query = f'SELECT MAX(USER_AUTH.`LEVEL`), NAME FROM USER_AUTH, PERMISSIONS_NAMES WHERE ITEM_ID IN ' \
                    f'({", ".join(f"${x}" for x in range(1, len(ids)))}) AND USER_AUTH.`LEVEL` = PERMISSIONS_NAMES.`LEVEL`'
        else:
            query = f'SELECT MAX(LEVEL) FROM USER_AUTH WHERE ITEM_ID IN ({", ".join(f"${x}" for x in range(1, len(ids)))}) '
        async with self.db_pool.acquire() as connection:
            connection: asyncpg.Connection
            data = await connection.fetchrow(query, ids)
            permission_level = data[0]
        # self.__cursor_recycle__(cursor)
        if with_name:
            return permission_level, data[1]
        else:
            return permission_level

    async def auth_retriever(self, include_roles: bool = False):
        # cursor = await self.__cursor_creator__()
        async with self.db_pool.acquire() as connection:
            connection: asyncpg.Connection
            query = 'SELECT USER_AUTH.`ITEM_ID`, USER_AUTH.`LEVEL`, PERMISSIONS_NAMES.`Name`, USER_AUTH.`ROLE` ' \
                    'FROM USER_AUTH, PERMISSIONS_NAMES WHERE USER_AUTH.`LEVEL` = PERMISSIONS_NAMES.`LEVEL`'
            if include_roles is False:
                query = ' '.join((query, 'AND USER_AUTH.`ROLE` = 0'))
            # await connection.execute(query)
            # TODO same as upward
            data = await connection.fetch(query)
        # self.__cursor_recycle__(cursor)
        return ({'id': item[0], 'level': item[1], 'nick': item[2], 'role': bool(item[3])} for item in data)

    async def auth_adder(self, target_id: int, level: int, role: bool = False, server_id: int = 0):
        query = 'INSERT INTO USER_AUTH (ITEM_ID, LEVEL, ROLE, SERVER_ID) VALUES (%s, %s, %s, %s)'
        try:
            async with self.db_pool.acquire() as connection:
                connection: asyncpg.Connection
                await connection.execute(query, (target_id, level, int(role), server_id))
        except asyncpg.IntegrityConstraintViolationError:
            raise DatabaseDuplicateEntry

        # cursor = await self.__cursor_creator__()
        # try:
        #     await cursor.execute(query, (target_id, level, int(role), server_id))
        # except aiomysql.IntegrityError:
        #     raise DatabaseDuplicateEntry
        # except Exception as e:
        #     # print(e, type(e))
        #     raise e
        # finally:
        #     self.__cursor_recycle__(cursor)

    async def auth_changer(self, target_id: int, level: int):
        query = 'UPDATE USER_AUTH set LEVEL = %s where ITEM_ID = %s'
        # cursor = await self.__cursor_creator__()
        try:
            async with self.db_pool.acquire() as connection:
                connection: asyncpg.Connection
                await connection.execute(query, (level, target_id))
        except Exception as e:
            raise e
        # finally:
        #     self.__cursor_recycle__(cursor)

    async def whitelist_check(self, server_id: int, channel_id: int):
        query = 'SELECT count(1) FROM CHANNEL_AUTH WHERE SERVER_ID = $1 AND CHANNEL_ID = $2'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (server_id, channel_id))
            data = await cursor.fetchone()
            result = bool(data[0])
        except Exception as e:
            raise e
        finally:
            self.__cursor_recycle__(cursor)
        return result

    async def whitelist_add(self, server_id: int, channel_id: int, whitelist_level: int = 1):
        query = 'INSERT INTO CHANNEL_AUTH (SERVER_ID, CHANNEL_ID) VALUES ($1, $2)'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (server_id, channel_id))
        except aiomysql.IntegrityError:
            raise DatabaseDuplicateEntry('Duplicate values at CHANNEL AUTH')
        except Exception as e:
            raise e
        finally:
            self.__cursor_recycle__(cursor)
        return

    async def whitelist_remove(self, server_id: int, channel_id: int):
        query = 'DELETE FROM CHANNEL_AUTH WHERE SERVER_ID = $1 AND CHANNEL_ID = $2'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (server_id, channel_id))
        except Exception as e:
            raise e
        finally:
            self.__cursor_recycle__(cursor)
        return

    async def retrieve_all_simple_books(self) -> typing.List[SimpleBook]:
        pass

    async def retrieve_all_simple_comics(self) -> typing.List[SimpleComic]:
        pass

    async def retrieve_library_account(self, library_type: int) -> QiAccount:
        pass

    async def expired_account(self, account: QiAccount):
        pass

    async def retrieve_proxy(self) -> Proxy:
        pass

    async def expired_proxy(self, proxy: Proxy):
        pass

    async def set_library_pages_number(self, account: QiAccount, pages_number: int):
        pass

    def get_all_books_ids_names_sub_names_dict(self):
        pass


class Database:
    """to be deleted once migrated to other class"""

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

    def __cursor_recycle__(self, cursor: aiomysql.Cursor):
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
        self.__cursor_recycle__(cursor)
        if with_name:
            return permission, data[1]
        else:
            return permission

    async def auth_retriever(self, include_roles: bool = False):
        cursor = await self.__cursor_creator__()
        query = 'SELECT USER_AUTH.`ITEM_ID`, USER_AUTH.`LEVEL`, PERMISSIONS_NAMES.`Name`, USER_AUTH.`ROLE` ' \
                'FROM USER_AUTH, PERMISSIONS_NAMES WHERE USER_AUTH.`LEVEL` = PERMISSIONS_NAMES.`LEVEL`'
        if include_roles is False:
            query = ' '.join((query, 'AND USER_AUTH.`ROLE` = 0'))
        await cursor.execute(query)
        data = await cursor.fetchall()
        self.__cursor_recycle__(cursor)
        return ({'id': item[0], 'level': item[1], 'nick': item[2], 'role': bool(item[3])} for item in data)

    async def auth_adder(self, target_id: int, level: int, role: bool = False, server_id: int = 0):
        query = 'INSERT INTO USER_AUTH (ITEM_ID, LEVEL, ROLE, SERVER_ID) VALUES (%s, %s, %s, %s)'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (target_id, level, int(role), server_id))
        except aiomysql.IntegrityError:
            raise DatabaseDuplicateEntry
        except Exception as e:
            # print(e, type(e))
            raise e
        finally:
            self.__cursor_recycle__(cursor)

    async def auth_changer(self, target_id: int, level: int):
        query = 'UPDATE USER_AUTH set LEVEL = %s where ITEM_ID = %s'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (level, target_id))
        except Exception as e:
            raise e
        finally:
            self.__cursor_recycle__(cursor)

    async def whitelist_check(self, server_id: int, channel_id: int):
        query = 'SELECT count(1) FROM CHANNEL_AUTH WHERE SERVER_ID = %s AND CHANNEL_ID = %s'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (server_id, channel_id))
            data = await cursor.fetchone()
            result = bool(data[0])
        except Exception as e:
            raise e
        finally:
            self.__cursor_recycle__(cursor)
        return result

    async def whitelist_add(self, server_id: int, channel_id: int):
        query = 'INSERT INTO CHANNEL_AUTH (SERVER_ID, CHANNEL_ID) VALUES (%s, %s)'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (server_id, channel_id))
        except aiomysql.IntegrityError:
            raise DatabaseDuplicateEntry('Duplicate values at CHANNEL AUTH')
        except Exception as e:
            raise e
        finally:
            self.__cursor_recycle__(cursor)
        return

    async def whitelist_remove(self, server_id: int, channel_id: int):
        query = 'DELETE FROM CHANNEL_AUTH WHERE SERVER_ID = %s AND CHANNEL_ID = %s'
        cursor = await self.__cursor_creator__()
        try:
            await cursor.execute(query, (server_id, channel_id))
        except Exception as e:
            raise e
        finally:
            self.__cursor_recycle__(cursor)
        return


if __name__ == '__main__':
    async def main():
        database_obj = PgDatabase('5.9.57.20', 'raider-db', 'raider', 'ra1d3r')
        await database_obj.test()
        print(True)


    asyncio.run(main())
    # IP:
    # user:
    # password:
    # port: 5432
    # database
    # name:
