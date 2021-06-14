import asyncio
import time

import aiohttp

from dependencies.database import Database
from dependencies.email_agent import MailAgent
from dependencies.webnovel.web import auth
from .base_service import BaseService


class CookieMaintainerService(BaseService):
    def __init__(self, database: Database):
        super().__init__(name="Cookie Maintainer Service", output_service=False)
        self.db = database
        self.captcha_block = 0

    async def main(self):
        expired_account = await self.db.retrieve_expired_account()
        if expired_account is None:
            return

        host_index = expired_account.host_email_id

        email_account = await self.db.retrieve_email_obj(id_=host_index)
        mail_agent = MailAgent(email_account.email, email_account.password)
        await mail_agent.initialize()

        async with aiohttp.ClientSession(cookies=expired_account.cookies) as session:
            try:
                response, ticket = await auth.check_status(expired_account.ticket, session)

                if response['code'] != 0:
                    response, ticket = await auth.check_code(session, ticket, expired_account.email,
                                                             expired_account.password)

                    if response['code'] == 11318:
                        encry_param = response['encry']
                        response = await auth.send_trust_email(session, ticket, encry_param)
                        await asyncio.sleep(55)
                        keycode = await mail_agent.get_keycode_by_recipient(expired_account.email)

                        response, ticket = await auth.check_trust(session, ticket, encry_param, keycode)
                        expired_account.ticket = ticket

                    elif response['code'] == 11401:
                        print('Captcha block!')
                        self.captcha_block = time.time()
                        raise Exception(f"Captcha blocked at {int(time.time())}")

                response_code = response['code']
                if response_code == 0:
                    expired_account.expired = False
                    update_db_flg = True

                elif response_code == -51018:
                    # Invoke ticket error. Updating Cookies and redoing request seems to clear it
                    update_db_flg = True

                else:
                    raise Exception(f'Unknown Response for {expired_account.email}! Response_code: {response["code"]}.'
                                    f'\nResponse:{response}')

                if update_db_flg is True:
                    cookies_dict = {}
                    for cookie in session.cookie_jar:
                        cookie_key = cookie.key
                        cookie_value = cookie.value
                        cookies_dict[cookie_key] = cookie_value
                    expired_account.cookies = cookies_dict
                    await self.db.update_account_params(expired_account)

            except Exception as e:
                await self.db.update_account_params(expired_account)
                raise e

    async def inner_loop_manager(self):
        while True:
            if time.time() - self.captcha_block < 3600:
                self.last_loop = -10
                await asyncio.sleep(self._loop_interval)
            else:
                await self.inner_error_handler()
                self.last_loop = time.time()
                await asyncio.sleep(self._loop_interval)
