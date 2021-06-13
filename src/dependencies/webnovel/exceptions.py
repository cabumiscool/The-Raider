from ..exceptions import RaiderBaseException


class WebnovelBaseException(RaiderBaseException):
    """
    Base exception for all Webnovel related errors
    """
    MESSAGE = "Webnovel Base Exception"
    ERROR_CODE = 200


# TODO: Change this Exception later - Raz
class ErrorList(RaiderBaseException):
    def __init__(self, *errors):
        self.errors = []
        self.errors.extend(errors)


class ChapterAlreadyBought(WebnovelBaseException):
    """
    Raised when an account tries to buy a chapter it owns
    """
    MESSAGE = "Chapter Already Bought"
    ERROR_CODE = 201


class FailedWebnovelRequest(WebnovelBaseException):
    """
    Base Exception for all failed Webnovel Requests(aka requests with code as 1)
    """
    MESSAGE = "Failed Webnovel Request"
    ERROR_CODE = 210


class ChapterBuyFailed(FailedWebnovelRequest):
    """
    Raised when a Buy Request fails
    """
    MESSAGE = "Chapter Buy Failed"
    ERROR_CODE = 211


class UnknownResponseCode(WebnovelBaseException):
    """
    Raised when a request returns an unknown response code
    """
    MESSAGE = "Unknown Response Code"
    ERROR_CODE = 220

    def __init__(self, response_code: int, response_message: str):
        self.code = response_code
        self.message = response_message

    def get_message(self) -> str:
        return f"{self.MESSAGE}:\nResponse Code - `{self.code}`\nResponse Message - `{self.message}"


class MissingVolumesError(WebnovelBaseException):
    """
    Used when a book object tries to access the volumes but they haven't been added yet
    """
    MESSAGE = "Missing Volumes in Database"
    ERROR_CODE = 231
