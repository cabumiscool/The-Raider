from __future__ import annotations

import asyncio
import typing

import asyncpg

from dependencies.proxy_manager import Proxy
from dependencies.database.database_exceptions import *

from dependencies.webnovel.classes import SimpleBook, SimpleComic, QiAccount, Book, Chapter, SimpleChapter


class Database:
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
            await self.__database_initializer__()
            return True
        except Exception as e:
            raise DatabaseInitError(f'Databased failed to start with error:  {e}, type:  {type(e)}') from e

    async def __init_check__(self):
        if self.running:
            return
        await self.__async_init_task

    async def test(self):
        await self.__init_check__()
        data = await self.db_pool.fetch('SELECT version();')
        print(data)

    async def __database_initializer__(self):
        try:
            with open('./dependencies/database/database_initialization.sql') as file:
                query = file.read()
                await self.db_pool.execute(query)
        except FileNotFoundError:
            print('Please run the the launcher with the repository as the working directory.')

    async def permission_retriever(self, *ids, with_name=False):
        if len(ids) == 0:
            raise DatabaseMissingArguments('Missing arguments at the permission retriever')
        if with_name:
            query = f'SELECT MAX("LEVEL"), "NAME" FROM "USER_AUTH" INNER JOIN "PERMISSIONS_NAMES" USING ("LEVEL") ' \
                    f'WHERE "ITEM_ID" IN({", ".join(f"${x + 1}" for x in range(len(ids)))})'
        else:
            query = f'SELECT MAX("LEVEL") FROM "USER_AUTH" WHERE "ITEM_ID" IN ' \
                    f'({", ".join(f"${x + 1}" for x in range(len(ids)))}) '
        data = await self.db_pool.fetchrow(query, *ids)
        permission_level = data[0]
        if with_name:
            return permission_level, data[1]
        return permission_level

    async def auth_retriever(self, include_roles: bool = False):
        query = 'SELECT "ITEM_ID", "LEVEL", "NAME", "ROLE" FROM "USER_AUTH" ' \
                'INNER JOIN "PERMISSIONS_NAMES" USING ("LEVEL")'
        if include_roles is False:
            query = ' '.join((query, 'AND USER_AUTH.`ROLE` = 0'))

        data = await self.db_pool.fetch(query)
        return [{'id': item[0], 'level': item[1], 'nick': item[2], 'role': bool(item[3])} for item in data]

    async def auth_adder(self, target_id: int, level: int, role: bool = False, server_id: int = 0):
        query = 'INSERT INTO "USER_AUTH" ("ITEM_ID", "LEVEL", "ROLE", "SERVER_ID") VALUES ($1, $2, $3, $4)'
        try:
            await self.db_pool.execute(query, target_id, level, int(role), server_id)
        except asyncpg.IntegrityConstraintViolationError:
            raise DatabaseDuplicateEntry from asyncpg.IntegrityConstraintViolationError

    async def auth_changer(self, target_id: int, level: int):
        query = 'UPDATE "USER_AUTH" set "LEVEL" = $1 where "ITEM_ID" = $2'
        await self.db_pool.execute(query, level, target_id)

    async def whitelist_check(self, server_id: int, channel_id: int) -> int:
        query = 'SELECT "WHITELIST_LEVEL" FROM "CHANNEL_AUTH" WHERE "SERVER_ID" = $1 AND "CHANNEL_ID" = $2'
        data = await self.db_pool.fetchval(query, server_id, channel_id)
        return data

    async def whitelist_add(self, server_id: int, channel_id: int, whitelist_level: int = 1):
        query = 'INSERT INTO "CHANNEL_AUTH" ("SERVER_ID", "CHANNEL_ID", "WHITELIST_LEVEL") VALUES ($1, $2, $3)'
        try:
            await self.db_pool.execute(query, server_id, channel_id, whitelist_level)
        except asyncpg.IntegrityConstraintViolationError:
            raise DatabaseDuplicateEntry('CHANNEL AUTH has duplicates!') from asyncpg.IntegrityConstraintViolationError

    async def whitelist_remove(self, server_id: int, channel_id: int):
        query = 'DELETE FROM "CHANNEL_AUTH" WHERE "SERVER_ID" = $1 AND "CHANNEL_ID" = $2'
        await self.db_pool.execute(query, server_id, channel_id)

    async def retrieve_all_simple_books(self) -> typing.List[SimpleBook]:
        pass

    async def retrieve_complete_book(self, book: int) -> Book:
        pass

    async def retrieve_all_simple_comics(self) -> typing.List[SimpleComic]:
        pass

    async def retrieve_library_account(self, library_type: int) -> QiAccount:
        pass

    async def expired_account(self, account: QiAccount):
        pass

    async def retrieve_proxy(self, proxy_area_id: int = 2) -> Proxy:
        """Will retrieve a proxy from db
            :arg proxy_area_id if given will retrieve the proxy with that area id"""
        # proxy with id of 1 should be the waka proxy, #2 should be U.S. area
        pass

    async def expired_proxy(self, proxy: Proxy):
        pass

    async def set_library_pages_number(self, account: QiAccount, pages_number: int):
        pass

    def get_all_books_ids_names_sub_names_dict(self):
        pass

    async def retrieve_buyer_account(self) -> QiAccount:
        """Will retrieve an account for buying and should mark in the db either here or in sql that the account is being
         used to prevent a double count and attempting a buy when there aren't anymore fp"""

    async def __update_simple_book(self, chapter: SimpleBook):
        pass

    async def __update_complete_book(self, book: Book):
        pass

    async def update_book(self, book: typing.Union[SimpleBook, Book], *, update_full: bool = True):
        """Will update the database entries to update"""
        assert issubclass(type(book), (SimpleBook, Book)) or isinstance(book, (SimpleBook, Book))
        if isinstance(book, SimpleBook) or update_full is False:
            await self.__update_simple_book(book)
        else:
            await self.__update_complete_book(book)

    async def batch_add_chapters(self, *chapters: typing.Union[SimpleChapter, Chapter]):
        for chapter in chapters:
            assert isinstance(chapter, (Chapter, SimpleChapter)) or issubclass(type(chapter), (Chapter, SimpleChapter))
