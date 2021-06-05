from __future__ import annotations

import asyncio
import json
import time
import typing

import asyncpg

from .database_exceptions import *
from ..proxy_classes import Proxy, DummyProxy
from ..webnovel.classes import Chapter, Book, Volume, SimpleChapter, SimpleBook, SimpleComic, QiAccount, EmailAccount


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

    async def channel_type_adder(self, channel_id: int, channel_type: int):
        await self.__init_check__()
        query = """INSERT INTO "CHANNELS" ("CHANNEL_ID", "CHANNEL_TYPE") VALUES ($1, $2)"""
        query_args = (channel_id, channel_type)
        await self._db_pool.execute(query, *query_args)

    async def channel_type_remover(self, channel_type: int):
        await self.__init_check__()
        query = """DELETE FROM "CHANNELS" WHERE "CHANNEL_TYPE" =$1"""
        await self._db_pool.execute(query, channel_type)

    async def channel_type_updater(self, channel_id: int, channel_type: int):
        await self.__init_check__()
        query = """UPDATE "CHANNELS" SET "CHANNEL_ID"=$1 WHERE "CHANNEL_TYPE"=$2"""
        query_args = (channel_id, channel_type)
        await self._db_pool.execute(query, *query_args)

    async def channel_type_retriever(self, channel_type: int) -> typing.Union[None, int]:
        await self.__init_check__()
        query = """SELECT "CHANNEL_ID" FROM "CHANNELS" WHERE "CHANNEL_TYPE"=$1"""
        record = await self._db_pool.fetchrow(query, channel_type)
        if record is None:
            return None
        return record[0]

    async def all_channel_type_retriever(self):
        await self.__init_check__()
        query = """"""

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
        # complete_metadata_query = '''SELECT "BOOK_ID", "PRIVILEGE", "BOOK_TYPE", "BOOK_STATUS", "READ_TYPE" FROM
        # "FULL_BOOKS_DATA" WHERE "BOOK_ID" = $1'''
        # simple_book = await self.retrieve_simple_book(book_id)
        complete_metadata_query = '''SELECT "BOOK_ID", "BOOK_NAME", "TOTAL_CHAPTERS", "PRIVILEGE", "BOOK_TYPE",
        "COVER_ID", "BOOK_STATUS", "READ_TYPE", "BOOK_ABBREVIATION", "LIBRARY_NUMBER" FROM "BOOKS_DATA"
         INNER JOIN "FULL_BOOKS_DATA" USING ("BOOK_ID") WHERE "BOOK_ID" = $1;'''
        all_volumes_list = await self.retrieve_all_volumes(book_id)

        record = await self._db_pool.fetchrow(complete_metadata_query, book_id)
        if record is None:
            raise NoEntryFoundInDatabaseError
        abbreviation = record[8]
        book = Book(record[0], record[1], record[2], record[3], record[4], record[5], record[6], record[7],
                    abbreviation, library_number=record[9])
        book.add_volume_list(all_volumes_list)
        return book

    async def get_all_books_ids_and_names_dict(self, *, invert: bool = False) -> typing.Dict[str: int]:
        await self.__init_check__()
        request_query = '''SELECT "BOOK_NAME", "BOOK_ID" FROM "BOOKS_DATA"'''
        records_list = await self._db_pool.fetch(request_query)
        if len(records_list) == 0:
            return {}
        if invert:
            data_dict = {int(book_id): book_name for book_name, book_id in [(record[0],
                                                                             record[1]) for record in records_list]}
        else:
            data_dict = {book_name: int(book_id) for book_name, book_id in [(record[0],
                                                                             record[1]) for record in records_list]}
        return data_dict

    async def retrieve_all_simple_comics(self) -> typing.List[SimpleComic]:
        raise NotImplementedError

    async def retrieve_all_book_string_matches(self) -> dict:
        await self.__init_check__()
        query = 'SELECT "BOOK_ID", "BOOK_NAME", "BOOK_ABBREVIATION" FROM "BOOKS_DATA"'
        books_data = await self._db_pool.fetch(query)
        all_matches = {}
        for book_id, book_name, book_abbreviation in books_data:
            all_matches[book_id] = book_id
            all_matches[book_name] = book_id
            if book_abbreviation:
                all_matches[book_abbreviation] = book_id
        return all_matches

    async def get_chapter_objs_from_index(self, book_id: int, range_start: int, range_end: int) -> \
            typing.List[SimpleChapter]:
        await self.__init_check__()
        query = f'''SELECT "PRIVILEGE", "CHAPTER_ID", "INDEX", "VIP_LEVEL", "CHAPTER_NAME", "VOLUME" 
        FROM "CHAPTERS" WHERE "BOOK_ID" = $1 AND "INDEX" BETWEEN $2 AND $3'''
        chapters_records = await self._db_pool.fetch(query, book_id, range_start, range_end)
        chapters = []
        for chapter_record in chapters_records:
            chapters.append(SimpleChapter(chapter_record[0], chapter_record[1], book_id, chapter_record[2],
                                          chapter_record[3], chapter_record[4], chapter_record[5]))

        return chapters

    async def release_accounts_over_five_in_use_minutes(self):
        await self.__init_check__()
        release_query = '''UPDATE "QIACCOUNT" SET "IN_USE"=False 
        WHERE (select extract(epoch from now())) - "USE_TIME" >=300'''
        await self._db_pool.execute(release_query)

    async def retrieve_buyer_account(self) -> QiAccount:
        """Will retrieve an account for buying and should mark in the db either here or in sql that the account is being
         used to prevent a double count and attempting a buy when there aren't anymore fp"""
        await self.__init_check__()
        select_accounts_guid_with_fp_query = '''SELECT "GUID", "FP" FROM "QIACCOUNT" 
        WHERE "IN_USE"=False and "EXPIRED"=False and "FP" > 0 order by "FP" DESC'''
        accounts_with_fp_records = await self._db_pool.fetch(select_accounts_guid_with_fp_query)
        accounts_with_fp_tuples = ((guid, fp) for guid, fp in accounts_with_fp_records)
        # accounts_with_fp_tuples_sorted = accounts_with_fp_tuples.sort(key=itemgetter(1), reverse=True)
        update_query = '''UPDATE "QIACCOUNT" SET "IN_USE"=True, "USE_TIME" = (select extract(epoch from now())) 
        WHERE "GUID"=$1 and "IN_USE"=False'''
        selected_account_guid = 0
        for account_tuple in accounts_with_fp_tuples:
            guid, fp = account_tuple
            operation_status = await self._db_pool.execute(update_query, guid)
            if operation_status == 'UPDATE 1':
                selected_account_guid = guid
                break

        return await self.retrieve_specific_account(selected_account_guid)

    async def __update_simple_book(self, book: SimpleBook):
        await self.__init_check__()
        update_book_query = '''UPDATE "BOOKS_DATA" SET "BOOK_NAME"=$2, "TOTAL_CHAPTERS"=$3, "COVER_ID"=$4'''
        update_book_query_where_clause = 'WHERE "BOOK_ID"=$1'
        if book.qi_abbreviation:
            abbreviation = book.abbreviation
            update_book_query = f'{update_book_query}, "BOOK_ABBREVIATION"=$5 {update_book_query_where_clause}'
            query_args = (book.id, book.name, book.total_chapters, book.cover_id, abbreviation)
        else:
            update_book_query = f'{update_book_query} {update_book_query_where_clause}'
            query_args = (book.id, book.name, book.total_chapters, book.cover_id)
        await self._db_pool.execute(update_book_query, *query_args)

    async def check_if_volume_entry_exists(self, book_id: int, volume_index: int):
        raise NotImplementedError

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
        await self.__init_check__()
        update_book_query = '''UPDATE "FULL_BOOKS_DATA" SET "PRIVILEGE"=$2, "BOOK_TYPE"=$3, "READ_TYPE"=$4,
        "BOOK_STATUS"=$5 WHERE "BOOK_ID" = $1'''
        query_args = (book.id, book.privilege, book.book_type_num, book.read_type_num, book.book_status)
        if connection:
            await connection.execute(update_book_query, *query_args)
        else:
            await self._db_pool.execute(update_book_query, *query_args)

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
        await self.__init_check__()
        assert issubclass(type(book), (SimpleBook, Book)) or isinstance(book, (SimpleBook, Book))
        if isinstance(book, SimpleBook) or update_full is False:
            await self.__update_simple_book(book)
        else:
            await self.__update_simple_book(book.return_simple_book())
            await self.update_complete_book(book)

    async def insert_new_chapter(self, chapter: typing.Union[SimpleChapter, Chapter]):
        assert isinstance(chapter, (Chapter, SimpleChapter)) or issubclass(type(chapter), (Chapter, SimpleChapter))
        await self.__init_check__()
        query = '''INSERT INTO "CHAPTERS" ("BOOK_ID", "CHAPTER_ID", "CHAPTER_NAME", "PRIVILEGE", "INDEX", "VIP_LEVEL", 
                "VOLUME") VALUES ($1, $2, $3, $4, $5, $6, $7)'''
        chapter_tuple_formatted = (chapter.parent_id, chapter.id, chapter.name, chapter.is_privilege, chapter.index,
                                   chapter.is_vip, chapter.volume_index)
        try:
            await self._db_pool.execute(query, *chapter_tuple_formatted)
        except asyncpg.UniqueViolationError:
            raise DatabaseDuplicateEntry

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
        try:
            if connection:
                await connection.executemany(query, formatted_db_chapters)
            else:
                await self._db_pool.executemany(query, formatted_db_chapters)
        except asyncpg.UniqueViolationError:
            raise DatabaseDuplicateEntry

    async def delete_chapter(self, chapter: typing.Union[SimpleChapter, Chapter]):
        assert isinstance(chapter, (SimpleChapter, Chapter))
        await self.__init_check__()
        query = '''DELETE FROM "CHAPTERS" WHERE "CHAPTER_ID" = $1'''
        await self._db_pool.execute(query, chapter.id)

    async def batch_delete_chapters(self, *chapters: typing.Union[SimpleChapter, Chapter]):
        chapter_ids = []
        for obj in chapters:
            assert isinstance(obj, (SimpleChapter, Chapter))
            chapter_ids.append((obj.id,))
        await self.__init_check__()
        query = '''DELETE FROM "CHAPTERS" WHERE "CHAPTER_ID" = $1'''
        await self._db_pool.executemany(query, chapter_ids)

    async def update_chapter(self, chapter: typing.Union[SimpleChapter, Chapter]):
        assert isinstance(chapter, (SimpleChapter, Chapter))
        await self.__init_check__()
        query = '''UPDATE "CHAPTERS" SET "CHAPTER_NAME"=$1, "INDEX"=$2, "PRIVILEGE"=$3, "VIP_LEVEL"=$4, "VOLUME"=$5 
        WHERE "CHAPTER_ID"=$6'''
        await self._db_pool.execute(query, chapter.name, chapter.index, chapter.is_privilege, chapter.is_vip,
                                    chapter.volume_index, chapter.id)

    async def batch_update_chapters(self, *chapters: typing.Union[SimpleChapter, Chapter]):
        chapter_args = []
        for obj in chapters:
            assert isinstance(obj, (SimpleChapter, Chapter))
            chapter_args.append((obj.name, obj.index, obj.is_privilege, obj.is_vip,
                                 obj.volume_index, obj.id))
        await self.__init_check__()
        query = '''UPDATE "CHAPTERS" SET "CHAPTER_NAME"=$1, "INDEX"=$2, "PRIVILEGE"=$3, "VIP_LEVEL"=$4, "VOLUME"=$5 
        WHERE "CHAPTER_ID"=$6'''
        await self._db_pool.executemany(query, chapter_args)

    async def retrieve_proxies_ip(self):
        await self.__init_check__()
        query = 'SELECT "IP" FROM "PROXIES"'
        records_list = await self._db_pool.fetch(query)
        ips = []
        for record in records_list:
            ips.append(record[0])
        return ips

    async def add_proxy(self, ip: str, port: int, type_: str, uptime: int, latency: int, speed: str,
                        region: int):
        await self.__init_check__()
        query = '''INSERT INTO "PROXIES" ("IP", "PORT", "TYPE", "UPTIME", "TIME_ADDED", "LATENCY", "SPEED",
        "REGION") VALUES ($1, $2, $3, $4, (select extract(epoch from now())), $5, $6, $7)'''
        query_args = (ip, port, type_, uptime, latency, speed, region)
        await self._db_pool.execute(query, *query_args)

    async def batch_add_proxies(self, *args: typing.Tuple[str, int, str, int, str, str, int]):
        await self.__init_check__()
        query = '''INSERT INTO "PROXIES" ("IP", "PORT", "TYPE", "UPTIME", "TIME_ADDED", "LATENCY", "SPEED",
                "REGION") VALUES ($1, $2, $3, $4, (select extract(epoch from now())), $5, $6, $7)'''
        query_args = []
        for proxy_args in args:
            query_args.append((proxy_args[0], proxy_args[1], proxy_args[2], proxy_args[3], proxy_args[4], proxy_args[5],
                               proxy_args[6]))
        await self._db_pool.executemany(query, query_args)

    async def retrieve_proxy(self, proxy_area_id: int = 2) -> Proxy:
        """Will retrieve a proxy from db
            :arg proxy_area_id if given will retrieve the proxy with that area id"""
        # proxy with id of 1 should be the waka proxy, #2 should be U.S. area
        await self.__init_check__()
        if proxy_area_id == 2:
            return DummyProxy()
        else:
            query = '''SELECT "ID", "IP", "PORT", "TYPE", "UPTIME", "LATENCY", "SPEED", "REGION" 
            FROM "PROXIES" WHERE "EXPIRED" = False AND "REGION" = $1'''
            record = await self._db_pool.fetchrow(query, proxy_area_id)
            return Proxy(record[0], record[1], record[2], record[3], record[4], record[5], record[6], record[7])

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

    async def expired_proxy(self, proxy_id: int):
        """Will set a proxy as expired"""
        await self.__init_check__()
        query = '''UPDATE "PROXIES" SET "EXPIRED" = TRUE WHERE "ID" = $1'''
        await self._db_pool.execute(query, proxy_id)

    async def mark_as_working_proxy(self, proxy_id: int, new_download_speed: int, latency: int):
        """Will set a proxy as working"""
        await self.__init_check__()
        query = '''UPDATE "PROXIES" SET "EXPIRED" = false, "SPEED"=$1, "LATENCY"=$2 WHERE "ID" = $3'''
        query_args = (new_download_speed, latency, proxy_id)
        await self._db_pool.execute(query, *query_args)

    async def set_library_pages_number(self, account: QiAccount, pages_number: int):
        """will update the total number of library pages in the given account"""
        await self.__init_check__()
        query = '''UPDATE "QIACCOUNT" SET "LIBRARY_PAGES"=$1 WHERE "GUID"=$2'''
        query_args = (pages_number, account.guid)
        await self._db_pool.execute(query, *query_args)

    async def update_account_fp_count(self, fp_count: int, account: QiAccount, *, farm_update: bool = False):
        """Will update the fp count of the respective account"""
        await self.__init_check__()
        if farm_update:
            query = '''UPDATE "QIACCOUNT" SET "FP"=$1, "LAST_CURRENCY_UPDATE_AT"=$2 WHERE "GUID"=$3'''
            query_args = (fp_count, time.time(), account.guid)
        else:
            query = '''UPDATE "QIACCOUNT" SET "FP"=$1 WHERE "GUID"=$2'''
            query_args = (fp_count, account.guid)
        await self._db_pool.execute(query, *query_args)

    async def retrieve_specific_library_type_number_account(self, library_type: int) -> QiAccount:
        """Will retrieve an account that has an specific library number assign"""
        await self.__init_check__()
        query = '''SELECT "ID", "EMAIL", "PASSWORD", "COOKIES", "TICKET", "EXPIRED", "UPDATED_AT", "FP", "LIBRARY_TYPE",
        "LIBRARY_PAGES", "MAIN_EMAIL", "GUID" FROM "QIACCOUNT" WHERE "LIBRARY_TYPE" = $1 AND "EXPIRED" = False'''
        account_record = await self._db_pool.fetchrow(query, library_type)
        if account_record is None:
            raise NoEntryFoundInDatabaseError(f"No entry found for library type:  {library_type}")
        account = QiAccount(account_record[0], account_record[1], account_record[2], account_record[3],
                            account_record[4], account_record[5], account_record[6], account_record[7],
                            account_record[8], account_record[9], account_record[10], account_record[11])
        return account

    async def retrieve_expired_account(self) -> typing.Union[None, QiAccount]:
        """Will retrieve an expired account from the db giving priority to the library accounts"""
        await self.__init_check__()
        query = '''SELECT "ID", "EMAIL", "PASSWORD", "COOKIES", "TICKET", "EXPIRED", "UPDATED_AT", "FP", "LIBRARY_TYPE",
        "LIBRARY_PAGES", "MAIN_EMAIL", "GUID" FROM "QIACCOUNT" WHERE "EXPIRED" = TRUE and "IGNORE_RENEW" = False 
        ORDER BY "UPDATED_AT"'''
        account_record = await self._db_pool.fetchrow(query)
        if account_record is None:
            return None
        account = QiAccount(account_record[0], account_record[1], account_record[2], account_record[3],
                            account_record[4], account_record[5], account_record[6], account_record[7],
                            account_record[8], account_record[9], account_record[10], account_record[11])
        return account

    async def retrieve_all_library_type_number_accounts(self, library_type: int) -> typing.List[QiAccount]:
        await self.__init_check__()
        found_account_number = []
        accounts = []
        query = '''SELECT "ID", "EMAIL", "PASSWORD", "COOKIES", "TICKET", "EXPIRED", "UPDATED_AT", "FP", "LIBRARY_TYPE",
        "LIBRARY_PAGES", "MAIN_EMAIL", "GUID" 
        FROM "QIACCOUNT" WHERE "EXPIRED" = false AND "LIBRARY_TYPE" BETWEEN 
        (SELECT "STARTING_NUMBER" FROM "LIBRARY_RANGES" WHERE "LIBRARY_TYPE" = $1) AND
        (SELECT "LAST_NUMBER" FROM "LIBRARY_RANGES" WHERE "LIBRARY_TYPE" = $1)'''
        records = await self._db_pool.fetch(query, library_type)
        for record in records:
            if record[8] not in found_account_number:
                found_account_number.append(record[8])
                accounts.append(QiAccount(record[0], record[1], record[2], record[3], record[4], record[5], record[6],
                                          record[7], record[8], record[9], record[10], record[11]))
        return accounts

    async def retrieve_account_for_farming(self):
        """Will retrieve an account that the last currency update was 24 hrs ago"""
        query = '''SELECT "ID", "EMAIL", "PASSWORD", "COOKIES", "TICKET", "EXPIRED", "UPDATED_AT", "FP", "LIBRARY_TYPE",
        "LIBRARY_PAGES", "MAIN_EMAIL", "GUID" FROM "QIACCOUNT"
        WHERE (select extract(epoch from now())) - "LAST_CURRENCY_UPDATE_AT" >= 86400.0 and "EXPIRED" = False
          and "IN_USE" = False'''
        record = await self._db_pool.fetchrow(query)
        if record:
            return QiAccount(record[0], record[1], record[2], record[3], record[4], record[5], record[6], record[7],
                             record[8], record[9], record[10], record[11])
        return None

    async def retrieve_account_stats(self) -> typing.Tuple[typing.Tuple[int, int], int]:
        await self.__init_check__()
        account_stats_query = 'SELECT COUNT(*), SUM("FP") From "QIACCOUNT" WHERE "EXPIRED" = false '
        all_accounts_count_query = 'select count(*) from "QIACCOUNT"'
        all_accounts_record = await self._db_pool.fetchrow(all_accounts_count_query)
        account_stats_record = await self._db_pool.fetchrow(account_stats_query)
        non_expired_accounts, fp_sum = account_stats_record[0], account_stats_record[1]
        if fp_sum is None:
            fp_sum = 0
        return (non_expired_accounts, all_accounts_record[0]), fp_sum

    async def retrieve_specific_account(self, guid: int) -> QiAccount:
        """will retrieve an specific account using the guid"""
        await self.__init_check__()
        query = '''SELECT "ID", "EMAIL", "PASSWORD", "COOKIES", "TICKET", "EXPIRED", "UPDATED_AT", "FP", "LIBRARY_TYPE",
        "LIBRARY_PAGES", "MAIN_EMAIL", "GUID" FROM "QIACCOUNT" WHERE "GUID" = $1'''
        account_record_obj = await self._db_pool.fetchrow(query, guid)
        if account_record_obj is None:
            raise NoAccountFound
        account_obj = QiAccount(account_record_obj[0], account_record_obj[1], account_record_obj[2],
                                account_record_obj[3], account_record_obj[4], account_record_obj[5],
                                account_record_obj[6], account_record_obj[7], account_record_obj[8],
                                account_record_obj[9], account_record_obj[10], account_record_obj[11])
        return account_obj

    async def expired_account(self, account: QiAccount):
        """will set an account cookies as expired"""
        await self.__init_check__()
        query = 'UPDATE "QIACCOUNT" SET "EXPIRED"=TRUE, "IN_USE"=False WHERE "GUID"=$1'
        query_args = (account.guid,)
        await self._db_pool.execute(query, *query_args)

    async def update_account_params(self, account: QiAccount):
        """will update the cookies, ticket, and expired status of the given account at the db"""
        await self.__init_check__()
        query = f'UPDATE "QIACCOUNT" SET "COOKIES"=$1, "TICKET"=$2, "EXPIRED"=$3, ' \
                f'"UPDATED_AT"={time.time()} WHERE "GUID"=$4'
        query_args = (json.dumps(account.cookies), account.ticket, account.expired, account.guid)
        await self._db_pool.execute(query, *query_args)

    async def release_account(self, account: QiAccount):
        """Will set an in use account as available again"""
        await self.__init_check__()
        query = 'UPDATE "QIACCOUNT" SET "IN_USE"=FALSE WHERE "GUID"=$1'
        query_args = (account.guid,)
        await self._db_pool.execute(query, *query_args)

    async def retrieve_email_obj(self, *, id_: int = None, email_address: str = None):
        """Will retrieve an email account object using the keyword parameter given as the search key, only one given
        key will be used"""
        await self.__init_check__()
        query = '''SELECT "ID", "EMAIL_ADDRESS", "EMAIL_PASSWORD" FROM "EMAIL_ACCOUNTS"'''
        if id_:
            query += ' WHERE "ID" = $1'
            query_args = (id_,)
        elif email_address:
            query += ' WHERE "EMAIL_ADDRESS" = $1'
            query_args = (email_address,)
        else:
            raise Exception
        email_record = await self._db_pool.fetchrow(query, *query_args)
        return EmailAccount(email_record[1], email_record[2], email_record[0])

    async def retrieve_all_books_pings(self) -> typing.Union[typing.Dict[int: int], None]:
        """Will retrieve all the books ids that have users requesting to be pinged about an update"""
        query = '''SELECT "BOOK_ID", "USER_ID" FROM "PINGS_REQUESTS"'''
        rows = await self._db_pool.fetch(query)
        if len(rows) == 0:
            return None
        return_dict = {}
        for row in rows:
            book_id = int(row[0])
            user_id = int(row[1])
            if row[0] in return_dict:
                return_dict[book_id].append(user_id)
            else:
                return_dict[book_id] = [user_id]

        return return_dict

    async def insert_ping_request(self):
        pass

    async def remove_ping_request(self):
        pass

    # TODO Delete once complete migration from seeker to raider
    async def retrieve_email_accounts(self) -> typing.Dict[int: EmailAccount]:
        await self.__init_check__()
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
    # TODO make it also set time either in sql or python
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
