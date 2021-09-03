import json
import typing
from operator import attrgetter

import aiohttp

from . import exceptions
from .utils import decode_qi_content


class DataDescriptorChecker:
    def __init__(self, expected_type: typing.Any = None):
        self._name = 'Unknown'
        self._value = None
        self._owner = None
        if expected_type is None:
            raise ValueError('The descriptor is missing an expected value')
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
        self.uut = int(uut)
        if avatar_pic_url == '':
            self.avatar_url = 0
        else:
            self.avatar_url = avatar_pic_url
        self.author = author
        self.pen_name = author_pen_name
        self.author_type = author_type
        self.content = content


class SimpleChapter:
    def __init__(self, chapter_level: int, chapter_id: int, parent_id: int, index: int, is_vip: int, name: str,
                 volume_index: int):
        self.id = int(chapter_id)
        self.is_privilege = bool(chapter_level)
        self.index = int(index)
        self.is_vip = int(is_vip)
        self.name = name
        self.parent_id = int(parent_id)
        self.volume_index = int(volume_index)

    def __eq__(self, other):
        if isinstance(other, (Chapter, SimpleChapter)):
            if not self.is_privilege == other.is_privilege:
                return False
            elif not self.index == other.index:
                return False
            elif not self.is_vip == other.is_vip:
                return False
            elif not self.name == other.name:
                return False
            elif not self.volume_index == other.volume_index:
                return False
            else:
                return True
        else:
            raise NotImplementedError

    def __ne__(self, other):
        if isinstance(other, (Chapter, SimpleChapter)):
            if not self.is_privilege == other.is_privilege:
                return True
            elif not self.index == other.index:
                return True
            elif not self.is_vip == other.is_vip:
                return True
            elif not self.name == other.name:
                return True
            elif not self.volume_index == other.volume_index:
                return True
            else:
                return False
        else:
            raise NotImplementedError

    def __repr__(self):
        return f'<SIMPLE CHAPTER (ID:{self.id}, NAME:{self.name}, INDEX:{self.index}, PRIVILEGE:{self.is_privilege}, ' \
               f'VIP:{self.is_vip}, PARENT_ID:{self.parent_id}, VOLUME_INDEX:{self.volume_index})>'


