import asyncio
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


# A class that allows you to get the confirmation link from a webnovel account
class MailAgent:
    def __init__(self, mail_address: str, mail_pass: str):
        """
        Takes two arguments, a mail address and a password, and then it sets the port to 993, and
        then it checks if the mail address is a gmail, yahoo, outlook, or cock.li address, and then it
        sets the host to the appropriate host, and then it creates an imap client, and then it sets the
        mail address and password to the arguments, and then it sets the initialized variable to False
        
        :param mail_address: The email address you want to use
        :type mail_address: str
        :param mail_pass: The password for the email account
        :type mail_pass: str
        """
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
        """
        The function returns a string representation of the object
        :return: The return value is a string representation of the object.
        """
        return f'<MAIL AGENT (MAIL_ADDRESS:{self.mail_address}, HOST:{self.host}, PORT:{self.port}, ' \
               f'INITIALIZED:{self.__initialized})>'

    def imap_response_check(self, response: str):
        """
        Checks if the response from the IMAP server is "OK" and if not, it raises an exception
        
        :param response: str
        :type response: str
        :return: The return value of the function is the return value of the last statement in the
        function.
        """
        if response != "OK":
            raise ImapCommandFailure(self.mail_address)
        return True

    async def initialize(self) -> None:
        """
        Waits for the server to send a greeting, then logs in, then selects the inbox
        """
        await self.imap_client.wait_hello_from_server()

        res, login_data = await self.imap_client.login(self.mail_address, self.mail_pass)
        self.imap_response_check(res)

        await self.imap_client.select("inbox")
        self.__initialized = True

    def __initialization_check(self) -> bool:
        """
        If the object is not initialized, return True. Otherwise, raise an exception
        :return: a boolean value.
        """
        if self.__initialized is not True:
            return True
        raise InitializationFailure(self.mail_address)

    def __parse_mail(self, raw_mail: bytes) -> str:
        """
        Takes a raw email, decodes it, removes all the HTML tags, and returns the plain text
        
        :param raw_mail: bytes
        :type raw_mail: bytes
        :return: The return value is a string.
        """
        try:
            raw_mail = raw_mail.decode("utf-8")
            raw_mail = BeautifulSoup(raw_mail, "lxml").text
            formatted_mail = raw_mail.replace('=\r\n', '').replace('\t', '').replace('=3D', '=').replace('=09', '')
            return formatted_mail
        except Exception as e:
            raise MailParsingError(self.mail_address) from e

    async def __get_latest_mail__(self, subject: str, recipient: str) -> List[bytes]:
        """
        Searches for the latest email with the given subject and recipient, and returns the raw email
        data
        
        :param subject: str = "Webnovel - Reset Password"
        :type subject: str
        :param recipient: the email address you're sending to
        :type recipient: str
        :return: A list of bytes
        """
        # Patch to allow `theseeker` accounts (No idea why searching twice works)
        res, result = await self.imap_client.search(f'(FROM "noreply@webnovel.com" SUBJECT "{subject}" TO {recipient})')
        await asyncio.sleep(5)
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
        """
        Fetches the latest email from the sender "Webnovel Support" and then parses the email to find
        the keycode
        
        :param recipient: The email address you want to get the keycode from
        :type recipient: str
        :return: The keycode is being returned.
        """
        mail_fetch = await self.__get_latest_mail__("Webnovel Support", recipient)
        parsed_mail = self.__parse_mail(mail_fetch[1])

        match = re.search(r'([0-9a-zA-Z]{6})[\s\n]+This email ', parsed_mail)
        if not match:
            raise KeyCodeParseError(self.mail_address)
        key_code = match.group(1)
        return key_code

    async def confirmation_url(self, recipient: str) -> str:
        """
        Gets the latest email from the sender "Webnovel Support" and the recipient "recipient" and
        then parses the email to find the confirmation url
        
        :param recipient: the email address you want to check
        :type recipient: str
        :return: The confirmation url
        """
        mail_content = await self.__get_latest_mail__("Webnovel Support", recipient)
        parsed_mail = self.__parse_mail(mail_content[1])

        str_check = "bold;\">We're glad you're here!"
        keycode_start = parsed_mail.find(str_check) + len(str_check)
        keycode_end = parsed_mail.find('" title="START READING', keycode_start)
        confirm_url = parsed_mail[keycode_start:keycode_end]
        return confirm_url
