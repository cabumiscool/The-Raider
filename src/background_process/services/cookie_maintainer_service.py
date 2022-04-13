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
        expired_acc = await self.db.retrieve_expired_account()
        if expired_acc is None:
            return

        async with aiohttp.ClientSession(cookies=expired_acc.cookies) as session:
            try:
                response, ticket = await auth.check_status(expired_acc.ticket, session)

                if response['code'] != 0:
                    response, ticket = await auth.check_code(session, ticket, expired_acc.email, expired_acc.password)

                if response['code'] == 11318:
                    if expired_acc.owned is False:
                        await self.db.mark_account_with_keycode_problem(expired_acc.guid)
                        return
                    host_index = expired_acc.host_email_id
                    email_account = await self.db.retrieve_email_obj(id_=host_index)
                    mail_agent = MailAgent(email_account.email, email_account.password)
                    await mail_agent.initialize()

                    encry_param = response['encry']
                    response = await auth.send_trust_email(session, ticket, encry_param)
                    await asyncio.sleep(45)
                    keycode = await mail_agent.get_keycode_by_recipient(expired_acc.email)

                    response, ticket = await auth.check_trust(session, ticket, encry_param, keycode)

                if response['code'] == 11401:
                    print('Captcha block!')
                    self.captcha_block = time.time()
                    raise Exception(f"Captcha blocked at {int(time.time())}")

                response_code = response['code']
                cookies_dict = {}
                for cookie in session.cookie_jar:
                    cookie_key = cookie.key
                    cookie_value = cookie.value
                    cookies_dict[cookie_key] = cookie_value

                expired_acc.cookies = cookies_dict
                expired_acc.ticket = ticket
                if response_code == 0:
                    expired_acc.expired = False

                await self.db.update_account_params(expired_acc)

                # Send it to the log channel
                if response_code not in [0, -51018]:
                    # 11104: Internet error. The returned cookies actually seem to be valid for check_trust
                    # -51018: Invoke ticket error. Updating Cookies and redoing request seems to clear it

                    raise Exception(f'Unknown Response for {expired_acc.email}! Response_code: {response["code"]}.'
                                    f'\nResponse:{response}')

            except Exception as e:
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
