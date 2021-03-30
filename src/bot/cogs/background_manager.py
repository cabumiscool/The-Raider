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
    async def queue_status(self, ctx: Context):
        queue_history_stats = await self.background_process_interface.request_queue_status()
        await ctx.send("emmbed pending to be made by dev")
        await ctx.send("printing queue content instead")
        for book_status in queue_history_stats.books_status_list:
            book_status: BookStatus
            stages = []
            for stage_name, quantity in book_status.chapters_status_dict.items():
                if quantity > 0:
                    stages.append(f"{stage_name}: {quantity}")
            await ctx.send(f"{book_status.base_obj.name}\n"
                           f"Chapters at queue: {len(book_status.chapters)}\n")
            if len(stages) > 0:
                await ctx.send(f"Chapters stage status:  \n%s" % '\n'.join(stages))

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
