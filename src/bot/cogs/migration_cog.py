import datetime
import asyncio
from json import loads
from io import StringIO

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context

from bot import bot_exceptions, bot_utils
from bot.bot import Raider
from bot.cogs import bot_checks
from dependencies.database.database import Database

from background_process import BackgroundProcessInterface
from background_process.background_objects import *

from dependencies.webnovel.classes import QiAccount, Book
from dependencies.webnovel.web.book import full_book_retriever
from dependencies.proxy_classes import Proxy
from dependencies.webnovel.exceptions import FailedWebnovelRequest


class MigrationCog(commands.Cog):
    def __init__(self, bot: Raider):
        self.bot = bot
        self.config = bot.config
        self.db: Database = bot.db

    @bot_checks.check_permission_level(10)
    @commands.command()
    # TODO add a check that only seeker can run this command
    # TODO delete once raider can farm by itself
    async def load_wn_accounts(self, ctx: Context):
        await ctx.send('preparing to import')
        message_obj: discord.Message = ctx.message
        if len(message_obj.attachments) > 1 or len(message_obj.attachments) == 0:
            raise Exception
        data_file = message_obj.attachments[0]
        content_bin = await data_file.read()
        content_str = content_bin.decode()
        accounts_lists = [account_row.split('\t') for account_row in content_str.split('\n')]

        email_list = await self.db.retrieve_email_accounts()
        email_ids = {email_obj.email: email_obj.id for email_obj in email_list}

        accounts_guids = await self.db.retrieve_all_qi_accounts_guid()

        account_objs_list = [QiAccount(0, account[1], account[2], loads(account[3].replace("'", '"')), account[4],
                                       not bool(account[5]), 0, account[6], account[7], account[8], email_ids[account[9]],
                                       account[12]) for account in accounts_lists]

        accounts_to_insert = []
        accounts_to_update = []
        for account in account_objs_list:
            if account.guid in accounts_guids:
                accounts_to_update.append(account)
            else:
                accounts_to_insert.append(account)

        account_insert_args = []
        for account in accounts_to_insert:
            account_insert_args.append((account.email, account.password, account.cookies, account.ticket, account.guid,
                                        account.expired, account.fast_pass_count, account.host_email_id))
        await ctx.send(f'inserting {len(account_insert_args)} new accounts to db')
        if len(account_insert_args) > 0:
            await self.db.batch_insert_qi_account(*account_insert_args)

        account_update_args = []
        for account in accounts_to_update:
            account_update_args.append((account.guid, account.ticket, account.expired, account.fast_pass_count,
                                        account.cookies))

        await ctx.send(f'updating {len(account_update_args)} in the db')
        if len(account_update_args) > 0:
            await self.db.batch_update_qi_account(*account_update_args)

        await ctx.send('import successful')

    # TODO to be deleted after alpha
    @commands.command()
    @bot_checks.check_permission_level(10)
    async def import_proxies(self, ctx: Context, region: int):
        message_obj: discord.Message = ctx.message
        if len(message_obj.attachments) > 1 or len(message_obj.attachments) == 0:
            raise Exception

        await ctx.send('preparing to import')

        db_proxy_ips = await self.db.retrieve_proxies_ip()

        data_file = message_obj.attachments[0]
        content_bin = await data_file.read()
        content_str = content_bin.decode()
        proxies_list = [proxy_row.split('\t') for proxy_row in content_str.split('\n')]
        proxies_list.remove([''])
        proxy_objects_list = [Proxy(0, proxy[0], proxy[1], proxy[2], speed=proxy[3], uptime=proxy[4], latency=proxy[5],
                                    region=region) for proxy in proxies_list]

        proxies_to_add = []
        for proxy in proxy_objects_list:
            if proxy.return_ip() not in db_proxy_ips:
                proxies_to_add.append(proxy)

        insert_args = []
        for proxy in proxies_to_add:
            insert_args.append((proxy.return_ip(), proxy.return_port(), proxy.type_str, proxy.uptime, proxy.latency,
                                proxy.speed, proxy.region))

        await ctx.send(f'importing {len(insert_args)} proxies')

        if len(insert_args) > 0:
            await self.db.batch_add_proxies(*insert_args)

        await ctx.send('import complete')
        print(True)

    @commands.command()
    @bot_checks.has_attachment()
    @bot_checks.check_permission_level(10)
    async def import_batch_books(self, ctx: Context):
        message_obj = ctx.message
        attachments_list = message_obj.attachments
        attachment = attachments_list[0]
        file_content = await attachment.read()
        file_content_str = file_content.decode()
        list_of_book_ids_str = file_content_str.split('\n')
        list_of_book_ids = [int(book_id) for book_id in list_of_book_ids_str]

        books_to_retrieve = []
        dict_with_book_ids_and_names = await self.db.get_all_books_ids_and_names_dict(invert=True)
        for book_id in list_of_book_ids:
            if book_id not in dict_with_book_ids_and_names:
                books_to_retrieve.append(book_id)

        await ctx.send(f"Retrieving metadata for {len(books_to_retrieve)} from a "
                       f"requested total of {len(list_of_book_ids)}")

        async_tasks = []
        completed_books = []
        failed_books_id = []
        for book_id in books_to_retrieve:
            async_tasks.append((asyncio.create_task(full_book_retriever(book_id)), book_id))
        count_message = await ctx.send(f"Downloading metadata of books, 0 completed  "
                                       f"of a total of {len(books_to_retrieve)}")
        time_ = time.time()
        for task, book_id in async_tasks:
            try:
                book: Book = await task
            except (FailedWebnovelRequest, TimeoutError):
                failed_books_id.append(book_id)
                continue
            completed_books.append(book)
            if time.time() - time_ > 3:
                await count_message.edit(content=f"Downloading metadata of books, {len(completed_books)} "
                                                 f"completed  of a total of {len(books_to_retrieve)}")
                time_ = time.time()
        await count_message.edit(content=f"Metadata downloaded for {len(completed_books)}, failed books:  "
                                         f"{len(failed_books_id)}")
        missing_books_messages = []
        books_to_join = []
        count = 0
        for book_id in failed_books_id:
            books_to_join.append(str(book_id))
            count += 1
            if count >= 10:
                missing_books_messages.append("\n".join(books_to_join))
                books_to_join.clear()
                count = 0
        if len(books_to_join) > 0:
            missing_books_messages.append("\n".join(books_to_join))

        await ctx.send("failed books ids: ")
        for message in missing_books_messages:
            await ctx.send(message)

        await ctx.send(f"Preparing to add {len(completed_books)}.")
        count_message = await ctx.send("Starting.....")
        counter = 1
        error_books = []
        book_adding_tasks = [(asyncio.create_task(self.db.insert_new_book(book)), book)for book in completed_books]
        time_ = time.time()
        for task, book in book_adding_tasks:
            if time.time() - time_ > 3:
                await count_message.edit(content=f"Adding book {counter} of a total of {len(completed_books)}")
                time_ = time.time()
            counter += 1
            try:
                await task
            except asyncio.CancelledError as e:
                raise e
            except Exception:
                error_books.append(book)

        await count_message.edit(content=f"Finished adding books, number of failed books:  {len(error_books)}")
        for book in error_books:
            await ctx.send(f"Failed book name:  {book.name}  | Id:  {book.id}")


def setup(bot):
    cog = MigrationCog(bot)
    bot.add_cog(cog)