class Chapter(SimpleChapter):
    def __init__(self, chapter_level: int, chapter_id: int, parent_id: int, index: int, vip_status: int, name: str,
                 full_content: bool, content: str, price: int, volume_index: int, chapter_note: ChapterNote = None,
                 editor: str = None, translator: str = None):
        """Full metadata object for chapters
            :arg chapter_note takes the content of the author note at the end of chapters, may be
                safely ignored
            :arg chapter_note takes a ChapterNote obj, can be safely ignored
            :arg vip_status probably stands if it is premium, free or ad... needs confirmation
        """
        super().__init__(chapter_level, chapter_id, parent_id, index, vip_status, name, volume_index)
        self.is_full_content = full_content
        self.content = content
        self.note = chapter_note
        self.editor = editor
        self.translator = translator
        self.price = int(price)

    def __repr__(self):
        return f'<CHAPTER (ID:{self.id}, NAME:{self.name}, INDEX:{self.index}, PRIVILEGE:{self.is_privilege}, ' \
               f'VIP:{self.is_vip}, PARENT_ID:{self.parent_id}, VOLUME_INDEX:{self.volume_index}, PRICE:{self.price}' \
               f'IS_FULL_CONTENT:{self.is_full_content}>, EDITOR:{self.editor}, TRANSLATOR:{self.translator}, ' \
               f'NOTE:{self.note}, CONTENT:{self.content})>'

    def return_simple_chapter(self):
        return SimpleChapter(int(self.is_privilege), self.id, self.parent_id, self.index, self.is_vip, self.name,
                             self.volume_index)


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
        chapters_list = sorted(chapters_list, key=attrgetter("index"))
        self._chapters_with_index = {chapter.index: chapter for chapter in chapters_list}
        self._chapters = {chapter.id: chapter for chapter in chapters_list}
        self.index = int(volume_index)
        self.name = volume_name
        self.book_id = int(book_id)
        starting_index, last_index, missing = self.__find_first_last_and_missing_indexes(*[chapter.index for chapter
                                                                                           in chapters_list])
        self._start_index = starting_index
        self._last_index = last_index
        self._missing_indexes = missing

    def __repr__(self):
        return f'<VOLUME (INDEX:{self.index}, NAME:{self.name}, BOOK_ID:{self.book_id})>'

    def __check_if_index_in_volume(self, index: int):
        return self._start_index <= index <= self._last_index and index not in self._missing_indexes

    def check_if_id_in_volume(self, id_: int):
        return id_ in self._chapters

    def retrieve_chapter_by_index(self, chapter_index: int) -> SimpleChapter:
        if self.__check_if_index_in_volume(chapter_index):
            return self._chapters_with_index[chapter_index]
        raise KeyError(f"The index '{chapter_index}' is not part of this volume")

    def retrieve_chapter_by_id(self, chapter_id: int) -> SimpleChapter:
        """
        :param chapter_id: chapter id to try to retrieve the respective chapter from the volume
        :raises Keyerror
        :return: a SimpleChapter object
        """
        return self._chapters[chapter_id]

    def retrieve_volume_ranges(self, *, return_first: bool = True, return_last: bool = True,
                               return_missing: bool = True):
        """will return the available ranges found on the chapter or just a select few

            Args:
                :arg return_first if it should return the first index in the volume
                :arg return_last if it should return the last index in the volume
                :arg return_missing if it should return a list containing all the indexes that are missing in between

                """
        return_value = []
        if return_first:
            return_value.append(self._start_index)
        if return_last:
            return_value.append(self._last_index)
        if return_missing:
            return_value.append(self._missing_indexes)

        if len(return_value) > 1:
            return tuple(return_value)
        if len(return_value) == 0:
            raise ValueError('Missing enough arguments in the request')
        return return_value[0]

    def return_all_chapters_ids(self) -> typing.List[int]:
        return [chapter_id for chapter_id, chapter in self._chapters.items()]

    def return_all_chapter_objs(self) -> typing.List[SimpleChapter]:
        return [chapter for chapter_id, chapter in self._chapters.items()]


class SimpleBook:
    """To be used when not all of the book metadata is needed"""
    NovelType = 0

    def __init__(self, book_id: int, book_name: str, total_chapters: int, cover_id: int = None,
                 book_abbreviation: str = None, library_number: int = None):
        self.id = int(book_id)
        self.name = book_name
        if book_abbreviation is None:
            self.qi_abbreviation = False
            words = book_name.split(' ')
            if words == ['']:
                self.abbreviation = ''
            else:
                pseudo_abbreviation_list = []
                for word in words:
                    if word == '':
                        continue
                    pseudo_abbreviation_list.append(word[0])

                # pseudo_abbreviation = ''.join([word[0] for word in words])
                pseudo_abbreviation = ''.join(pseudo_abbreviation_list)
                self.abbreviation = pseudo_abbreviation
        else:
            self.qi_abbreviation = True
            self.abbreviation = book_abbreviation
        self.total_chapters = int(total_chapters)
        if cover_id is None:
            self.cover_id = None
        else:
            self.cover_id = int(cover_id)
        self.library_number = library_number  # this value can only be found in the internal db

    def __repr__(self):
        return f'<SIMPLE BOOK (ID:{self.id}, NAME:{self.name}, TOTAL_CHAPTERS:{self.total_chapters}, ' \
               f'LIBRARY_NUMBER:{self.library_number}, ABBREVIATION:{self.abbreviation}, COVER_ID:{self.cover_id})>'

    def __ne__(self, other):
        if isinstance(other, (SimpleBook, Book)):
            return self.total_chapters != other.total_chapters
        raise NotImplementedError(f"Don't know how to compare object type '{type(other)}' with type '{type(self)}'")

    def __eq__(self, other):
        if isinstance(other, (SimpleBook, Book)):
            return self.total_chapters == other.total_chapters
        raise NotImplementedError(f"Don't know how to compare object type '{type(other)}' with type '{type(self)}'")

    def __gt__(self, other):
        if issubclass(other, (SimpleBook, SimpleComic)) or isinstance(other, (SimpleBook, SimpleComic)):
            return self.total_chapters > other.total_chapters
        raise NotImplementedError(f"Don't know how to compare object type '{type(other)}' with type '{type(self)}'")


