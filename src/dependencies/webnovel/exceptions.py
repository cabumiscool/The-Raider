class AlreadyBoughtChapter(Exception):
    """Used when a chapter is already bought"""


class FailedChapterBuy(Exception):
    """Used when a buy request fails"""


class FailedRequest(Exception):
    pass


class MissingVolumesError(Exception):
    """Used when a book object tries to access the volumes but they haven't been added yet"""


class UnknownResponseCode(Exception):
    """Used when a request returns an unknown response code"""

    def __init__(self, response_code: int, response_message: str):
        self.code = response_code
        self.message = response_message
        super().__init__()
