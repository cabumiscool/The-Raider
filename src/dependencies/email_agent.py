import aioimaplib
import re

from bs4 import BeautifulSoup


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
            raise Exception(f"Unknown Mail Address Host...... Please add support for host of {mail_address}")
        self.IMAP_client = aioimaplib.IMAP4_SSL(host=self.host, timeout=120)
        self.mail_address = mail_address
        self.mail_pass = mail_pass
        self.initialized = False

    async def initialize(self):
        await self.IMAP_client.wait_hello_from_server()
        login_result, login_data = await self.IMAP_client.login(self.mail_address, self.mail_pass)
        if login_result == "OK":
            await self.IMAP_client.select("inbox")
            self.initialized = True

    async def __get_latest_mail__(self, subject: str, recipient: str):
        res, search_data = await self.IMAP_client.search(
            f'(FROM "noreply@webnovel.com" SUBJECT "{subject}" TO {recipient})')
        if res != 'OK':
            return ''
        data_list = search_data[0].split()
        if len(data_list) == 0:
            return ''
        data_item_last = data_list[-1]
        result_search, fetch_data = await self.IMAP_client.fetch(data_item_last, "(RFC822)")
        raw_mail = fetch_data[1].decode("utf-8")
        raw_mail = BeautifulSoup(raw_mail, "lxml").text
        formatted_mail = raw_mail.replace('=\r\n', '').replace('\t', '').replace('=3D', '=')
        return formatted_mail

    async def __do_get_latest_mail__(self, subject: str, recipient: str):
        # TODO: Check cock.li IMAP requests later for the same behaviour
        # Cock li IMAP server seems to update cache only when you call it twice
        res, search_data = await self.IMAP_client.search(
            f'(FROM "noreply@webnovel.com" SUBJECT "{subject}" TO {recipient})')
        if res != 'OK':
            return ''

    async def get_keycode_by_recipient(self, recipient: str):
        await self.__do_get_latest_mail__("Webnovel Support", recipient)
        parsed_mail = await self.__get_latest_mail__("Webnovel Support", recipient)
        if parsed_mail == '':
            return ''
        match = re.search(r'([0-9A-Z]{6})[\s\n]+This email ', parsed_mail)
        if match:
            key_code = match.group(1)
            return key_code
        else:
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
