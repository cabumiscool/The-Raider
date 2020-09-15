import typing
from operator import attrgetter


class DataDescriptorChecker:
    def __init__(self, expected_type: typing.Any = None):
        self._name = 'Unknown'
        self._value = None
        self._owner = None
        if expected_type is None:
            raise ValueError(f'The descriptor is missing an expected value')
        else:
            self.expected_type = expected_type

    def __set_name__(self, owner, name):
        self._name = name
        self._owner = owner

    def __set__(self, instance, value):
        if issubclass(value, self.expected_type):
            self._value = value
        else:
            raise TypeError(f"Was expecting a value of {self.expected_type.__name__} for attribute {self._name} at "
                            f"{self._owner.__name__}. Received instead a {type(value).__name__}")

    def __get__(self, instance, owner):
        return self._value


class Chapter:
    def __init__(self, chapter_level: int, chapter_id: int, book_id: int, index: int, is_vip: int, name: str):
        self.id = chapter_id
        self.is_privilege = bool(chapter_level)
        self.index = index
        self.is_vip = is_vip
        self.name = name
        self.book_id = book_id


class Volume:
    @staticmethod
    def __find_first_last_and_missing_indexes(*indexes: int) -> (int, int, typing.List[int]):
        list_of_indexes = sorted(indexes)
        first_index: int = list_of_indexes[0]
        expected_index: int = list_of_indexes[0]
        missing_indexes = []
        last_index = list_of_indexes[-1]
        for index in list_of_indexes:
            if index == expected_index:
                expected_index += 1
            else:
                difference = index - expected_index
                missing_indexes.append(expected_index)
                if difference > 1:
                    for _ in range(difference):
                        expected_index += 1
                        missing_indexes.append(expected_index)
        return first_index, last_index, missing_indexes

    def __init__(self, chapters_list: typing.List[Chapter], volume_index: int, book_id: int,
                 volume_name: str = "No-Name"):
        self.containing_items = {chapter.index: chapter.id for chapter in chapters_list}
        self._chapters = {chapter.id: chapter for chapter in chapters_list}
        self.index = volume_index
        self.name = volume_name
        self.book_id = book_id
        starting_index, last_index, missing = self.__find_first_last_and_missing_indexes(*[chapter.index for chapter
                                                                                           in chapters_list])
        self._start_index = starting_index
        self._last_index = last_index
        self._missing_indexes = missing

    def check_if_index_in_db(self, index: int):
        return self._start_index <= index <= self._last_index and index not in self._missing_indexes

    def retrieve_chapter_by_index(self, chapter_index: int) -> Chapter:
        if self.check_if_index_in_db(chapter_index):
            chapter_id = self._chapters[chapter_index]
            return self._chapters[chapter_id]
        else:
            raise ValueError(f"The index '{chapter_index}' is not part of this volume")

    def retrieve_chapter_by_id(self, chapter_id: int) -> Chapter:
        return self._chapters[chapter_id]


class Book:
    def __init__(self, book_id: int, book_name: str, novel_type: int, total_chapter_count: int):
        self.id = book_id
        self.name = book_name
        self.type = novel_type
        self.total_chapters = total_chapter_count
        self.volume_list = []

    def add_volume_list(self, volume_list: typing.List[Chapter]):
        self.volume_list = sorted(volume_list, key=attrgetter('index'))


class Account:
    def __init__(self, id_: int, qi_email: str, qi_pass: str, cookies: dict, ticket: str, expired: bool,
                 update_time: int, fp: int, library: int, library_pages: int, main_email: str, main_email_pass: str):
        self.id = id_
        self.email = qi_email
        self.password = qi_pass
        self.cookies = cookies
        self.ticket = ticket
        self.expired = expired
        self.update_time = update_time
        self.fast_pass_count = fp
        self.library_type = library
        self.library_pages = library_pages
        self.host_email = main_email
        self.host_email_password = main_email_pass
