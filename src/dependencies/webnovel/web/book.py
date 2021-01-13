import json
from typing import List, Union, Tuple
from time import time

import aiohttp
import aiohttp_socks

from dependencies.proxy_classes import Proxy
from dependencies.webnovel import classes, exceptions
from dependencies.webnovel.utils import decode_qi_content

API_ENDPOINT = 'https://www.webnovel.com/apiajax/chapter'


default_connector_settings = {'force_close': True, 'enable_cleanup_closed': True}

# possible_second_api = 'https://www.webnovel.com/go/pcm/chapter/getContent'

# TODO change the input from the proxy connector to the proxy class where required


def find_volume_index_from_id(chapter_id, volumes: List[classes.Volume]) -> int:
    for volume in volumes:
        if volume.check_if_id_in_volume(chapter_id):
            volume_index = volume.index
            break
    else:
        volume_index = 0
    return volume_index


async def __chapter_list_retriever_call(params: dict, api_endpoint: str, session: aiohttp.ClientSession = None,
                                        proxy_connector: aiohttp_socks.ProxyConnector = None):
    if session is None:
        # TODO check if it is possible to retrieve a specific cookie from the session and csrf to the params

        if not proxy_connector:
            proxy_connector = aiohttp.TCPConnector()

        async with aiohttp.request('GET', api_endpoint, params=params, connector=proxy_connector) as req:
            resp_dict = decode_qi_content(await req.read())
    else:
        async with session.get(api_endpoint, params=params) as req:
            resp_dict = decode_qi_content(await req.read())

    return resp_dict


async def chapter_list_retriever(book: Union[classes.SimpleBook, int], session: aiohttp.ClientSession = None,
                                 proxy: Proxy = None, return_book: bool = False
                                 ) -> Union[List[classes.Volume], Tuple[List[classes.Volume], classes.SimpleBook]]:
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
    api = '/'.join((API_ENDPOINT, 'GetChapterList'))
    while True:
        try:
            proxy_connector = None
            if proxy:
                proxy_connector = proxy.generate_connector()

            resp_dict = await __chapter_list_retriever_call(params, api, session,  proxy_connector=proxy_connector)
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
        book_sub_name = book_metadata['bookSubName']
        total_chapters = book_metadata['totalChapterNum']
        volumes_dict = data_message['volumeItems']
        simple_book = classes.SimpleBook(book.id, book_name, total_chapters, book_abbreviation=book_sub_name)
        volumes = []
        for volume in volumes_dict:
            chapters = []
            volume_index = volume['index']
            volume_name = volume['name']
            chapters_list = volume['chapterItems']
            for chapter in chapters_list:
                chapter_level = chapter['chapterLevel']
                chapter_id = chapter['id']
                chapter_index = chapter['index']
                chapter_vip = chapter['isVip']
                chapter_name = chapter['name']
                chapters.append(classes.SimpleChapter(chapter_level, chapter_id, book.id, chapter_index, chapter_vip,
                                                      chapter_name, volume_index))
            volumes.append(classes.Volume(chapters, volume_index, book.id, volume_name))
        if return_book:
            return volumes, simple_book
        return volumes
    if code == 1:
        # TODO check if 1 is error and log the error to database for later review
        raise exceptions.FailedRequest(f'returned dit:  {resp_dict}')
    else:
        raise exceptions.UnknownResponseCode(code, resp_dict['msg'])


async def __chapter_metadata_retriever(book_id: int, chapter_id: int, session: aiohttp.ClientSession = None,
                                       proxy: aiohttp_socks.ProxyConnector = None, return_both: bool = False,
                                       cookies: dict = None,
                                       return_chapter_meta: bool = True) -> Union[dict, Tuple[dict, dict]]:
    """Retrieves the chapter content json
            args:
                :arg return_both will return both type of metadata, if False will return what return_chapter_meta asks
                 for
                :arg return_chapter_meta determines if a it should return the chapter meta or the book meta, will be
                ignored if return_both is True
            """
    # aiohttp_socks.ProxyConnector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True),

    api = '/'.join((API_ENDPOINT, 'GetContent'))
    params = {'bookId': book_id, 'chapterId': chapter_id, '_': str(time())}
    if not proxy:
        proxy = aiohttp.TCPConnector()

    # retry for the exceptions will happen outside
    if session:
        # TODO check if a cookie can be retrieved from the session
        async with session.get(api, params=params) as req:
            resp_bin = await req.read()
    else:
        if cookies:
            params['_csrfToken'] = cookies['_csrfToken']
        else:
            cookies = {}
            async with aiohttp.request('GET', api, params=params, connector=proxy, cookies=cookies) as resp:
                resp_bin = await resp.read()

    resp_str = resp_bin.decode()
    resp_dict = json.loads(resp_str)
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
    content_str = '\n'.join([paragraph['content'] for paragraph in content_list])
    price = chapter_info['SSPrice']
    vip_status = chapter_info['isVip']
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
                           price, volume_index, note_obj, editor, translator)


