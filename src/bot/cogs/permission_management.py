import discord
from discord.ext import commands
from discord.ext.commands import Context
from bot import bot_exceptions

from typing import Union

from dependencies import utils
from dependencies.database import Database
from . import bot_checks


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
    @bot_checks.check_permission_level(2)
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
    @bot_checks.check_permission_level(8)
    async def list_authorized(self, ctx: Context):
        users = []
        result_dict = await self.db.auth_retriever(include_roles=True)
        for item_dict in result_dict:
            if item_dict['role'] is False:
                item_obj = ctx.guild.get_member(item_dict['id'])
            else:
                item_obj: discord.guild.Guild = ctx.guild.get_role(item_dict['id'])
            if item_obj is None:
                item_obj = item_dict['id']

            # TODO streamline this
            users.append({'name': (str(item_obj)), 'level': f'Level:  {item_dict["level"]} ({item_dict["nick"]})',
                          'role': item_dict['role']})
        await ctx.send('\n'.join((str(user) for user in users)))

    @commands.command()
    @bot_checks.check_permission_level(6)
    async def authorize(self, ctx: Context, item: Union[discord.member.User, discord.guild.Role], level: int):
        db = self.db
        role = False
        if level > 10:
            await ctx.send('You are attempting to give a permission higher than the max. Do you want to usurp the '
                           'god\'s power?')
            return
        if isinstance(item, discord.role.Role):
            item_id = item.id
            role = True
        else:
            item_id = item.id

        # Level checker between target and self
        self_author: discord.Member = ctx.author
        self_level = await db.permission_retriever(*[self_author.id, *[role.id for role in self_author.roles]])
        target_level: Union[None, int] = await db.permission_retriever(item_id)
        if target_level is None:
            await db.auth_adder(item_id, level, role)
            await ctx.send(f'Successfully authorized `{item.name}` to clearance level {level}')
        if target_level == level:
            await ctx.send('The target already has that clearance level!')
            return
        else:
            if target_level >= self_level and self_level != 10:
                await ctx.send('You do know you are attempting to commit insubordination right? (target has a '
                               'higher or equal clearance level)')
            else:
                await db.auth_changer(item_id, level)
                await ctx.send(f"successfully changed `{item.name}` clearance level from {target_level} to {level}")
        return

    @commands.command()
    @bot_checks.check_permission_level(8)
    async def test(self, ctx: Context, mention: Union[discord.member.User, discord.guild.Role]):
        await ctx.send(f"mention is :  {mention},  type:  {type(mention)}")






def setup(bot):
    cog = PermissionManagement(bot)
    bot.add_cog(cog)
