import json
from asyncio import CancelledError
from io import BytesIO
from time import time
from typing import List, Union, Tuple

import aiohttp
import aiohttp_socks
from bs4 import BeautifulSoup

from dependencies.proxy_classes import Proxy
from .. import classes, exceptions
from ..utils import decode_qi_content

# API_ENDPOINT_1 = 'https://www.webnovel.com/apiajax/chapter'

default_connector_settings = {'force_close': True, 'enable_cleanup_closed': True}

API_ENDPOINT_2 = 'https://www.webnovel.com/go/pcm/chapter'


# TODO change the input from the proxy connector to the proxy class where required


async def generate_thumbnail_url_or_file(book_id: int, url_only: bool = True, session: aiohttp.ClientSession = None,
                                         proxy_connector: aiohttp_socks.ProxyConnector = None) -> Union[str, BytesIO]:
    """
    Returns either a URL or a BytesIO object of the thumbnail of a book
    
    :param book_id: The book ID of the book you want to get the thumbnail of
    :type book_id: int
    :param url_only: If you want the url of the image, set this to True. If you want the image itself,
    set this to False, defaults to True
    :type url_only: bool (optional)
    :param session: aiohttp.ClientSession = None
    :type session: aiohttp.ClientSession
    :param proxy_connector: aiohttp_socks.ProxyConnector = None
    :type proxy_connector: aiohttp_socks.ProxyConnector
    :return: A string or a BytesIO object.
    """
    assert isinstance(book_id, int)
    cover_url = f"https://img.webnovel.com/bookcover/{book_id}/150/150.jpg"
    if not url_only:
        if session is None:
            if not proxy_connector:
                proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

            async with proxy_connector as connector:
                async with aiohttp.request('GET', cover_url, connector=connector) as req:
                    image_file = BytesIO(await req.read())
        else:
            async with session.get(cover_url) as req:
                image_file = BytesIO(await req.read())
        return image_file
    else:
        return cover_url


def find_volume_index_from_id(chapter_id, volumes: List[classes.Volume]) -> int:
    """
    Takes a chapter id and a list of volumes, and returns the index of the volume that contains the
    chapter id
    
    :param chapter_id: The id of the chapter you want to find the volume index of
    :param volumes: List[classes.Volume]
    :type volumes: List[classes.Volume]
    :return: The index of the volume that contains the chapter_id.
    """
    for volume in volumes:
        if volume.check_if_id_in_volume(chapter_id):
            volume_index = volume.index
            break
    else:
        volume_index = 0
    return volume_index


async def __chapter_list_retriever_call(params: dict, api_endpoint: str, session: aiohttp.ClientSession = None,
                                        proxy_connector: aiohttp_socks.ProxyConnector = None):
    """
    Takes a dictionary of parameters, an API endpoint, and an optional aiohttp session and proxy
    connector, and returns a dictionary of the response
    
    :param params: dict = {'manga_id': manga_id, 'chapter_id': chapter_id, 'page': page}
    :type params: dict
    :param api_endpoint: https://manga.bilibili.com/twirp/comic.v1.Comic/ComicDetail
    :type api_endpoint: str
    :param session: aiohttp.ClientSession = None
    :type session: aiohttp.ClientSession
    :param proxy_connector: aiohttp_socks.ProxyConnector = None
    :type proxy_connector: aiohttp_socks.ProxyConnector
    :return: A dictionary of the response from the API endpoint.
    """
    if session is None:
        if not proxy_connector:
            proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

        async with proxy_connector as connector:
            async with aiohttp.request('GET', api_endpoint, params=params, connector=connector) as req:
                resp_bin = await req.read()
                resp_dict = decode_qi_content(resp_bin)
    else:
        async with session.get(api_endpoint, params=params) as req:
            resp_bin = await req.read()
            resp_dict = decode_qi_content(resp_bin)

    return resp_dict


