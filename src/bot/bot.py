import asyncio
import aiohttp

import discord
from discord.ext import commands

from collections import Counter, deque, defaultdict

from config import Settings


initial_extensions = ()


def _custom_prefix_adder(*args):
    def _prefix_callable(bot, msg):
        """returns a list of strings which will be used as command prefixes"""
        user_id = bot.user.id
        base = [f'<@!{user_id}> ', f'<@{user_id}> ']
        base.extend(args)
        return base
    return _prefix_callable


class Raider(commands.AutoShardedBot):
    def __init__(self):
        self.configs = Settings()
        super().__init__(command_prefix=_custom_prefix_adder(self.configs.bot_prefix),
                         description=self.configs.bot_description, pm_help=None, help_attrs=dict(hidden=True),
                         fetch_offline_members=False, heartbeat_timeout=150.0)
        self.bot_token = self.configs.bot_token

        # TODO change implementation to a non deprecated form, unknown if possible
        self.session = aiohttp.ClientSession(loop=self.loop)

        self._prev_events = deque(maxlen=10)

        # shard_id: List[datetime.datetime]
        # shows the last attempted IDENTIFYs and RESUMEs
        self.resumes = defaultdict(list)
        self.identifies = defaultdict(list)



