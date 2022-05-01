import datetime
import sys
import traceback
from collections import deque, defaultdict

import aiohttp
import discord
from discord.ext import commands

from config import ConfigReader
from dependencies.database import Database
from dependencies.exceptions import RaiderBaseException

initial_extensions = ('bot.cogs.permission_management',
    """
    Takes any number of arguments and returns a function that takes two arguments and returns a list
    of strings.
    """
                      'bot.cogs.qi_commands',
                      'bot.cogs.background_manager',
                      'bot.cogs.migration_cog',
                      'bot.cogs.chapter_pings_cog',
                      'bot.cogs.external_accounts')


def _custom_prefix_adder(*args):
    """
    Takes any number of arguments and returns a function that takes two arguments and returns a list
    of strings which will be used as command prefixes
    :return: A function that returns a list of strings.
    """
    def _prefix_callable(bot, msg):
        """returns a list of strings which will be used as command prefixes"""
        user_id = bot.user.id
        base = [f'<@!{user_id}> ', f'<@{user_id}> ']
        base.extend(args)
        return base

    return _prefix_callable


# A bot that uses the discord.py library to connect to discord and do stuff.
class Raider(commands.AutoShardedBot):
    def __init__(self):
        """
        A constructor for the bot class, it reads the config file, sets the bot's prefix,
        description, token, and other stuff
        """
        self.config = ConfigReader()
        super().__init__(command_prefix=_custom_prefix_adder(self.config.bot_prefix),
                         description=self.config.bot_description, pm_help=None, help_attrs=dict(hidden=True),
                         fetch_offline_members=False, heartbeat_timeout=150.0,
                         help_command=commands.DefaultHelpCommand(dm_help=True, width=120))
        self.bot_token = self.config.bot_token
        self.db = Database(self.config.db_host, self.config.db_name, self.config.db_user, self.config.db_password,
                           self.config.db_port, self.config.min_db_conns, self.config.max_db_conns, loop=self.loop)

        self.uptime: datetime.datetime = datetime.datetime.now()

        # TODO change implementation to a non deprecated form, unknown if possible
        self.session = aiohttp.ClientSession(loop=self.loop)

        self._prev_events = deque(maxlen=10)

        # shard_id: List[datetime.datetime]
        # shows the last attempted IDENTIFYs and RESUMEs
        self.resumes = defaultdict(list)
        self.identifies = defaultdict(list)  # TODO check if it is still used

        # Cogs loader
        for extension in initial_extensions:
            try:
                self.load_extension(extension)
            except Exception as e:
                print(f'failed to load extension because of:  {e}, type:  {type(e)}')
                traceback.print_exc()
                # TODO probably log it

    def _clear_gateway_data(self):
        """
        Removes the data from the identifies and resumes dictionaries that are older than a week
        """
        one_week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        for shard_id, dates in self.identifies.items():
            to_remove = [index for index, dt in enumerate(dates) if dt < one_week_ago]
            for index in reversed(to_remove):
                del dates[index]

        # checks resume instead of identifies
        for shard_id, dates in self.resumes.items():
            to_remove = [index for index, dt in enumerate(dates) if dt < one_week_ago]
            for index in reversed(to_remove):
                del dates[index]

    async def on_socket_response(self, msg):
        self._prev_events.append(msg)

    async def before_identify_hook(self, shard_id, *, initial=False):
        """
        Clears the gateway data and then appends the current time to the identifies list
        
        :param shard_id: The shard ID that is being identified
        :param initial: Whether this is the first identify for this shard, defaults to False (optional)
        """
        self._clear_gateway_data()
        self.identifies[shard_id].append(datetime.datetime.utcnow())
        await super().before_identify_hook(shard_id, initial=initial)

    async def on_command_error(self, ctx, error):
        """
        If an error occurs, it will send a message to the user
        
        :param ctx: Context
        :param error: The error that was raised
        """
        if isinstance(error, commands.DisabledCommand):
            await ctx.send('Sorry. This command is disabled and cannot be used.')
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send('This command cannot be used in private messages.')
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('You are missing required arguments in the command. :frowning:')
        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            if isinstance(original, RaiderBaseException):
                await ctx.send(f"An error occurred. Error: {original.get_message()}")
            if not isinstance(original, discord.HTTPException):
                print(f'In {ctx.command.qualified_name}:', file=sys.stderr)
                traceback.print_tb(original.__traceback__)
                print(f'{original.__class__.__name__}: {original}', file=sys.stderr)
                await ctx.send(f"What you are trying to do caused a error, whip the devs to fix it 😈 ```{error}```")
        elif isinstance(error, commands.ArgumentParsingError):
            await ctx.send(error)

    # TODO check if this is needed
    def get_guild_prefixes(self, guild, *, local_inject=_custom_prefix_adder()):
        """
        Returns a list of prefixes for a given guild
        
        :param guild: The guild to get the prefixes for
        :param local_inject: This is a function that will be called to inject custom prefixes into the
        prefixes list
        :return: The return value is a list of prefixes.
        """
        proxy_msg = discord.Object(id=0)
        proxy_msg.guild = guild
        return local_inject(self, proxy_msg)

    # Unknown if needed
    # def get_raw_guild_prefixes(self, guild_id):
    #     return self.prefixes.get(guild_id, ['?', '!'])
    #
    # async def set_guild_prefixes(self, guild, prefixes):
    #     if len(prefixes) == 0:
    #         await self.prefixes.put(guild.id, [])
    #     elif len(prefixes) > 10:
    #         raise RuntimeError('Cannot have more than 10 custom prefixes.')
    #     else:
    #         await self.prefixes.put(guild.id, sorted(set(prefixes), reverse=True))

    async def on_ready(self):
        """
        When the bot is ready, print the bot's name and ID to the console.
        """
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()

        print(f'Ready: {self.user} (ID: {self.user.id})')

    async def on_shard_resumed(self, shard_id):
        """
        When a shard resumes, it will print a message in the console and add the time it resumed to the
        resumes dictionary
        
        :param shard_id: The ID of the shard that has resumed
        """
        print(f'Shard ID {shard_id} has resumed...')
        self.resumes[shard_id].append(datetime.datetime.utcnow())

    @property
    def stats_webhook(self):
        """
        Returns a webhook object that can be used to send messages to a webhook
        :return: The webhook object.
        """
        wh_id, wh_token = self.config.stat_webhook
        hook = discord.Webhook.partial(id=wh_id, token=wh_token, adapter=discord.AsyncWebhookAdapter(self.session))
        return hook

    #  can be used in case more precise control wants to be used
    ####
    # async def process_commands(self, message):
    #     ctx = await self.get_context(message)
    #
    #     if ctx.command is None:
    #         return
    #
    #     # if ctx.author.id in self.blacklist:
    #     #     return
    #
    #     # if ctx.guild is not None and ctx.guild.id in self.blacklist:
    #     #     return
    #
    #     bucket = self.spam_control.get_bucket(message)
    #     current = message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp()
    #     retry_after = bucket.update_rate_limit(current)
    #     author_id = message.author.id
    #     if retry_after and author_id != self.owner_id:
    #         self._auto_spam_count[author_id] += 1
    #         if self._auto_spam_count[author_id] >= 5:
    #             await self.add_to_blacklist(author_id)
    #             del self._auto_spam_count[author_id]
    #             await self.log_spammer(ctx, message, retry_after, autoblock=True)
    #         else:
    #             self.log_spammer(ctx, message, retry_after)
    #         return
    #     else:
    #         self._auto_spam_count.pop(author_id, None)
    #
    #     try:
    #         await self.invoke(ctx)
    #     finally:
    #         # Just in case we have any outstanding DB connections
    #         await ctx.release()

    async def invoke(self, ctx):
        """|coro|

        Overridden function to add emotes during the start and the end of commands.

        Invokes the command given under the invocation context and
        handles all the internal event dispatch mechanisms.

        Parameters
        -----------
        ctx: :class:`.Context`
            The invocation context to invoke.
        """
        if ctx.command is not None:
            self.dispatch('command', ctx)
            try:
                if await self.can_run(ctx, call_once=True):
                    await ctx.message.add_reaction('🧐')
                    await ctx.command.invoke(ctx)
                    await ctx.message.add_reaction('😀')
                else:
                    raise commands.CheckFailure('The global check once functions failed.')
            except commands.CommandError as exc:
                await ctx.command.dispatch_error(ctx, exc)
                await ctx.message.add_reaction('🔥')
            else:
                self.dispatch('command_completion', ctx)
            finally:
                await ctx.message.remove_reaction('🧐', self.user)
        elif ctx.invoked_with:
            exc = commands.CommandNotFound('Command "{}" is not found'.format(ctx.invoked_with))
            self.dispatch('command_error', ctx, exc)

    async def process_commands(self, message):
        """
        If the message author is a bot, and the bot is not the bot that the code is running on, then
        return. If the message author is not a bot, then run the command
        
        :param message: The message that was sent
        :return: The return value of the command being invoked.
        """
        if message.author.bot:
            if message.author.id not in [626487260031746050]:
                return

        ctx = await self.get_context(message)
        await self.invoke(ctx)

    async def close(self):
        """
        The function closes the connection to the database and closes the session
        """
        await super().close()
        await self.session.close()

    # probably won't be manually implemented
    def run(self):
        try:
            super().run(self.config.bot_token, reconnect=True)
        except Exception as e:
            print(f"Error at startup!  error: {e},  type:  {type(e)}")