async def trail_read_books_finder() -> List[int]:
    """
    Gets the book ids of all the books that are currently being promoted on the webnovel website
    :return: A list of integers.
    """
    books_ids = set()
    for i in range(1, 3):
        async with aiohttp.request("get", f"https://www.webnovel.com/trailer?sex={i}") as resp:
            page_html = await resp.read()
        soup = BeautifulSoup(page_html, "lxml")
        hyperlinks = soup.find_all("a")
        for hyperlink in hyperlinks:
            book_id_str = hyperlink.attrs.get("data-bookid", None)
            if book_id_str:
                book_id = int(book_id_str)
                books_ids.add(book_id)
    return list(books_ids)


async def chapter_list_retriever(book: Union[classes.SimpleBook, int], session: aiohttp.ClientSession = None,
                                 proxy: Proxy = None, return_book: bool = False
                                 ) -> Union[List[classes.Volume], Tuple[List[classes.Volume], classes.SimpleBook]]:
    """
    Takes a book object, and returns a list of Volume objects
    
    :param book: Union[classes.SimpleBook, int]
    :type book: Union[classes.SimpleBook, int]
    :param session: aiohttp.ClientSession = None,
    :type session: aiohttp.ClientSession
    :param proxy: Proxy = None
    :type proxy: Proxy
    :param return_book: bool = False, defaults to False
    :type return_book: bool (optional)
    :return: A list of Volume objects or a tuple in the following format (list[volume objects],simple
    book])
    """
    #  aiohttp_socks.ProxyConnector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)
    """Retrieves a chapter list of a book
        :arg book receives either a book or a book_id from which to retrieve the chapter list
        :arg session receives an aiohttp session object that includes the cookies of the account, if empty will use the
            account arg to generate a request
        :arg proxy accepts an aiohttp proxy connector object, will be ignored if session is given
        :arg return_book defines if it should return the book metadata found on the chapter list
        :returns a list containing Volume objects or a tuple in the following format (list[volume objects],simple book])

    """
    if isinstance(book, int):
        book = classes.SimpleBook(book, '', 0)
    params = {'bookId': str(book.id), '_': str(time())}
    if session:
        assert isinstance(session, aiohttp.ClientSession)
        csrf_token = ''
        for cookie in session.cookie_jar:
            if cookie.key == '_csrfToken':
                csrf_token = cookie.value
        params['_csrfToken'] = csrf_token
    api = '/'.join((API_ENDPOINT_2, 'get-chapter-list'))
    try_attempts = 0
    errors = []
    while True:
        try:
            proxy_connector = None
            if proxy:
                proxy_connector = proxy.generate_connector()

            resp_dict = await __chapter_list_retriever_call(params, api, session, proxy_connector=proxy_connector)
            # if session is None:
            #     # TODO check if it is possible to retrieve a specific cookie from the session
            #
            #     if proxy:
            #         proxy_connector = proxy.generate_connector()
            #     else:
            #         proxy_connector = aiohttp.TCPConnector()
            #
            #     async with aiohttp.request('GET', api, params=params, connector=proxy_connector) as req:
            #         resp_bin = await req.read()
            #         resp_str = resp_bin.decode()
            #         resp_dict = json.loads(resp_str)
            # else:
            #     async with session.get(api, params=params) as req:
            #         resp_bin = await req.read()
            #         resp_str = resp_bin.decode()
            #         resp_dict = json.loads(resp_str)
            break
        except json.JSONDecodeError:
            pass
        except CancelledError:
            raise CancelledError
        except Exception as e:
            errors.append(e)
        try_attempts += 1
        if try_attempts > 8:
            raise TimeoutError
        # except Exception:
        #     # TODO analyze what exceptions can here paying special attention to the exceptions that happen when proxy
        #     #  is used
        #     pass
    code = resp_dict['code']
    if code == 0:
        # successful request
        data_message = resp_dict['data']
        book_metadata = data_message['bookInfo']
        book_name = book_metadata['bookName']
        book_sub_name = book_metadata.get('bookSubName', None)
        total_chapters = book_metadata['totalChapterNum']
        volumes_dict = data_message['volumeItems']
        simple_book = classes.SimpleBook(book.id, book_name, total_chapters, book_abbreviation=book_sub_name)
        volumes = []
        for volume in volumes_dict:
            chapters = []
            volume_index = volume['volumeId']
            volume_name = volume['volumeName']
            chapters_list = volume['chapterItems']
            for chapter in chapters_list:
                chapter_level = chapter['chapterLevel']
                chapter_id = chapter['chapterId']
                chapter_index = chapter['chapterIndex']
                chapter_vip = chapter['isVip']
                chapter_name = chapter['chapterName']
                chapters.append(classes.SimpleChapter(chapter_level, chapter_id, book.id, chapter_index, chapter_vip,
                                                      chapter_name, volume_index))
            volumes.append(classes.Volume(chapters, volume_index, book.id, volume_name))
        if return_book:
            return volumes, simple_book
        return volumes
    if code == 1:
        # TODO check if 1 is error and log the error to database for later review
        raise exceptions.FailedRequest(f'returned dit:  {resp_dict}, book id:  {book.id}')
    else:
        raise exceptions.UnknownResponseCode(code, resp_dict['msg'])


