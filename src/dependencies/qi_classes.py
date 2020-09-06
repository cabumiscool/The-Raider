import aiohttp
import asyncio
import typing


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
    def __init__(self, chapter_level: int, chapter_id: int, index: int, is_vip: int, name: str):
        self.id = chapter_id
        self.is_privilege = bool(chapter_level)
        self.index = index
        self.is_vip = is_vip
        self.name = name


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

    def __init__(self, chapters_list: typing.List[Chapter], volume_index: int, volume_name: str = "No-Name"):
        self.containing_items = {chapter.index: chapter.id for chapter in chapters_list}
        self._chapters = {chapter.id: chapter for chapter in chapters_list}
        self.index = volume_index
        self.name = volume_name
        starting_index, last_index, missing = self.__find_first_last_and_missing_indexes(*[chapter.index for chapter
                                                                                           in chapters_list])
        self._start_index = starting_index
        self._last_index = last_index
        self._missing_indexes = missing

    def retrieve_chapter_by_index(self, chapter_index: int) -> Chapter:
        if self._start_index <= chapter_index <= self._last_index and chapter_index not in self._missing_indexes:
            return self._chapters[chapter_index]
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
        self.chapter_list = []


class Account:
    pass