async def full_book_retriever(book_or_book_id: Union[classes.SimpleBook, classes.Book, int], session: aiohttp.ClientSession = None,
                              proxy: Proxy = None):
    if isinstance(book_or_book_id, int):
        book_or_book_id = classes.SimpleBook(book_or_book_id, '', 0)
    while True:
        try:
            volumes, chapter_list_book_meta = await chapter_list_retriever(book_or_book_id, session, proxy, return_book=True)
            break
        except json.JSONDecodeError:
            pass

    volumes: List[classes.Volume]
    last_volume = volumes[-1]
    last_chapter_range = last_volume.retrieve_volume_ranges(return_first=False, return_missing=False)
    last_chapter = last_volume.retrieve_chapter_by_index(last_chapter_range)

    while True:
        try:
            if proxy:
                proxy_connector = proxy.generate_connector()
            else:
                proxy_connector = aiohttp.TCPConnector()
            chapter_meta_dict, book_meta_dict = await __chapter_metadata_retriever(book_or_book_id.id, last_chapter.id,
                                                                                   proxy=proxy_connector,
                                                                                   return_both=True)
            break
        except json.JSONDecodeError:
            pass
    chapter_list_book_meta: classes.SimpleBook
    last_chapter_volume_index = find_volume_index_from_id(last_chapter.id, volumes)
    last_chapter_obj = __full_chapter_parser(book_or_book_id.id, last_chapter.id, chapter_meta_dict, last_chapter_volume_index)
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


async def chapter_retriever(book_id: int, chapter_id: int, chapter_volume_index: int,
                            session: aiohttp.ClientSession = None,
                            account: classes.QiAccount = None, proxy: Proxy = None) -> classes.Chapter:
    cookies = {}
    if hasattr(account, 'cookies'):
        cookies = account.cookies

    while True:
        try:
            if proxy is None:
                proxy_connector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)
            else:
                proxy_connector = proxy.generate_connector(force_close=True, enable_cleanup_closed=True)

            # TODO check after usage what excepts can happen here
            chapter_info = await __chapter_metadata_retriever(book_id, chapter_id, session, proxy_connector,
                                                              cookies=cookies)
            break
        except json.JSONDecodeError:
            pass

    return __full_chapter_parser(book_id, chapter_id, chapter_info, chapter_volume_index)


async def __chapter_buy_request(book_id: int, chapter_id: int, *, session: aiohttp.ClientSession = None,
                                cookies: dict = None, proxy: Proxy = None, unlock_type: int = 5, chapter_type: int = 2,
                                chapter_price: int = 1) -> str:
    """Will buy a chapter with fastpass unless the rest of the data are modified    """
    api_url = 'https://www.webnovel.com/apiajax/SpiritStone/useSSAjax'

    # _connector: aiohttp_socks.ProxyConnector =
    # aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)

    # check to see if the csrftken can be extracted from a session
    form_data_dict = {'bookId': book_id, 'unlockType': unlock_type}
    if cookies:
        form_data_dict['_csrfToken'] = cookies['_csrfToken']
    else:
        # TODO: Why does this exists? it does nothing

        # RESPONSE: I forgot to continue writing it XD, should retrieve the csrf cookie from the seesion and do the
        # same as above
        # TODO do as above
        pass

    form_data = aiohttp.FormData(form_data_dict)
    form_data.add_field('chapters', [{'chapterPrice': chapter_price, 'chapterId': chapter_id,
                                      'chapterType': chapter_type}])

    if session:
        while True:
            try:
                async with session.post(api_url, data=form_data) as req:
                    content_dict = decode_qi_content(await req.read())
            except json.JSONDecodeError:
                continue
            break
    else:
        while True:
            try:
                if proxy:
                    proxy_connector = proxy.generate_connector(force_close=True, enable_cleanup_closed=True)
                else:
                    proxy_connector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)

                async with aiohttp.request('POST', api_url, data=form_data, cookies=cookies,
                                           connector=proxy_connector) as req:
                    content_dict = decode_qi_content(await req.read())
            except json.JSONDecodeError:
                continue
            break
    request_code = content_dict['code']

    # code 0 is success | code 2 is already bought | code 1 is fail or possibly insufficient fp/ss
    if request_code == 0:
        data = content_dict['data']
        paragraphs_dict = data['contents']
        return '\n'.join([paragraph['content'] for paragraph in paragraphs_dict])
    if request_code == 1:
        raise exceptions.FailedChapterBuy()
    elif request_code == 2:
        raise exceptions.AlreadyBoughtChapter()
    else:
        raise exceptions.UnknownResponseCode(request_code, content_dict['msg'])


async def chapter_buyer(book_id: int, chapter_id: int, session: aiohttp.ClientSession = None,
                        account: classes.QiAccount = None, proxy: Proxy = None, *, use_ss=False) -> classes.Chapter:
    cookies = None
    if hasattr(account, 'cookies'):
        cookies = account.cookies
    volumes = await chapter_list_retriever(book_id, session=session, proxy=proxy)
    chapter_volume_index = find_volume_index_from_id(chapter_id, volumes)

    # TODO check what possible excepts can happen here
    chapter = await chapter_retriever(book_id, chapter_id, chapter_volume_index,
                                      session=session, account=account, proxy=proxy)
    if chapter.is_preview:
        chapter.content = await __chapter_buy_request(book_id, chapter_id, session=session, cookies=cookies,
                                                      proxy=proxy)
        chapter.is_preview = False
    return chapter