async def __chapter_metadata_retriever(book_id: int, chapter_id: int, session: aiohttp.ClientSession = None,
                                       proxy: aiohttp_socks.ProxyConnector = None, return_both: bool = False,
                                       cookies: dict = None, encrypt_type: int = 2,
                                       return_chapter_meta: bool = True) -> Union[dict, Tuple[dict, dict]]:
    """
    Takes a book_id and chapter_id, and returns a dictionary of metadata
    
    :param book_id: int, chapter_id: int, session: aiohttp.ClientSession = None,
    :type book_id: int
    :param chapter_id: int = None,
    :type chapter_id: int
    :param session: aiohttp.ClientSession = None,
    :type session: aiohttp.ClientSession
    :param proxy: aiohttp_socks.ProxyConnector = None,
    :type proxy: aiohttp_socks.ProxyConnector
    :param return_both: bool = False,, defaults to False
    :type return_both: bool (optional)
    :param cookies: dict = None, encrypt_type: int = 2,
    :type cookies: dict
    :param encrypt_type: int = 2,, defaults to 2
    :type encrypt_type: int (optional)
    :param return_chapter_meta: bool = True, defaults to True
    :type return_chapter_meta: bool (optional)
    :return: The chapter metadata and the book metadata.
    """

    """Retrieves the chapter content json
            args:
                :arg return_both will return both type of metadata, if False will return what return_chapter_meta asks
                 for
                :arg return_chapter_meta determines if a it should return the chapter meta or the book meta, will be
                ignored if return_both is True
            """
    # aiohttp_socks.ProxyConnector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True),

    api = '/'.join((API_ENDPOINT_2, 'getContent'))
    params = {'bookId': book_id, 'chapterId': chapter_id, 'encryptType': encrypt_type,
              'font': 'Merriweather', '_': str(time())}
    if not proxy:
        proxy = aiohttp.TCPConnector(**default_connector_settings)

    # retry for the exceptions will happen outside
    if session:
        csrf_token = ''
        for cookie in session.cookie_jar:
            if cookie.key == '_csrfToken':
                csrf_token = cookie.value
        params['_csrfToken'] = csrf_token
        async with session.get(api, params=params) as req:
            resp_bin = await req.read()
    else:
        if cookies:
            params['_csrfToken'] = cookies['_csrfToken']
        else:
            cookies = {}
        async with proxy as connector:
            async with aiohttp.request('GET', api, params=params, connector=connector, cookies=cookies) as resp:
                resp_bin = await resp.read()

    # resp_str = resp_bin.decode()
    # resp_dict = json.loads(resp_str)
    resp_dict = decode_qi_content(resp_bin)
    resp_code = resp_dict['code']
    if resp_code == 0:
        if return_both:
            return resp_dict['data']['chapterInfo'], resp_dict['data']['bookInfo']
        if return_chapter_meta:
            return resp_dict['data']['chapterInfo']
        return resp_dict['data']['bookInfo']
    # TODO: check exceptions codes
    raise exceptions.UnknownResponseCode(resp_code, resp_dict['msg'])


