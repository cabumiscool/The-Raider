import re

import aioimaplib
from bs4 import BeautifulSoup


class MailAgentNotInitialized(Exception):
    """Error raised when the mail agent is not initialized"""


class MailAgentConnectionBroken(Exception):
    """Error raised when the mail agent times out"""


class MailAgent:
    def __init__(self, mail_address: str, mail_pass: str):
        self.port = 993
        if mail_address.find("@gmail.") != -1:
            self.host = "imap.gmail.com"
        elif mail_address.find("@yahoo.") != -1:
            self.host = "imap.mail.yahoo.com"
        elif mail_address.find("@outlook.") != -1:
            self.host = "imap-mail.outlook.com"
        elif mail_address.find("@cock.li") != -1:
            self.host = "mail.cock.li"
        else:
            raise Exception(f"Unknown Mail Address Host...... No support for mail server of {mail_address}")
        self.imap_client = aioimaplib.IMAP4_SSL(host=self.host, timeout=120)
        self.mail_address = mail_address
        self.mail_pass = mail_pass
        self.__initialized = False

    async def initialize(self):
        self.imap_client = aioimaplib.IMAP4_SSL(host=self.host, timeout=120)
        await self.imap_client.wait_hello_from_server()
        login_result, login_data = await self.imap_client.login(self.mail_address, self.mail_pass)
        if login_result == "OK":
            await self.imap_client.select("inbox")
            self.__initialized = True

    def __initialization_check(self):
        if self.__initialized is True:
            return True
        raise MailAgentNotInitialized

    async def check_connection(self) -> False:
        # TODO: Check cock.li IMAP requests later for the same behaviour
        # Cock li IMAP server seems to update cache only when you call it twice
        try:
            self.__initialization_check()
            res, _ = await self.imap_client.search()
            if res == 'OK':
                return True
        except TimeoutError as err:
            raise MailAgentConnectionBroken from err

    async def __get_latest_mail__(self, subject: str, recipient: str):
        await self.check_connection()
        res, result = await self.imap_client.search(f'(FROM "noreply@webnovel.com" SUBJECT "{subject}" TO {recipient})')
        if res != 'OK':
            return ''
        data_list = result[0].split()
        if len(data_list) == 0:
            return ''
        data_item_last = data_list[-1]
        result_search, fetch_data = await self.imap_client.fetch(data_item_last, "(RFC822)")
        raw_mail = fetch_data[1].decode("utf-8")
        raw_mail = BeautifulSoup(raw_mail, "lxml").text
        formatted_mail = raw_mail.replace('=\r\n', '').replace('\t', '').replace('=3D', '=')
        return formatted_mail

    async def get_keycode_by_recipient(self, recipient: str):
        parsed_mail = await self.__get_latest_mail__("Webnovel Support", recipient)
        if parsed_mail == '':
            return ''
        match = re.search(r'([0-9A-Z]{6})[\s\n]+This email ', parsed_mail)
        if match:
            key_code = match.group(1)
            return key_code
        return ''

    async def confirmation_url(self, recipient: str):
        formatted_mail = await self.__get_latest_mail__("Activate your Webnovel account", recipient)
        if formatted_mail == '':
            return ''
        str_check = "bold;\">We're glad you're here!"
        keycode_start = formatted_mail.find(str_check) + len(str_check)
        keycode_end = formatted_mail.find('" title="START READING', keycode_start)
        confirm_url = formatted_mail[keycode_start:keycode_end]
        return confirm_url
