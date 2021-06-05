import datetime
import asyncio
# from json import loads
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

# from dependencies.webnovel.classes import QiAccount
# from dependencies.proxy_classes import Proxy

valid_service_commands = {'restart': BackgroundProcessInterface.restart_service,
                          'stop': BackgroundProcessInterface.stop_service,
                          'start': BackgroundProcessInterface.start_service}


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
        self.services_names = {}
        self.services_ids = []

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
            error_string = f'Error occurred, Comment: {error.comment} | Error: {error.error} | ' \
                           f'Error type:  {type(error)} '
            error_traceback = f'Traceback: {error.traceback}'
            if len(error_string) + 3 + len(error_traceback) >= 2000:
                error_string = ''.join(('```', error_string, 'Traceback appended as the file below', '```'))
                traceback_file = discord.File(StringIO(error_traceback), 'error_traceback.txt')
                async_tasks.append(asyncio.create_task(error_channel.send(error_string, file=traceback_file)))
            else:
                error_string = '|'.join((error_string, error_traceback))
                error_string = ''.join(('```', error_string, '```'))
                async_tasks.append(asyncio.create_task(error_channel.send(error_string)))
        await asyncio.gather(*async_tasks)

    @tasks.loop(seconds=3)
    async def pastes_retriever(self):
        try:
            default_paste_channel: discord.TextChannel = await self.bot.fetch_channel(827393945796870184)

            translated_paste_channel_id = await self.db.channel_type_retriever(1)
            if translated_paste_channel_id is None:
                translated_paste_channel = default_paste_channel
            else:
                translated_paste_channel: discord.TextChannel = await self.bot.fetch_channel(translated_paste_channel_id)

            original_paste_channel_id = await self.db.channel_type_retriever(2)
            if original_paste_channel_id is None:
                original_paste_channel = default_paste_channel
            else:
                original_paste_channel: discord.TextChannel = await self.bot.fetch_channel(original_paste_channel_id)

            pastes = self.background_process_interface.return_all_pastes()
            send_tasks = []
            for paste in pastes:
                if paste.ranges[0] == paste.ranges[1]:
                    range_str = paste.ranges[0]
                else:
                    range_str = f"{paste.ranges[0]}-{paste.ranges[1]}"
                paste_format = f"!paste {paste.book_obj.name} - {range_str} <{paste.full_url}>"
                if paste.book_obj.book_type_num == 1:
                    send_tasks.append(asyncio.create_task(translated_paste_channel.send(paste_format)))
                elif paste.book_obj.book_type_num == 2:
                    send_tasks.append(asyncio.create_task(original_paste_channel.send(paste_format)))

            await asyncio.gather(*send_tasks)
        except Exception as e:
            print(f"Critical error at the paste retriever!!:   {e} | type:  {type(e)}")
            raise e

    @bot_checks.check_permission_level(5)
    @commands.command(aliases=['stat', 'status'],
                      brief='Retrieves the status of the bot')
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
                                         ('Fp Left', fp_count), ('Bot Uptime', bot_uptime),
                                         ('Background Process', background_process_status),
                                         ('Accounts', f"{accounts_count[0]}/{accounts_count[1]}"),)
        await ctx.send(embed=embed)

    def inner_services_cache_updater(self, services_status_object: AllServicesStatus):
        for service in services_status_object.services:
            self.services_ids.append(service.service_id)
            self.services_names[service.service_name] = service.service_id

    @bot_checks.check_permission_level(5)
    @commands.command(brief='Retrieves the operating status of the background services')
    async def services_stats(self, ctx: Context):
        reports = await self.background_process_interface.request_all_services_status()
        self.inner_services_cache_updater(reports)
        services_reports = reports.services
        # actual_time = time.time()
        fields = []
        for service_report in services_reports:
            last_execution = service_report.service_last_execution
            if last_execution == 0:
                last_execution_str = 'Never'
            elif last_execution == 1:
                last_execution_str = 'Started but never finished'
            elif last_execution == -1:
                last_execution_str = 'Service was stopped'
            elif last_execution == -10:
                last_execution_str = 'Captcha cool down was hit.... resting'
            else:
                time_difference = datetime.datetime.now() - datetime.datetime.fromtimestamp(last_execution)
                last_execution_str = f'{time_difference.total_seconds():.3f} secs ago'
            fields.append((f"{service_report.service_id}: {service_report.service_name}",
                           f"Last Execution: {last_execution_str}"))

        embed = bot_utils.generate_embed('Services Status', ctx.author, *fields)
        await ctx.send(embed=embed)

    @bot_checks.check_permission_level(6)
    @commands.command(brief='Will retrieve the contents of the background queue WIP')
    async def queue_status(self, ctx: Context):
        queue_history_stats = await self.background_process_interface.request_queue_status()
        await ctx.send("embed pending to be made by dev")
        await ctx.send("printing queue content instead")
        await ctx.send(f"{len(queue_history_stats.books_status_list)} books on the background queue.... contents: ")

        books_messages = []
        for book_status in queue_history_stats.books_status_list:
            book_message = []
            book_status: BookStatus
            stages = []
            for stage_name, quantity in book_status.chapters_status_dict.items():
                if quantity > 0:
                    stages.append(f"{stage_name}: {quantity}")
            book_message.append(f"{book_status.base_obj.name}\nChapters at queue: {len(book_status.chapters)}")
            if len(stages) > 0:
                book_message.append(f"Chapters stage status:  \n%s\n" % '\n'.join(stages))

            books_messages.append('\n'.join(book_message))

        completed_messages = []
        to_join = []
        chars_count = 0
        for book_message in books_messages:
            if len(book_message) + chars_count + 1 < 2000:
                to_join.append(book_message)
                chars_count += len(book_message) + 1
            else:
                completed_messages.append('\n'.join(to_join))
                to_join.clear()
                chars_count = 0

        if len(to_join) != 0:
            completed_messages.append('\n'.join(to_join))

        async_tasks = []
        for completed_message in completed_messages:
            async_tasks.append(asyncio.create_task(ctx.send(completed_message)))

        await asyncio.gather(*async_tasks)
        await ctx.send('finished printing queue')

    @bot_checks.check_permission_level(6)
    @commands.command(brief='Will force the background process to update the db with the data available in the '
                            'background without waiting')
    async def force_queue_update(self, ctx: Context):
        await ctx.send("Are you sure you want to force the background queue to update its value? This will cause any "
                       "ongoing buy to be cancelled and ignored afterwards. (Please confirm in 60 seconds....)")
        await ctx.send("Check pending to be written..... Please ping cabum to stop lazing around.. moving on with the "
                       "process")
        try:
            response_object = await self.background_process_interface.force_queue_update()
        except TimeoutError:
            await ctx.send("Timeout Error!! The response to the queue update was never received....")
            return
        if response_object.command_status == 0:
            await ctx.send(f"Unknown failed execution of {ctx.command} ran by {ctx.author} with the comment"
                           f" of {response_object.text_status}")
        elif response_object.command_status == 1:
            await ctx.send(f"The command {ctx.command} ran by {ctx.author} failed to be executed")
        else:
            await ctx.send(f"The command {ctx.command} ran by {ctx.author} was successfully executed, queue updated.")

    @bot_checks.check_permission_level(6)
    @commands.command(brief='Manages multiple service management operations',
                      help='Manages the manual start, stop, and restart of any background service')
    async def service(self, ctx: Context, operation: str, name_or_id: typing.Union[int, str]):
        await ctx.send("attempting operation")
        operation_lower_case = operation.lower()
        # if operation_lower_case not in valid_service_commands:
        #     await ctx.send(f"The requested operation is an invalid one")
        if operation_lower_case not in ['restart', 'stop', 'start']:
            await ctx.send(f"The requested operation is an invalid one")
            return

        if len(self.services_ids) == 0 or name_or_id not in self.services_names and name_or_id not in self.services_ids:
            services_status = await self.background_process_interface.request_all_services_status()
            self.inner_services_cache_updater(services_status)

        if name_or_id not in self.services_names and name_or_id not in self.services_ids:
            await ctx.send(f"The service that was attempted to be {operation} couldn't be found")
            return

        if name_or_id in self.services_names:
            service_id = self.services_names[name_or_id]
        else:
            service_id = name_or_id

        if operation_lower_case == 'stop':
            response_obj = await self.background_process_interface.stop_service(service_id)
        elif operation_lower_case == 'start':
            response_obj = await self.background_process_interface.start_service(service_id)
        else:
            response_obj = await self.background_process_interface.restart_service(service_id)

        if response_obj.command_status == 0:
            # unknown
            await ctx.send(f"The command service {operation} executed by {ctx.author} failed to execute | comment:  "
                           f"{response_obj.text_status}")
        elif response_obj.command_status == 1:
            # failed
            await ctx.send(f"The command service {operation} executed by {ctx.author} failed to be executed")
        else:
            # successful
            await ctx.send(f"The command service {operation} executed by {ctx.author} was successfully executed")

    # TODO to be deleted after alpha
    @commands.command(hidden=True)
    @bot_checks.check_permission_level(10)
    async def test_m(self, ctx: Context):
        print('trying to retrieve buyer account')
        # account = await self.db.retrieve_buyer_account()
        # print(True)
        await self.db.release_accounts_over_five_in_use_minutes()
        print('released extra accounts')

    @commands.command(hidden=True)
    async def ping(self, ctx: Context):
        await ctx.send('Ping!')


def setup(bot):
    cog = BackgroundManager(bot)
    bot.add_cog(cog)