def __full_chapter_parser(book_id: int, chapter_id: int, chapter_info: dict, volume_index: int) -> classes.Chapter:
    """
    Takes a chapter info dict and returns a Chapter object
    
    :param book_id: int
    :type book_id: int
    :param chapter_id: int
    :type chapter_id: int
    :param chapter_info: dict
    :type chapter_info: dict
    :param volume_index: int
    :type volume_index: int
    :return: A Chapter object
    """
    chapter_name = chapter_info['chapterName']
    is_owned = bool(chapter_info['isAuth'])
    notes_dict = chapter_info['notes']
    if notes_dict is None:
        note_obj = None
    else:
        uut = notes_dict['UUT']
        if uut == 0:
            note_obj = None
        else:
            note_avatar_pic_url = notes_dict['avatar']
            note_author = notes_dict['name']
            note_content = notes_dict['note']
            note_author_pen_name = notes_dict['penName']
            note_author_type = notes_dict['role']
            note_obj = classes.ChapterNote(uut, note_avatar_pic_url, note_author, note_content, note_author_pen_name,
                                           note_author_type)
    content_list = chapter_info['contents']
    encrypt_type = chapter_info['encryptType']
    content_str = '\n'.join([paragraph['content'] for paragraph in content_list])
    price = chapter_info['price']
    vip_status = chapter_info['vipStatus']
    priv_level = chapter_info['chapterLevel']
    index = chapter_info['chapterIndex']
    translator_list: list = chapter_info['translatorItems']
    translator = None
    if len(translator_list) > 0:
        translator = translator_list[0]['name']
    editor_list: list = chapter_info['editorItems']
    editor = None
    if len(editor_list) > 0:
        editor = editor_list[0]['name']
    return classes.Chapter(priv_level, chapter_id, book_id, index, vip_status, chapter_name, is_owned, content_str,
                           price, volume_index, encrypt_type, note_obj, editor, translator)


async def full_book_retriever(book_or_book_id: Union[classes.SimpleBook, classes.Book, int],
                              session: aiohttp.ClientSession = None,
                              proxy: Proxy = None) -> classes.Book:
    """
    Retrieves a book's metadata and chapter list, then uses the last chapter's metadata to retrieve
    the book's metadata
    
    :param book_or_book_id: Union[classes.SimpleBook, classes.Book, int]
    :type book_or_book_id: Union[classes.SimpleBook, classes.Book, int]
    :param session: aiohttp.ClientSession = None,
    :type session: aiohttp.ClientSession
    :param proxy: Proxy = None
    :type proxy: Proxy
    :return: A full book object.
    """
    if isinstance(book_or_book_id, int):
        book_or_book_id = classes.SimpleBook(book_or_book_id, '', 0)
    try_attempts = 0
    while True:
        try:
            volumes, chapter_list_book_meta = await chapter_list_retriever(book_or_book_id, session, proxy,
                                                                           return_book=True)
            break
        except json.JSONDecodeError:
            pass
        try_attempts += 1
        if try_attempts > 5:
            raise TimeoutError

    volumes: List[classes.Volume]
    last_volume = volumes[-1]
    last_chapter_range = last_volume.retrieve_volume_ranges(return_first=False, return_missing=False)
    last_chapter = last_volume.retrieve_chapter_by_index(last_chapter_range)

    try_attempts = 0
    while True:
        try:
            if proxy:
                proxy_connector = proxy.generate_connector(**default_connector_settings)
            else:
                proxy_connector = aiohttp.TCPConnector(**default_connector_settings)
            chapter_meta_dict, book_meta_dict = await __chapter_metadata_retriever(book_or_book_id.id, last_chapter.id,
                                                                                   proxy=proxy_connector,
                                                                                   return_both=True)
            break
        except json.JSONDecodeError:
            pass
        try_attempts += 1
        if try_attempts > 5:
            raise TimeoutError
    chapter_list_book_meta: classes.SimpleBook
    last_chapter_volume_index = find_volume_index_from_id(last_chapter.id, volumes)
    last_chapter_obj = __full_chapter_parser(book_or_book_id.id, last_chapter.id, chapter_meta_dict,
                                             last_chapter_volume_index)
    reading_type = last_chapter_obj.is_vip
    book_status = book_meta_dict['actionStatus']
    is_priv = last_chapter.is_privilege
    book_id = book_meta_dict['bookId']
    book_name = book_meta_dict['bookName']
    total_chapters = book_meta_dict['totalChapterNum']
    type_ = book_meta_dict['type']
    cover_id = book_meta_dict['coverUpdateTime']
    if chapter_list_book_meta.qi_abbreviation:
        abbreviation = chapter_list_book_meta.abbreviation
    else:
        abbreviation = None
    full_book = classes.Book(book_id, book_name, total_chapters, is_priv, type_, cover_id, book_status,
                             reading_type=reading_type, book_abbreviation=abbreviation)
    full_book.add_volume_list(volumes)
    return full_book