class Book(SimpleBook):
    """To be used when almost the complete metadata is needed. To assemble it requires the chapter api book section"""
    _types = {1: 'Translated', 2: 'Original'}
    _payment_method = ["Free", "Adwall", "Premium"]
    # translating related fields in status could also be in progress and not started... maybe. ui concern
    # og_status = {-1: 'UNTRANSLATED', 30: 'TRANSLATING', 40: 'SUSPEND', 50: 'COMPLETED'}
    _status = {-1: 'NOT STARTED', 30: 'IN PROGRESS', 40: 'SUSPENDED', 50: 'COMPLETED'}

    def __init__(self, book_id: int, book_name: str, total_chapter_count: int, is_privileged: bool,
                 type_is_tl: int, cover_id: int, action_status: int,
                 reading_type: int = None, book_abbreviation: str = None, library_number: int = None):
        super().__init__(book_id, book_name, total_chapter_count, cover_id, book_abbreviation=book_abbreviation,
                         library_number=library_number)
        self.privilege = is_privileged
        type_is_tl = int(type_is_tl)
        self.book_type = Book._types[type_is_tl]
        self.book_type_num = type_is_tl
        self.book_status = int(action_status)
        self.book_status_text = Book._status.get(self.book_status, 'UNKNOWN')
        if reading_type is not None:
            reading_type = int(reading_type)
            self.read_type = Book._payment_method[reading_type]
            self.read_type_num = reading_type
        else:
            self.read_type = None
            self.read_type_num = None
        self._volumes_list = []
        self._volume_dict = {}

    def __repr__(self):
        return f'<BOOK (ID:{self.id}, NAME:{self.name}, PRIVILEGE:{self.privilege}, BOOK_TYPE:{self.book_type} ' \
               f'TOTAL_CHAPTERS:{self.total_chapters}, READ_TYPE:{self.read_type}, COVER_ID:{self.cover_id}, ' \
               f'BOOK_STATUS:{self.book_status_text}, LIBRARY_NUMBER:{self.library_number})>'

    def __ne__(self, other):
        if isinstance(other, Book):
            if len(self._volumes_list) > 0 and len(self._volumes_list) > 0:
                return_list = []
                # self_chapters_id = [volume.return_all_chapters_ids() for volume in self.return_volume_list()]
                self_chapters_id = __retrieve_all_chapters_ids__(self)

                # other_chapters_id = [volume.return_all_chapters_ids() for volume in other.return_volume_list()]
                other_chapters_id = __retrieve_all_chapters_ids__(other)

                for chapter_id in self_chapters_id:
                    if chapter_id in other_chapters_id:
                        pass
                    else:
                        return_list.append(chapter_id)

                return return_list

            else:
                raise exceptions.MissingVolumesError("One of the two objects being compared is missing a volume list")
        else:
            return NotImplemented

    def return_simple_book(self):
        if self.qi_abbreviation:
            abbreviation = self.abbreviation
        else:
            abbreviation = None
        return SimpleBook(self.id, self.name, self.total_chapters, self.cover_id, abbreviation, self.library_number)

    def add_volume_list(self, volume_list: typing.List[Volume]):
        self._volumes_list = sorted(volume_list, key=attrgetter('index'))
        self._volume_dict = {volume.index: volume for volume in self._volumes_list}

    def return_volume_list(self) -> typing.List[Volume]:
        if len(self._volumes_list) == 0:
            raise ValueError('No the book object contains no volume objects')
        return self._volumes_list

    def retrieve_chapter_by_id(self, chapter_id: int):
        if len(self._volumes_list) > 0:
            for volume in self._volumes_list:
                try:
                    chapter = volume.retrieve_chapter_by_id(chapter_id)
                    return chapter
                except KeyError:
                    pass
            raise ValueError("Chapter not found on the Book")
        raise exceptions.MissingVolumesError('The book object is missing volume objects')

    def retrieve_chapter_by_index(self, chapter_index: int):
        if len(self._volumes_list) > 0:
            for volume in self._volumes_list:
                try:
                    chapter = volume.retrieve_chapter_by_index(chapter_index)
                    return chapter
                except KeyError:
                    pass
            raise ValueError("Chapter not found on the Book")
        else:
            raise exceptions.MissingVolumesError('The book object is missing volume objects')

    def return_priv_chapters_count(self):
        chapters_count = 0
        for volume in self._volumes_list:
            for chapter in volume.return_all_chapter_objs():
                if chapter.is_privilege:
                    chapters_count += 1
        return chapters_count


