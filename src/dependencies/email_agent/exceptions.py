from ..exceptions import RaiderBaseException


class MailAgentBaseException(RaiderBaseException):
    """Base exception for Mail Agent errors"""
    MESSAGE = "Mail Agent Base Exception"
    ERROR_CODE = 300

    def __init__(self, mail_address: str):
        self.mail_address = mail_address

    def get_message(self) -> str:
        return super().get_message() + f'\nMail Address: `{self.mail_address}`'


class ImapCommandFailure(MailAgentBaseException):
    """Raised when a IMAP command does not return a `OK` response"""
    MESSAGE = "IMAP Command Failure"
    ERROR_CODE = 301


class UnknownMailHost(MailAgentBaseException):
    """Raised when a unknown mail host is encountered"""
    MESSAGE = "Unknown Mail Host"
    ERROR_CODE = 302


class InitializationFailure(MailAgentBaseException):
    """Raised when the mail agent is not initialized"""
    MESSAGE = "Mail Agent Initialization Failure"
    ERROR_CODE = 303


class NoMatchingMailsFound(MailAgentBaseException):
    """Raised when no matching mails are found for a search"""
    MESSAGE = "Mail Agent Initialization Failure"
    ERROR_CODE = 304


class MailParsingError(MailAgentBaseException):
    """Raised when mail parsing fails"""
    MESSAGE = "Mail Parsing Error"
    ERROR_CODE = 310


class KeyCodeParseError(MailParsingError):
    """Raised when keycode can't be parsed out of the mail"""
    MESSAGE = "KeyCode Parsing Error"
    ERROR_CODE = 311

