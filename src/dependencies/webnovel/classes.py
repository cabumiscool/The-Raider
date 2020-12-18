import typing
import requests
import aiohttp
from operator import attrgetter
from dependencies.utils import decode_qi_content


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


class ChapterNote:
    def __init__(self, uut: int, avatar_pic_url: str, author: str, content: str, author_pen_name: str,
                 author_type: str):
        self.uut = uut
        self.avatar_url = avatar_pic_url
        self.author = author
        self.pen_name = author_pen_name
        self.author_type = author_type
        self.content = content


class SimpleChapter:
    def __init__(self, chapter_level: int, chapter_id: int, parent_id: int, index: int, is_vip: int, name: str):
        self.id = chapter_id
        self.is_privilege = bool(chapter_level)
        self.index = index
        self.is_vip = is_vip
        self.name = name
        self.parent_id = parent_id


class Chapter(SimpleChapter):
    def __init__(self, chapter_level: int, chapter_id: int, parent_id: int, index: int, vip_status: int, name: str,
                 full_content: bool, content: str, price: int, chapter_note: ChapterNote = None,
                 editor: str = None, translator: str = None):
        """Full metadata object for chapters
                :arg chapter_note takes the content of the author note at the end of chapters, may be
                safely ignored
                :arg chapter_note takes a ChapterNote obj, can be safetly ignored
                """
        super().__init__(chapter_level, chapter_id, parent_id, index, vip_status, name)
        self.is_preview = full_content
        self.content = content
        self.note = chapter_note
        self.editor = editor
        self.translator = translator
        self.price = price


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

    def __init__(self, chapters_list: typing.List[SimpleChapter], volume_index: int, book_id: int,
                 volume_name: str = "No-Name"):
        # self.containing_items = {chapter.index: chapter.id for chapter in chapters_list}
        self._chapters = {chapter.id: chapter for chapter in chapters_list}
        self.index = volume_index
        self.name = volume_name
        self.book_id = book_id
        starting_index, last_index, missing = self.__find_first_last_and_missing_indexes(*[chapter.index for chapter
                                                                                           in chapters_list])
        self._start_index = starting_index
        self._last_index = last_index
        self._missing_indexes = missing

    def __check_if_index_in_db(self, index: int):
        return self._start_index <= index <= self._last_index and index not in self._missing_indexes

    def retrieve_chapter_by_index(self, chapter_index: int) -> SimpleChapter:
        if self.__check_if_index_in_db(chapter_index):
            chapter_id = self._chapters[chapter_index]
            return self._chapters[chapter_id]
        else:
            raise ValueError(f"The index '{chapter_index}' is not part of this volume")

    def retrieve_chapter_by_id(self, chapter_id: int) -> SimpleChapter:
        return self._chapters[chapter_id]


class SimpleBook:
    NovelType = 0
    """To be used when not all of the book metadata is needed"""
    def __init__(self, book_id: int, book_name: str, total_chapters: int, cover_id: int, book_abbreviation: str = None,
                 library_number: int = None):
        self.id = book_id
        self.name = book_name
        if book_abbreviation is None:
            self.qi_abbreviation = False
            words = book_name.split(' ')
            pseudo_abbreviation = ''.join([word[0] for word in words])
            self.abbreviation = pseudo_abbreviation
        else:
            self.qi_abbreviation = True
            self.abbreviation = book_abbreviation
        self.total_chapters = total_chapters
        self.cover_id = cover_id
        self.library_number = library_number  # this value can only be in the internal db


class Book(SimpleBook):
    """To be used when almost the complete metadata is needed. To assemble it requires the chapter api book section"""
    types = {1: 'Translated', 2: 'Original'}
    payment_method = ["Free", "Adwall", "Premium"]

    def __init__(self, book_id: int, book_name: str, total_chapter_count: int, is_priv: bool,
                 type_is_tl: int, cover_id: int,
                 reading_type: int = None, book_abbreviation: str = None):
        super().__init__(book_id, book_name, total_chapter_count, cover_id, book_abbreviation=book_abbreviation)
        self.privilege = is_priv
        self.book_type = self.types[type_is_tl]
        self.book_type_num = type_is_tl
        self.read_type = self.payment_method[reading_type]
        self.read_type_num = reading_type
        self._volume_list = []

    def add_volume_list(self, volume_list: typing.List[SimpleChapter]):
        self._volume_list = sorted(volume_list, key=attrgetter('index'))


class SimpleComic:
    NovelType = 100
    """To be used when not of all the comic metadata is needed"""
    def __init__(self, comic_id: int, comic_name: str, cover_id: int, total_chapters: int):
        self.id = comic_id
        self.name = comic_name
        self.cover_id = cover_id
        self.total_chapters = total_chapters


class Comic(SimpleComic):
    """To be used when almost the complete metadata is needed. To assemble it requires as a minimum the chapter
        list api"""
    payment_method = ["Free", "Adwall", "Premium"]

    def __init__(self, comic_id: int, comic_name: str, cover_id: int, total_chapters: int, is_privilege: bool,
                 reading_type: int):
        super().__init__(comic_id, comic_name, cover_id, total_chapters)
        self.reading_type = self.payment_method[reading_type]


class Account:
    def __init__(self, id_: int, qi_email: str, qi_pass: str, cookies: dict, ticket: str, expired: bool,
                 update_time: int, fp: int, library_type: int, library_pages: int, main_email: str, main_email_pass: str):
        self.id = id_
        self.email = qi_email
        self.password = qi_pass
        self.cookies = cookies
        self.ticket = ticket
        self.expired = expired
        self.update_time = update_time
        self.fast_pass_count = fp
        self.library_type = library_type
        self.library_pages = library_pages
        self.host_email = main_email
        self.host_email_password = main_email_pass

    def _read_valid(self, user_dict: dict) -> bool:
        if user_dict['userName'] == '':
            return False
        else:
            self.fast_pass_count = user_dict['fastPass']
            return True

    def check_valid(self) -> bool:
        params = {'taskType': 1, '_csrfToken': self.cookies['_csrfToken']}
        response = requests.get('https://www.webnovel.com/apiajax/task/taskList', params=params, cookies=self.cookies)
        response_dict = decode_qi_content(response.content)
        user_dict = response_dict['user']
        return self._read_valid(user_dict)

    async def async_check_valid(self) -> bool:
        params = {'taskType': 1, '_csrfToken': self.cookies['_csrfToken']}
        async with aiohttp.request('get', 'https://www.webnovel.com/apiajax/task/taskList', params=params,
                                   cookies=self.cookies) as req:
            response_dict = decode_qi_content(await req.read())
        user_dict = response_dict['user']
        return self._read_valid(user_dict)