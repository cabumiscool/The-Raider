
class DatabaseInitError(Exception):
    """raised when the database failes to init"""


class DatabaseMissingArguments(Exception):
    """raised when a method of the database is missing arguments"""


class DatabaseDuplicateEntry(Exception):
    """raised when a method of the database failes because an similar entry already exists"""
