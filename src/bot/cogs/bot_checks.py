from dependencies.database import Database
from discord.ext import commands
from discord.ext.commands import Context
import discord
from bot import bot_exceptions


def check_permission_level(required_level: int = 0):
    async def check(ctx: Context):
        bot = ctx.bot
        db: Database = bot.db
        author: discord.Member = ctx.author
        ids = [author.id, *[role.id for role in author.roles]]
        perm = await db.permission_retriever(*ids)
        if perm is None:
            perm = 0
        if perm > required_level:
            return True
        else:
            raise bot_exceptions.NotEnoughPerms(f"{ctx.author} does not have enough permission to run the command")
    return commands.check(check)