def __retrieve_all_chapters_ids__(book: Book):
    chapters_id = []
    for volume in book.return_volume_list():
        volume_chapters_list = volume.return_all_chapters_ids()
        chapters_id.extend(volume_chapters_list)
    return chapters_id


class SimpleComic:
    """To be used when not of all the comic metadata is needed"""
    NovelType = 100

    def __init__(self, comic_id: int, comic_name: str, cover_id: int, total_chapters: int):
        self.id = comic_id
        self.name = comic_name
        self.cover_id = cover_id
        self.total_chapters = total_chapters


class Comic(SimpleComic):
    """To be used when almost the complete metadata is needed. To assemble it requires as a minimum the chapter list
    api """
    payment_method = ["Free", "Adwall", "Premium"]

    def __init__(self, comic_id: int, comic_name: str, cover_id: int, total_chapters: int, is_privileged: bool,
                 reading_type: int):
        super().__init__(comic_id, comic_name, cover_id, total_chapters)
        self.reading_type = self.payment_method[reading_type]
        self.privileged = is_privileged


class QiAccount:
    def __init__(self, id_: int, qi_email: str, qi_pass: str, cookies: dict, ticket: str, expired: bool,
                 update_time: int, fp: int, library_type: int, library_pages: int, main_email_id: int, guid: int):
        self.id = id_
        self.email = qi_email
        self.password = qi_pass
        try:
            self.cookies = dict(cookies)
        except ValueError:
            cookies: str
            self.cookies = json.loads(cookies)
        self.ticket = ticket
        self.expired = bool(expired)
        self.update_time = update_time
        self.fast_pass_count = int(fp)
        self.library_type = library_type
        self.library_pages = library_pages
        self.host_email_id = main_email_id
        self.guid = int(guid)

    def __repr__(self):
        return f'<QI_ACCOUNT (ID:{self.id}, GUID:{self.guid}, EMAIL:{self.email}, FP_COUNT:{self.fast_pass_count}, ' \
               f'EXPIRED:{self.expired}, UPDATE_TIME{self.update_time}, HOST_EMAIL:{self.host_email_id}, ' \
               f'LIBRARY_TYPE:{self.library_type}, LIBRARY_PAGES:{self.library_pages})>'

    def _read_valid(self, user_dict: dict) -> bool:
        if user_dict['userName'] != '':
            self.fast_pass_count = user_dict['fastPass']
            return True
        return False

    # TODO: Should this be moved to auth.py or a new file?
    # Also Do we need a sync version?
    # def check_valid(self) -> bool:
    #     params = {'taskType': 1, '_csrfToken': self.cookies['_csrfToken']}
    #     response = requests.get('https://www.webnovel.com/apiajax/task/taskList', params=params, cookies=self.cookies)
    #     response_dict = decode_qi_content(response.content)
    #     user_dict = response_dict['user']
    #     return self._read_valid(user_dict)

    async def async_check_valid(self) -> bool:
        task_list_url = 'https://www.webnovel.com/go/pcm/task/getTaskList'
        params = {'taskType': 1, '_csrfToken': self.cookies['_csrfToken']}
        try_attempt = 0
        while True:
            try:
                async with aiohttp.request('get', task_list_url, params=params, cookies=self.cookies) as req:
                    response_dict = decode_qi_content(await req.read())
                    break
            except json.JSONDecodeError:
                pass
            try_attempt += 1
            if try_attempt > 5:
                raise TimeoutError
        response_data = response_dict['data']
        user_dict = response_data['user']
        return self._read_valid(user_dict)


class EmailAccount:
    def __init__(self, email: str, password: str, id_: int):
        self.id = id_
        self.email = email
        self.password = password

    def __repr__(self):
        return f'<EMAIL_ACCOUNT (ID:{self.id}, EMAIL:{self.email})>'