async def chapter_retriever(book_id: int, chapter_id: int, chapter_volume_index: int, encrypt_type: int = 2,
                            session: aiohttp.ClientSession = None,
                            account: classes.QiAccount = None, proxy: Proxy = None) -> classes.Chapter:
    """
    Retrieves the chapter metadata from the server, and then parses it into a Chapter object
    
    :param book_id: int
    :type book_id: int
    :param chapter_id: int
    :type chapter_id: int
    :param chapter_volume_index: int = 0
    :type chapter_volume_index: int
    :param encrypt_type: int = 2, defaults to 2
    :type encrypt_type: int (optional)
    :param session: aiohttp.ClientSession = None,
    :type session: aiohttp.ClientSession
    :param account: classes.QiAccount = None
    :type account: classes.QiAccount
    :param proxy: Proxy = None
    :type proxy: Proxy
    :return: A chapter object
    """
    cookies = {}
    if hasattr(account, 'cookies'):
        cookies = account.cookies

    try_attempts = 0
    while True:
        try:
            if proxy is None:
                proxy_connector = aiohttp.TCPConnector(**default_connector_settings)
            else:
                proxy_connector = proxy.generate_connector(**default_connector_settings)

            # TODO check after usage what excepts can happen here
            chapter_info = await __chapter_metadata_retriever(book_id, chapter_id, session, proxy_connector,
                                                              cookies=cookies, encrypt_type=encrypt_type)
            break
        except json.JSONDecodeError:
            pass
        try_attempts += 1
        if try_attempts > 5:
            raise TimeoutError

    return __full_chapter_parser(book_id, chapter_id, chapter_info, chapter_volume_index)


