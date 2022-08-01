from typing import Union

import aiohttp
import time


import discord
from discord.ext import commands
from discord.ext.commands import Context

from asyncpg.exceptions import ForeignKeyViolationError, UniqueViolationError

from bot.bot_utils import text_response_waiter
from bot import bot_exceptions
from dependencies.database.database import Database
from dependencies.webnovel.web.auth import check_code, send_trust_email, check_trust
from dependencies.database.database_exceptions import DatabaseDuplicateEntry
from dependencies.webnovel.classes import QiAccount
from . import bot_checks


# It adds a new account to the database
class ExternalAccounts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db
        self.captcha_block = 0

    @commands.command()
    async def add_account(self, ctx: Context):
        """
        It adds a new account to the database.
        
        :param ctx: Context
        :type ctx: Context
        :return: a coroutine object.
        """
        message = await ctx.send("Respond to this message with the email of the qi account you wish to add, to abort "
                                 "you can ignore this message")
        response = await text_response_waiter(ctx, message, 120)
        email_response: str = response.clean_content
        if email_response.find("@") == -1:
            await ctx.send("Couldn't verify the given email as a valid email! Please try again!!")
            return
        message = await ctx.send("Respond to this message with the password to the account, remember to **delete**"
                                 " your response!!")
        response = await text_response_waiter(ctx, message, 120)
        password: str = response.clean_content
        message = await ctx.send("Are you sure the details you inserted are correct? Please reply **yes** to confirm")
        response = await text_response_waiter(ctx, message, 120)
        if response.clean_content.lower() != 'yes':
            await ctx.send("Aborting!!")
        await ctx.send("Continuing!")
        # A function that adds a new account to the database.
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.webnovel.com/") as req:
                await req.read()
            response, ticket = await check_code(session, '', email_response, password)
            if response['code'] == 11313:
                await ctx.send("Either the email or password is wrong!! Aborting!! Please try again.")
                return
            if response['code'] == 11318:
                await ctx.send("Email verification required!!! Sending email!")
                encry_param = response['encry']
                await send_trust_email(session, ticket, encry_param)
                while True:
                    message = await ctx.send("Email sent! Please reply to this message with the code!")
                    response_code = await text_response_waiter(ctx, message, 300)
                    message = await ctx.send(f"Is the code `{response_code.clean_content}` correct? Please respond "
                                             f"with **yes** to this message, in case it is wrong respond "
                                             f"with anything else to retry.")
                    response_confirmation = await text_response_waiter(ctx, message, 120)
                    if response_confirmation.clean_content.lower() == 'yes':
                        break
                    else:
                        await ctx.send("Restarting operation!!\n------------")
                response, ticket = await check_trust(session, ticket, encry_param, response_code.clean_content)
                if response['code'] == 11319:
                    await ctx.send("Wrong verification code!!! PLease try again! Aborting!!")
                    return

            if response['code'] == 11104:
                response, ticket = await check_code(session, ticket, email_response, password)

            if response['code'] == 11401:
                # print('Captcha block!')
                self.captcha_block = time.time()
                await ctx.send("We hit the captcha!! Please try in 1 hour for the cd of the catha to end!")
                return
                # TODO raise Exception(f"Captcha blocked at {int(time.time())}")

            if response['code'] == 0:
                cookies_dict = {}
                for cookie in session.cookie_jar:
                    cookie_key = cookie.key
                    cookie_value = cookie.value
                    cookies_dict[cookie_key] = cookie_value
                account_obj = QiAccount(-1, email_response, password, cookies_dict, ticket, False, 0, 0, 0, 0, 10,
                                        cookies_dict['uid'], False)
                await account_obj.async_check_valid()
                await self.db.insert_quest_account(account_obj, ctx.author.id)
                await ctx.send("Account added succesfully!")




    @commands.command()
    async def list_accounts(self, ctx: Context, *args):    #command scheme/expected ctx: !list_accounts [optional: discord_id]
        """
        command scheme: !list_accounts [optional: discord_id]\n
        may need refining in terms of async and format of account ID is unclear (is it <@1243252345> or just 1241235421)
        """
        discord_id = int(args[0]) if args else ctx.author.id
        accounts = self.db.retrieve_all_accounts_from_discord_id(discord_id)
        if accounts == []:
            await ctx.send("Seems like this discord account does not have any webnovel accounts registered!")
        else:
            accounts_str = await "\n".join(accounts)
            await ctx.send(f"Your accounts are:\n```{accounts_str}```")

    @commands.command()
    async def remove_account(self, ctx: Context, mail:str) -> None:
        """
        It removes an account from the database.
        
        :param ctx: Context
        :type ctx: Context
        :return: a coroutine object.
        """
        await self.db.remove_quest_account(mail)
        ctx.send("Account has been removed!")

    @commands.command()
    async def fix_account(self, ctx: Context):
        pass


def setup(bot):
    cog = ExternalAccounts(bot)
    bot.add_cog(cog)
