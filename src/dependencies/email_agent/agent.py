import re
from typing import List

import aioimaplib
from bs4 import BeautifulSoup

from .exceptions import (
    UnknownMailHost,
    InitializationFailure,
    ImapCommandFailure,
    NoMatchingMailsFound,
    MailParsingError,
    KeyCodeParseError
)


class MailAgent:
    def __init__(self, mail_address: str, mail_pass: str):
        self.port = 993
        if mail_address.find("@gmail.") != -1:
            self.host = "imap.gmail.com"
        elif mail_address.find("@yahoo.") != -1:
            self.host = "imap.mail.yahoo.com"
        elif mail_address.find("@outlook.") != -1:
            self.host = "imap-mail.outlook.com"
        elif mail_address.find("@cock.li") != -1 or mail_address.find("@airmail.cc") != -1:
            self.host = "mail.cock.li"
        else:
            raise UnknownMailHost(self.mail_address)
        self.imap_client = aioimaplib.IMAP4_SSL(host=self.host, timeout=120)
        self.mail_address = mail_address
        self.mail_pass = mail_pass
        self.__initialized = False

    def __repr__(self):
        return f'<MAIL AGENT (MAIL_ADDRESS:{self.mail_address}, HOST:{self.host}, PORT:{self.port}, ' \
               f'INITIALIZED:{self.__initialized})>'

    def imap_response_check(self, response: str):
        if response != "OK":
            raise ImapCommandFailure(self.mail_address)
        return True

    async def initialize(self) -> None:
        await self.imap_client.wait_hello_from_server()

        res, login_data = await self.imap_client.login(self.mail_address, self.mail_pass)
        self.imap_response_check(res)

        await self.imap_client.select("inbox")
        self.__initialized = True

    def __initialization_check(self) -> bool:
        if self.__initialized is not True:
            return True
        raise InitializationFailure(self.mail_address)

    def __parse_mail(self, raw_mail: bytes) -> str:
        try:
            raw_mail = raw_mail.decode("utf-8")
            raw_mail = BeautifulSoup(raw_mail, "lxml").text
            formatted_mail = raw_mail.replace('=\r\n', '').replace('\t', '').replace('=3D', '=').replace('=09', '')
            return formatted_mail
        except Exception as e:
            raise MailParsingError(self.mail_address) from e

    async def __get_latest_mail__(self, subject: str, recipient: str) -> List[bytes]:
        res, result = await self.imap_client.search(f'(FROM "noreply@webnovel.com" SUBJECT "{subject}" TO {recipient})')
        self.imap_response_check(res)

        mail_entries_list = result[0].split()
        if len(mail_entries_list) == 0:
            raise NoMatchingMailsFound(self.mail_address)

        latest_mail_entry = mail_entries_list[-1]
        if type(latest_mail_entry) is not str:
            latest_mail_entry = latest_mail_entry.decode('utf-8')

        res, mail_fetch = await self.imap_client.fetch(latest_mail_entry, "(RFC822)")
        self.imap_response_check(res)

        return mail_fetch

    async def get_keycode_by_recipient(self, recipient: str) -> str:
        mail_fetch = await self.__get_latest_mail__("Webnovel Support", recipient)
        parsed_mail = self.__parse_mail(mail_fetch[1])

        match = re.search(r'([0-9a-zA-Z]{6})[\s\n]+This email ', parsed_mail)
        if not match:
            raise KeyCodeParseError(self.mail_address)
        key_code = match.group(1)
        return key_code

    async def confirmation_url(self, recipient: str) -> str:
        mail_content = await self.__get_latest_mail__("Webnovel Support", recipient)
        parsed_mail = self.__parse_mail(mail_content[1])

        str_check = "bold;\">We're glad you're here!"
        keycode_start = parsed_mail.find(str_check) + len(str_check)
        keycode_end = parsed_mail.find('" title="START READING', keycode_start)
        confirm_url = parsed_mail[keycode_start:keycode_end]
        return confirm_url
