class AlreadyBoughtChapter(Exception):
    """Used when a chapter is already bought"""


class FailedChapterBuy(Exception):
    """Used when a buy request fails"""


class UnknownResponseCode(Exception):
    """Used when a request returns an unknown response code"""

    def __init__(self, response_code: int, response_message: str):
        self.code = response_code
        self.message = response_message