async def __chapter_buy_request(book_id: int, chapter_id: int, *, session: aiohttp.ClientSession = None,
                                cookies: dict = None, proxy: Proxy = None, unlock_type: int = 5, chapter_type: int = 2,
                                chapter_price: int = 1) -> str:
    """
    Takes a book_id and chapter_id and returns the chapter content.
    
    :param book_id: int, chapter_id: int, *, session: aiohttp.ClientSession = None, cookies: dict =
    None, proxy: Proxy = None, unlock_type: int = 5, chapter_type: int = 2, chapter_price: int = 1
    :type book_id: int
    :param chapter_id: int = chapter id
    :type chapter_id: int
    :param session: aiohttp.ClientSession = None,
    :type session: aiohttp.ClientSession
    :param cookies: dict = None, proxy: Proxy = None, unlock_type: int = 5, chapter_type: int = 2,
    :type cookies: dict
    :param proxy: Proxy = None
    :type proxy: Proxy
    :param unlock_type: 5 is fastpass, 2 is spirit stone, defaults to 5
    :type unlock_type: int (optional)
    :param chapter_type: 2 is for normal chapters, 3 is for vip chapters, defaults to 2
    :type chapter_type: int (optional)
    :param chapter_price: int = 1, defaults to 1
    :type chapter_price: int (optional)
    :return: The chapter content and the encryption type
    """
    """Will buy a chapter with fastpass unless the rest of the data are modified    """
    # api_url = 'https://www.webnovel.com/apiajax/SpiritStone/useSSAjax'
    api_url = 'https://www.webnovel.com/go/pcm/book/unlockChapter'

    # _connector: aiohttp_socks.ProxyConnector =
    # aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)

    # check to see if the csrftken can be extracted from a session

    if cookies:
        csrf_token = cookies['_csrfToken']
    else:
        csrf_token = ''
        for cookie in session.cookie_jar:
            if cookie.key == '_csrfToken':
                csrf_token = cookie.value
    form_data_dict = {'_csrfToken': csrf_token, 'bookId': book_id, 'chapterId': chapter_id, 'price': 1,
                      'unlockType': unlock_type}

    form_data = aiohttp.FormData(form_data_dict)
    # form_data.add_field('chapters', [{'chapterPrice': chapter_price, 'chapterId': chapter_id,
    #                                   'chapterType': chapter_type}])

    try_attempts = 0
    if session:
        while True:
            try:
                async with session.post(api_url, data=form_data) as req:
                    content_dict = decode_qi_content(await req.read())
                    break
            except json.JSONDecodeError:
                pass
            try_attempts += 1
            if try_attempts > 5:
                raise TimeoutError

    else:
        while True:
            try:
                if proxy:
                    proxy_connector = proxy.generate_connector(**default_connector_settings)
                else:
                    proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

                async with proxy_connector as connector:
                    async with aiohttp.request('POST', api_url, data=form_data, cookies=cookies,
                                               connector=connector) as req:
                        content_dict = decode_qi_content(await req.read())
                        break
            except json.JSONDecodeError:
                pass
            try_attempts += 1
            if try_attempts > 5:
                raise TimeoutError
    request_code = content_dict['code']

    # code 0 is success | code 2 is already bought | code 1 is fail or possibly insufficient fp/ss
    if request_code == 0:
        data = content_dict['data']
        paragraphs_list = data['content']
        return '\n'.join([paragraph_dict['content'] for paragraph_dict in paragraphs_list]), data['encryptType']
    if request_code == 1:
        raise exceptions.ChapterBuyFailed()
    elif request_code == 2:
        raise exceptions.ChapterAlreadyBought()
    else:
        raise exceptions.UnknownResponseCode(request_code, content_dict['msg'])


async def chapter_buyer(book_id: int, chapter_id: int, session: aiohttp.ClientSession = None,
                        account: classes.QiAccount = None, proxy: Proxy = None, *, use_ss=False) -> classes.Chapter:
    """
    Takes a book_id and a chapter_id, and returns a Chapter object
    
    :param book_id: int, chapter_id: int, session: aiohttp.ClientSession = None,
    :type book_id: int
    :param chapter_id: int = the chapter id
    :type chapter_id: int
    :param session: aiohttp.ClientSession = None,
    :type session: aiohttp.ClientSession
    :param account: classes.QiAccount = None, proxy: Proxy = None, *, use_ss=False
    :type account: classes.QiAccount
    :param proxy: Proxy = None
    :type proxy: Proxy
    :param use_ss: boolean, whether to use shadowsocks or not, defaults to False (optional)
    :return: The chapter object
    """
    if account is None and session is None:
        raise ValueError("Missing either account or session as a parameter")
    # volumes = await chapter_list_retriever(book_id, session=session, proxy=proxy)
    # chapter_volume_index = find_volume_index_from_id(chapter_id, volumes)

    # TODO check what possible excepts can happen here
    chapter = await chapter_retriever(book_id, chapter_id, 0,
                                      session=session, account=account, proxy=proxy)
    if chapter.is_full_content is False:
        if session:
            chapter.content, chapter.encrypt_type = await __chapter_buy_request(book_id, chapter_id,
                                                                                session=session, proxy=proxy)
        else:
            chapter.content, chapter.encrypt_type = await __chapter_buy_request(book_id, chapter_id,
                                                                                session=session,
                                                                                cookies=account.cookies, proxy=proxy)
        chapter.is_full_content = True
    if chapter.encrypt_type == 3:
        chapter = await chapter_retriever(chapter.parent_id, chapter_id, chapter.volume_index, account=account)
    return chapter
