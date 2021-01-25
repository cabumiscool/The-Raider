from __future__ import annotations

import asyncio
import typing
import time
import json

import asyncpg

from dependencies.proxy_classes import Proxy
from dependencies.database.database_exceptions import *

from dependencies.webnovel.classes import *


class Database:
    def __init__(self, database_host: str, database_name: str, database_user: str, database_password,
                 database_port: int = 5432, min_conns: int = 3, max_conns: int = 10,
                 loop: asyncio.AbstractEventLoop = None):
        # self.db_connections = {}
        self._db_pool: asyncpg.pool.Pool
        self._running = False
        self._database_data = {'dsn': f'postgres://{database_user}:{database_password}'
                                      f'@{database_host}:{database_port}/{database_name}', 'min_size': min_conns,
                               'max_size': max_conns}

        self.loop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

        self.__async_init_task = self.loop.create_task(self.__pool_starter__())

    async def __pool_starter__(self):
        try:
            self._db_pool: asyncpg.pool.Pool = await asyncpg.create_pool(**self._database_data)
            self._running = True
            await self.__database_initializer__()
            print("connected to database")
            return True
        except Exception as e:
            raise DatabaseInitError(f'Databased failed to start with error:  {e}, type:  {type(e)}') from e

    async def __init_check__(self):
        if self._running:
            return
        await self.__async_init_task

    async def test(self):
        await self.__init_check__()
        data = await self._db_pool.fetch('SELECT version();')
        print(data)

    async def __database_initializer__(self):
        try:
            with open('./dependencies/database/database_initialization.sql') as file:
                query = file.read()
                await self._db_pool.execute(query)
        except FileNotFoundError:
            print('Please run the the launcher with the repository as the working directory.')

    async def permission_retriever(self, *ids, with_name=False):
        await self.__init_check__()
        if len(ids) == 0:
            raise DatabaseMissingArguments('Missing arguments at the permission retriever')
        if with_name:
            query = f'SELECT MAX("LEVEL"), "NAME" FROM "USER_AUTH" INNER JOIN "PERMISSIONS_NAMES" USING ("LEVEL") ' \
                    f'WHERE "ITEM_ID" IN({", ".join(f"${x + 1}" for x in range(len(ids)))})'
        else:
            query = f'SELECT MAX("LEVEL") FROM "USER_AUTH" WHERE "ITEM_ID" IN ' \
                    f'({", ".join(f"${x + 1}" for x in range(len(ids)))}) '
        data = await self._db_pool.fetchrow(query, *ids)
        permission_level = data[0]
        if with_name:
            return permission_level, data[1]
        return permission_level

    async def auth_retriever(self, include_roles: bool = False):
        await self.__init_check__()
        query = 'SELECT "ITEM_ID", "LEVEL", "NAME", "ROLE" FROM "USER_AUTH" ' \
                'INNER JOIN "PERMISSIONS_NAMES" USING ("LEVEL")'
        if include_roles is False:
            query = ' '.join((query, 'AND USER_AUTH.`ROLE` = 0'))

        data = await self._db_pool.fetch(query)
        return [{'id': item[0], 'level': item[1], 'nick': item[2], 'role': bool(item[3])} for item in data]

    async def auth_adder(self, target_id: int, level: int, role: bool = False, server_id: int = 0):
        await self.__init_check__()
        query = 'INSERT INTO "USER_AUTH" ("ITEM_ID", "LEVEL", "ROLE", "SERVER_ID") VALUES ($1, $2, $3, $4)'
        try:
            await self._db_pool.execute(query, target_id, level, int(role), server_id)
        except asyncpg.IntegrityConstraintViolationError:
            raise DatabaseDuplicateEntry from asyncpg.IntegrityConstraintViolationError

    async def auth_changer(self, target_id: int, level: int):
        await self.__init_check__()
        query = 'UPDATE "USER_AUTH" set "LEVEL" = $1 where "ITEM_ID" = $2'
        await self._db_pool.execute(query, level, target_id)

    async def whitelist_check(self, server_id: int, channel_id: int) -> int:
        await self.__init_check__()
        query = 'SELECT "WHITELIST_LEVEL" FROM "CHANNEL_AUTH" WHERE "SERVER_ID" = $1 AND "CHANNEL_ID" = $2'
        data = await self._db_pool.fetchval(query, server_id, channel_id)
        return data

    async def whitelist_add(self, server_id: int, channel_id: int, whitelist_level: int = 1):
        await self.__init_check__()
        query = 'INSERT INTO "CHANNEL_AUTH" ("SERVER_ID", "CHANNEL_ID", "WHITELIST_LEVEL") VALUES ($1, $2, $3)'
        try:
            await self._db_pool.execute(query, server_id, channel_id, whitelist_level)
        except asyncpg.IntegrityConstraintViolationError:
            raise DatabaseDuplicateEntry('CHANNEL AUTH has duplicates!') from asyncpg.IntegrityConstraintViolationError

    async def whitelist_remove(self, server_id: int, channel_id: int):
        await self.__init_check__()
        query = 'DELETE FROM "CHANNEL_AUTH" WHERE "SERVER_ID" = $1 AND "CHANNEL_ID" = $2'
        await self._db_pool.execute(query, server_id, channel_id)

    async def retrieve_all_book_chapters(self, book_id: int) -> typing.List[SimpleChapter]:
        await self.__init_check__()
        query = '''SELECT "PRIVILEGE", "CHAPTER_ID", "INDEX", "VIP_LEVEL", "CHAPTER_NAME", "VOLUME" 
        FROM "CHAPTERS" WHERE "BOOK_ID" = $1'''

        list_of_records = await self._db_pool.fetch(query, book_id)
        chapters = []
        for record in list_of_records:
            chapters.append(SimpleChapter(record[0], record[1], book_id, record[2], record[3], record[4],
                                          record[5]))

        return chapters

    async def retrieve_all_volumes(self, book_id: int) -> typing.List[Volume]:
        await self.__init_check__()
        all_chapters = await self.retrieve_all_book_chapters(book_id)
        requested_volumes = {}
        for chapter in all_chapters:
            if chapter.volume_index in requested_volumes:
                requested_volumes[chapter.volume_index].append(chapter)
            else:
                requested_volumes[chapter.volume_index] = [chapter]

        query = '''SELECT "NAME", "INDEX" FROM "VOLUMES" WHERE "BOOK_ID" = $1'''

        volumes_record = {}
        volume_record_list = await self._db_pool.fetch(query, book_id)
        for volume_record in volume_record_list:
            volumes_record[volume_record[1]] = {'volume_index': volume_record[1], 'book_id': book_id,
                                                'volume_name': volume_record[0]}

        volumes = []
        for volume_index, chapters_list in requested_volumes.items():
            volume_record = volumes_record.get(volume_index, {'volume_index': volume_index, 'book_id': book_id,
                                                              'volume_name': "UNKNOWN"})
            volumes.append(Volume(chapters_list=chapters_list, **volume_record))
        return volumes

    async def retrieve_all_simple_books(self) -> typing.List[SimpleBook]:
        await self.__init_check__()
        query = '''SELECT "BOOK_ID", "BOOK_NAME", "TOTAL_CHAPTERS", "COVER_ID", "BOOK_ABBREVIATION", "LIBRARY_NUMBER" 
        FROM "BOOKS_DATA"'''
        books_record_list = await self._db_pool.fetch(query)
        print(books_record_list)
        books = []
        for book_record in books_record_list:
            books.append(SimpleBook(book_record[0], book_record[1], book_record[2], book_record[3], book_record[4],
                                    book_record[5]))
        return books

    async def retrieve_simple_book(self, book_id: int) -> SimpleBook:
        await self.__init_check__()
        query = '''SELECT "BOOK_ID", "BOOK_NAME", "TOTAL_CHAPTERS", "COVER_ID", "BOOK_ABBREVIATION", "LIBRARY_NUMBER" 
        FROM "BOOKS_DATA" WHERE "BOOK_ID" = $1'''
        result = await self._db_pool.fetch(query, book_id)
        if len(result) == 0:
            raise NoEntryFoundInDatabaseError
        else:
            record = result[0]
        return SimpleBook(record[0], record[1], record[2], record[3], record[4], record[5])

    async def retrieve_complete_book(self, book_id: int) -> Book:
        complete_metadata_query = '''SELECT "BOOK_ID", "PRIVILEGE", "BOOK_TYPE", "BOOK_STATUS", "READ_TYPE" FROM 
        "FULL_BOOKS_DATA" WHERE "BOOK_ID" = $1'''
        # simple_book = await self.retrieve_simple_book(book_id)
        complete_metadata_query = '''SELECT "BOOK_ID", "BOOK_NAME", "TOTAL_CHAPTERS", "PRIVILEGE", "BOOK_TYPE",
        "COVER_ID", "BOOK_STATUS", "READ_TYPE", "BOOK_ABBREVIATION", "LIBRARY_NUMBER" FROM "BOOKS_DATA"
         INNER JOIN "FULL_BOOKS_DATA" USING ("BOOK_ID") WHERE "BOOK_ID" = $1;'''
        all_volumes_list = await self.retrieve_all_volumes(book_id)

        record = await self._db_pool.fetchrow(complete_metadata_query, book_id)
        abbreviation = record[8]
        book = Book(record[0], record[1], record[2], record[3], record[4], record[5], record[6], record[7],
                    abbreviation, library_number=record[9])
        book.add_volume_list(all_volumes_list)
        return book

    async def get_all_books_ids_names_sub_names_dict(self):
        pass

    async def retrieve_all_simple_comics(self) -> typing.List[SimpleComic]:
        pass


    async def retrieve_buyer_account(self) -> QiAccount:
        """Will retrieve an account for buying and should mark in the db either here or in sql that the account is being
         used to prevent a double count and attempting a buy when there aren't anymore fp"""

    async def __update_simple_book(self, chapter: SimpleBook):
        pass

    async def check_if_volume_entry_exists(self, book_id: int, volume_index: int):
        pass

    async def __insert_complete_book_data(self, book: Book, connection: asyncpg.Connection = None):
        await self.__init_check__()
        insert_query = '''INSERT INTO "FULL_BOOKS_DATA" ("BOOK_ID", "PRIVILEGE", "BOOK_TYPE", "READ_TYPE",
                         "BOOK_STATUS") VALUES ($1, $2, $3, $4, $5)'''
        query_arguments = (book.id, book.privilege, book.book_type_num, book.read_type_num, book.book_status)
        if connection:
            await connection.execute(insert_query, *query_arguments)
        else:
            await self._db_pool.execute(insert_query, *query_arguments)

    async def update_complete_book(self, book: Book, connection: asyncpg.Connection = None):
        pass

    async def insert_new_book(self, book: Book):
        await self.__init_check__()
        insert_book_query = f'''INSERT INTO "BOOKS_DATA" ("BOOK_ID", "BOOK_NAME", "BOOK_ABBREVIATION", 
                "TOTAL_CHAPTERS", "COVER_ID", "LIBRARY_NUMBER", "DATE_ADDED", "DATE_MODIFIED") 
                VALUES ($1, $2, $3, $4, $5, (
                    SELECT "LIBRARY_NUM" FROM "BOOKS_DATA"
                    RIGHT OUTER JOIN (SELECT generate_series AS "LIBRARY_NUM" FROM generate_series(
                        (select "STARTING_NUMBER" from "LIBRARY_RANGES" where "LIBRARY_TYPE" = 1)::int4,
                        (select "LAST_NUMBER" from "LIBRARY_RANGES" where "LIBRARY_TYPE" = 1)::int4)) as ti
                            ON "LIBRARY_NUMBER" = "LIBRARY_NUM"
                            GROUP BY "LIBRARY_NUM"
                            ORDER BY COUNT("LIBRARY_NUM")
                LIMIT 1), {time.time()}, {time.time()})'''  # not sure if leaving this declaration here or add as arg

        insert_book_query_args = (book.id, book.name, book.abbreviation, book.total_chapters, book.cover_id)
        volumes_list = book.return_volume_list()
        chapters = []
        # chapters = [volume.return_all_chapter_objs() for volume in volumes_list]
        for volume in volumes_list:
            chapters.extend(volume.return_all_chapter_objs())
        async with self._db_pool.acquire() as connection:
            connection: asyncpg.Connection
            async with connection.transaction():
                print('adding book')
                await connection.execute(insert_book_query, *insert_book_query_args, timeout=10)
                print('adding complete book')
                await self.__insert_complete_book_data(book, connection)
                print('adding volumes')
                for volume in volumes_list:
                    await self.insert_new_volume(volume, connection)
                print('adding chapters')
                await self.batch_add_chapters(*chapters, connection=connection)
                print('finished adding, closing transaction')
            print('closing connection')

        # could be used to return false in case of error somewhere in the future
        return True

    async def insert_new_volume(self, volume, connection: asyncpg.Connection = None):
        await self.__init_check__()
        query = 'INSERT INTO "VOLUMES" ("BOOK_ID", "NAME", "INDEX") VALUES ($1, $2, $3)'
        query_arguments = (volume.book_id, volume.name, volume.index)

        if connection:
            await connection.execute(query, *query_arguments)
        else:
            await self._db_pool.execute(query, *query_arguments)

    # async def batch_insert_new_volumes(self):
    #     await self.__init_check__()

    async def update_book(self, book: typing.Union[SimpleBook, Book], *, update_full: bool = True):
        """Will update the database entries to update"""
        assert issubclass(type(book), (SimpleBook, Book)) or isinstance(book, (SimpleBook, Book))
        if isinstance(book, SimpleBook) or update_full is False:
            await self.__update_simple_book(book)
        else:
            await self.update_complete_book(book)

    async def insert_new_chapter(self, chapter: typing.Union[SimpleChapter, Chapter]):
        assert isinstance(chapter, (Chapter, SimpleChapter)) or issubclass(type(chapter), (Chapter, SimpleChapter))
        await self.__init_check__()
        query = '''INSERT INTO "CHAPTERS" ("BOOK_ID", "CHAPTER_ID", "CHAPTER_NAME", "PRIVILEGE", "INDEX", "VIP_LEVEL", 
                "VOLUME") VALUES ($1, $2, $3, $4, $5, $6, $7)"'''
        chapter_tuple_formatted = (chapter.parent_id, chapter.id, chapter.name, chapter.is_privilege, chapter.index,
                                   chapter.is_vip, chapter.volume_index)
        await self._db_pool.execute(query, chapter_tuple_formatted)

    async def batch_add_chapters(self, *chapters: typing.Union[SimpleChapter, Chapter],
                                 connection: asyncpg.Connection = None):
        assert len(chapters) > 0
        await self.__init_check__()
        formatted_db_chapters = []
        query = '''INSERT INTO "CHAPTERS" ("BOOK_ID", "CHAPTER_ID", "CHAPTER_NAME", "PRIVILEGE", "INDEX", "VIP_LEVEL", 
        "VOLUME") VALUES ($1, $2, $3, $4, $5, $6, $7)'''
        for chapter in chapters:
            assert isinstance(chapter, (Chapter, SimpleChapter)) or issubclass(type(chapter), (Chapter, SimpleChapter))
            formatted_db_chapters.append((chapter.parent_id, chapter.id, chapter.name, chapter.is_privilege,
                                          chapter.index, chapter.is_vip, chapter.volume_index))
        if connection:
            await connection.executemany(query, formatted_db_chapters)
        else:
            await self._db_pool.executemany(query, formatted_db_chapters)

    async def retrieve_proxy(self, proxy_area_id: int = 2) -> Proxy:
        """Will retrieve a proxy from db
            :arg proxy_area_id if given will retrieve the proxy with that area id"""
        # proxy with id of 1 should be the waka proxy, #2 should be U.S. area
        pass

    async def retrieve_all_expired_proxies(self) -> typing.List[Proxy]:
        """Will retrieve all the proxies marked as expired from the db"""
        await self.__init_check__()
        query = '''SELECT "ID", "IP", "PORT", "TYPE", "UPTIME", "LATENCY", "SPEED", "REGION" FROM "PROXIES" WHERE 
        "EXPIRED" = True'''

        list_of_records = await self._db_pool.fetch(query)
        proxies = []
        for record in list_of_records:
            proxies.append(Proxy(record[0], record[1], record[2], record[3], record[4], record[5], record[6],
                                 record[7]))
        return proxies

    async def expired_proxy(self, proxy: Proxy):
        """Will set a proxy as expired"""
        query = '''UPDATE "PROXIES" SET "EXPIRED" = TRUE WHERE "ID" = $1'''
        await self._db_pool.execute(query, proxy.id)

    async def mark_as_working_proxy(self, proxy: Proxy):
        """Will set a proxy as working"""
        query = '''UPDATE "PROXIES" SET "EXPIRED" = FALSE WHERE "ID" = $1'''
        await self._db_pool.execute(query, proxy.id)

    async def set_library_pages_number(self, account: QiAccount, pages_number: int):
        pass

    async def retrieve_library_account(self, library_type: int) -> QiAccount:
        """Will retrieve an account that has an specific library number assign"""
        query = '''SELECT "ID", "EMAIL", "PASSWORD", "COOKIES", "TICKET", "EXPIRED", "UPDATED_AT", "FP", "LIBRARY_TYPE",
        "LIBRARY_PAGES", "MAIN_EMAIL", "GUID" WHERE "LIBRARY_TYPE" = $1 AND "EXPIRED" = 0'''  # TODO to sort by fp
        account_record = await self._db_pool.fetchrow(query, library_type)
        account = QiAccount(account_record[0], account_record[1], account_record[2], account_record[3],
                            account_record[4], account_record[5], account_record[6], account_record[7],
                            account_record[8], account_record[9], account_record[10], account_record[11])
        return account

    async def retrieve_all_library_type_accounts(self, library_type: int) -> typing.List[QiAccount]:
        pass

    async def retrieve_account_stats(self) -> typing.Tuple[typing.Tuple[int, int], int]:
        account_stats_query = 'SELECT COUNT(*), SUM("FP") From "QIACCOUNT" WHERE "EXPIRED" = false '
        all_accounts_count_query = 'select count(*) from "QIACCOUNT"'
        all_accounts_record = await self._db_pool.fetchrow(all_accounts_count_query)
        account_stats_record = await self._db_pool.fetchrow(account_stats_query)
        non_expired_accounts, fp_sum = account_stats_record[0], account_stats_record[1]
        if fp_sum is None:
            fp_sum = 0
        return (non_expired_accounts, all_accounts_record[0]), fp_sum

    async def expired_account(self, account: QiAccount):
        pass

    async def release_account(self, account: QiAccount):
        """Will set an in use account as available again"""
        pass

    # TODO Delete once complete migration from seeker to raider
    async def retrieve_email_accounts(self) -> typing.Dict[int: EmailAccount]:
        query = 'SELECT "ID", "EMAIL_ADDRESS", "EMAIL_PASSWORD" FROM "EMAIL_ACCOUNTS"'
        records_list = await self._db_pool.fetch(query)
        email_objs = []
        for record in records_list:
            email_objs.append(EmailAccount(record[1], record[2], record[0]))
        return email_objs

    # delete too
    async def retrieve_all_qi_accounts_guid(self):
        query = 'SELECT "GUID" FROM "QIACCOUNT"'
        records = await self._db_pool.fetch(query)
        return [record[0] for record in records]

    # delete too
    async def insert_qi_account(self, qi_email: str, qi_password: str, qi_cookies: dict, qi_ticket: str, qi_guid: int,
                                expired: bool, fast_pass_count: int, main_email_id):
        query = '''INSERT INTO "QIACCOUNT" ("EMAIL", "PASSWORD", "COOKIES", "TICKET", "GUID", "EXPIRED", "FP",
        "MAIN_EMAIL") VALUES ($1, $2, $3, $4, $5, $6, $7, $8)'''
        query_args = (qi_email, qi_password, qi_cookies, qi_ticket, qi_guid, expired, fast_pass_count, main_email_id)
        await self._db_pool.execute(query, *query_args)

    async def batch_insert_qi_account(self, *args: typing.Tuple[str, str, dict, str, int, bool, int, int]):
        query = '''INSERT INTO "QIACCOUNT" ("EMAIL", "PASSWORD", "COOKIES", "TICKET", "GUID", "EXPIRED", "FP",
                "MAIN_EMAIL") VALUES ($1, $2, $3, $4, $5, $6, $7, $8)'''
        query_args_list = []
        for account in args:
            query_args_list.append((account[0], account[1], json.dumps(account[2]).replace("'", '"'),
                                    account[3], account[4], account[5], account[6], account[7]))
        await self._db_pool.executemany(query, query_args_list)

    # delete too
    async def update_qi_account(self, qi_guid: int, *, ticket: str = None, expired_status: bool = True,
                                fp_count: int = 0, cookies: dict = None):
        assert isinstance(expired_status, bool)
        query = '''UPDATE "QIACCOUNT" set "TICKET"=$1, "EXPIRED"=$2, "FP"=$3, "COOKIES"=$4 WHERE "GUID" = $5'''
        query_args = (ticket, expired_status, fp_count, json.dumps(cookies).replace("'", '"'), qi_guid)
        await self._db_pool.execute(query, *query_args)

    # delete too
    async def batch_update_qi_account(self, *args: typing.Tuple[int, str, bool, int]):
        query = '''UPDATE "QIACCOUNT" set "TICKET"=$1, "EXPIRED"=$2, "FP"=$3, "COOKIES"=$4 WHERE "GUID" = $5'''
        query_args_list = []
        for account_arg in args:
            query_args_list.append((account_arg[1], account_arg[2], account_arg[3],
                                    json.dumps(account_arg[4]).replace("'", '"'), account_arg[0]))
        await self._db_pool.executemany(query, query_args_list)
