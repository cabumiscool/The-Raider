import discord
from discord.ext import commands
from discord.ext.commands import Context
from bot import bot_exceptions

from typing import Union

from dependencies import utils
from dependencies.database import Database
from . import checks


class PermissionManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error):
        print(error, type(error))
        if isinstance(error, bot_exceptions.NotImplementedFunction):
            await ctx.send(f"What you are attempting to do isn't implemented by the lazy devs 😱 | error: {error}")
        elif isinstance(error, bot_exceptions.NotEnoughPerms):
            await ctx.send(f"Who told you that you could do that? | error:  {error}")

    @commands.command()
    @checks.check_permission_level(2)
    async def check_permissions(self, ctx: Context, user: Union[int, str]):
        try:
            user_id = utils.look_for_user_id(user)
        except NotImplementedError:
            raise bot_exceptions.NotImplementedFunction('Mentions still not supported')
        if user_id is None:
            await ctx.send(f'I could not understand what that, did you type a user id or a mention? '
                           f'{ctx.author.mention}?')
            return
        user_obj: discord.guild.Member = ctx.guild.get_member(user_id)
        ids = [user_obj.id, *[role.id for role in user_obj.roles]]
        permission_level, permission_name = await self.db.permission_retriever(*ids, with_name=True)
        await ctx.send(f'Permission level for {user_obj.display_name}:   {permission_level} ({permission_name})')

    @commands.command(aliases=['authorized_users', 'super_users', 'su'])
    @checks.check_permission_level(8)
    async def list_authorized_users(self, ctx: Context):
        users = []
        result_dict = await self.db.auth_retriever()
        for user_dict in result_dict:
            user_obj = ctx.guild.get_member(user_dict['id'])
            if user_obj is None:
                user_obj = user_dict['id']
            users.append({'user': (str(user_obj)), 'level': f'Level:  {user_dict["level"]} ({user_dict["nick"]})'})
        await ctx.send('\n'.join((str(user) for user in users)))

    @commands.command()
    @checks.check_permission_level(8)
    async def authorize_user(self, ctx: Context, user: Union[int, str], level: int):
        if level > 10:
            await ctx.send('You are attempting to give a permission higher than the max. Do you want to usurp the '
                           'god\'s power?')
        try:
            user_id = utils.look_for_user_id(user)
        except NotImplementedError:
            raise bot_exceptions.NotImplementedFunction('Mentions not supported')
        if user_id is None:
            await ctx.send("I couldn't understand what you said, did you type a user id or mention?")
            return
        user_obj: discord.guild.Member = ctx.guild.get_member(user_id)
        if user_obj is None:
            await ctx.send("I couldn't find anyone matching that user id 😦")
            return

        # TODO add a check to see if the recipient user has a lower permission than self

        await self.db.auth_adder(user_id, level)
        await ctx.send(f'Successfully authorized {user_obj.mention} to clearance level {level}')
        return






def setup(bot):
    cog = PermissionManagement(bot)
    bot.add_cog(cog)
