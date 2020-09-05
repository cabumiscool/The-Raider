import discord
from discord.ext import commands
from discord.ext.commands import Context

from bot import bot_exceptions
from dependencies.database import Database


def check_permission_level(required_level: int = 0):
    async def check(ctx: Context):
        bot = ctx.bot
        db: Database = bot.db
        author: discord.Member = ctx.author
        is_god: bool = await ctx.bot.is_owner(ctx.author) or ctx.author.id in [479487273432514560, 339050854453608459]
        ids = [author.id, *[role.id for role in author.roles]]
        perm = await db.permission_retriever(*ids)
        if perm is None:
            perm = 0
        if perm > required_level or is_god:
            return True
        else:
            raise bot_exceptions.NotEnoughPerms(f"{ctx.author} does not have enough permission to run the command")

    return commands.check(check)


def is_whitelist():
    async def check(ctx: Context):
        db: Database = ctx.bot.db
        channel_id: int = ctx.channel.id
        server_id: int = ctx.guild.id
        check_ = await db.whitelist_check(server_id, channel_id)
        if check_:
            return check_
        else:
            raise bot_exceptions.NotOnWhiteList

    return commands.check(check)
