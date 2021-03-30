import discord
from discord.ext import commands
from discord.ext.commands import Context

from bot import bot_exceptions
from dependencies.database.database import Database


def has_attachment(attachment_len: int = 1):
    if attachment_len <= 0:
        raise Exception("Invalid attachment requirement")

    async def check(ctx: Context):
        message = ctx.message
        if len(message.attachments) == 0:
            raise bot_exceptions.AttachmentNumberMismatch("This message is missing an attachment")
        elif len(message.attachments) > attachment_len:
            raise bot_exceptions.AttachmentNumberMismatch("This message has too many attachments")
        else:
            return True

    return commands.check(check)


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
        raise bot_exceptions.NotOnWhiteList

    return commands.check(check)
