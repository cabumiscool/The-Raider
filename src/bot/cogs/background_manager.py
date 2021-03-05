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

from dependencies.webnovel.classes import QiAccount
from dependencies.proxy_classes import Proxy


class BackgroundManager(commands.Cog):
    def __init__(self, bot: Raider):
        self.bot = bot
        self.config = bot.config
        self.db: Database = bot.db
        self.background_process_interface = BackgroundProcessInterface(self.config)
        self.last_ping = 0
        self.ping_maker.add_exception_type(TimeoutError)
        self.ping_maker.start()
        self.error_retriever.start()
        self.pastes_retriever.start()

    @tasks.loop(seconds=5)
    async def ping_maker(self):
        await self.background_process_interface.send_ping()
        self.last_ping = time.time()

    @tasks.loop(seconds=3)
    async def error_retriever(self):
        # TODO add support to add a pickle file including the error object for deeper debugging
        error_channel: discord.TextChannel = await self.bot.fetch_channel(803352701295525908)
        # Todo: retrieve the error channel dynamically
        errors = self.background_process_interface.return_all_exceptions()
        async_tasks = []
        for error in errors:
            error_string = f'error occurred, comment: {error.comment} | error: {error.error} | ' \
                           f'error type:  {type(error)} '
            error_traceback = f' traceback: {error.traceback}'
            if len(error_string) + 3 + len(error_traceback) >= 2000:
                error_string = ''.join(('`', error_string, 'Traceback appended as the file below', '`'))
                traceback_file = discord.File(StringIO(error_traceback), 'error_traceback.txt')
                async_tasks.append(asyncio.create_task(error_channel.send(error_string, file=traceback_file)))
            else:
                error_string = '|'.join((error_string, error_traceback))
                error_string = ''.join(('`', error_string, '`'))
                async_tasks.append(asyncio.create_task(error_channel.send(error_string)))
        await asyncio.gather(*async_tasks)

    @tasks.loop(seconds=3)
    async def pastes_retriever(self):
        # TODO: retrieve the paste channel dynamically
        paste_channel: discord.TextChannel = await self.bot.fetch_channel(816682456714313780)
        # TODO add a different channel for og pastes before production
        pastes = self.background_process_interface.return_all_pastes()
        send_tasks = []
        for paste in pastes:
            if paste.ranges[0] == paste.ranges[1]:
                range_str = paste.ranges[0]
            else:
                range_str = f"{paste.ranges[0]}-{paste.ranges[1]}"
            paste_format = f"!paste {paste.book_obj.name} - {range_str} {paste.full_url}"
            send_tasks.append(asyncio.create_task(paste_channel.send(paste_format)))
        await asyncio.gather(*send_tasks)

    @bot_checks.check_permission_level(5)
    @commands.command(aliases=['stat', 'status'])
    async def stats(self, ctx: Context):
        if self.last_ping == 0:
            last_ping_str = 'never'
        else:
            last_ping_timestamp = datetime.datetime.fromtimestamp(self.last_ping)
            difference_str = str(datetime.datetime.now() - last_ping_timestamp)
            last_ping_str = difference_str[:difference_str.find('.')]  # might change to only return seconds instead of
            # this format
            if last_ping_str == '0:00:00':
                last_ping_str = '0:00:01'

        bot_uptime_str = str(datetime.datetime.now() - self.bot.uptime)
        bot_uptime = bot_uptime_str[:bot_uptime_str.find('.')]

        accounts_count, fp_count = await self.db.retrieve_account_stats()
        background_process_status_bool = self.background_process_interface.is_alive()
        if background_process_status_bool:
            background_process_status = "Alive"
        else:
            background_process_status = "Dead"

        embed = bot_utils.generate_embed('Bot Stats', ctx.author, ('Last Background Ping', last_ping_str),
                                         ('Background Process', background_process_status),
                                         ('Accounts', f"{accounts_count[0]}/{accounts_count[1]}"),
                                         ('Fp Left', fp_count), ('Bot Uptime', bot_uptime))
        await ctx.send(embed=embed)

    @commands.command()
    async def services_stats(self, ctx: Context):
        reports = await self.background_process_interface.request_all_services_status()
        services_reports = reports.services
        # actual_time = time.time()
        fields = []
        for service_report in services_reports:
            last_execution = service_report.service_last_execution
            if last_execution == 0:
                last_execution_str = 'Never'
            elif last_execution == 1:
                last_execution_str = 'Started but never finished'
            else:
                time_difference = datetime.datetime.now() - datetime.datetime.fromtimestamp(last_execution)
                last_execution_str = f'{time_difference.total_seconds():.3f} secs ago'
            fields.append((f"{service_report.service_id}: {service_report.service_name}",
                           f"Last Execution: {last_execution_str}"))

        embed = bot_utils.generate_embed('Services Status', ctx.author, *fields)
        await ctx.send(embed=embed)

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

    # TODO to be deleted after alpha
    @commands.command()
    @bot_checks.check_permission_level(10)
    async def test_m(self, ctx: Context):
        print('trying to retrieve buyer account')
        # account = await self.db.retrieve_buyer_account()
        # print(True)
        await self.db.release_accounts_over_five_in_use_minutes()
        print('released extra accounts')

    @commands.command()
    async def ping(self, ctx: Context):
        await ctx.send('Ping!')


def setup(bot):
    cog = BackgroundManager(bot)
    bot.add_cog(cog)
