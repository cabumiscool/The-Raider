import aiohttp
import aiohttp_socks
import typing
import json
from time import time
from dependencies.webnovel import classes, exceptions
from dependencies.proxy_manager import Proxy
from dependencies.webnovel.utils import decode_qi_content

main_api = 'https://www.webnovel.com/apiajax/chapter'

# possible_second_api = 'https://www.webnovel.com/go/pcm/chapter/getContent'

# TODO change the input from the proxy connector to the proxy class where required


async def chapter_list_retriever(book: classes.SimpleBook, session: aiohttp.ClientSession = None,
                                 proxy: aiohttp_socks.ProxyConnector =
                                 aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)
                                 ) -> typing.List[classes.Volume]:
    """Add an item to the library
        :arg book receives either a book or a comic object to be added to the library
        :arg session receives an aiohttp session object that includes the cookies of the account, if empty will use the
            account arg to generate a request
        :arg proxy accepts an aiohttp proxy connector object, will be ignored if session is given
        :returns a list containing Volume objects
    """
    params = {'bookId': str(book.id), '_': time()}
    api = '/'.join((main_api, 'GetChapterList'))
    try:
        if session is None:
            # TODO check if it is possible to retrieve a specific cookie from the session
            async with aiohttp.request('GET', api, params=params, connector=proxy) as req:
                resp_bin = await req.read()
                resp_str = resp_bin.decode()
                resp_dict = json.loads(resp_str)
        else:
            async with session.get(api, params=params) as req:
                resp_bin = await req.read()
                resp_str = resp_bin.decode()
                resp_dict = json.loads(resp_str)
    except:
        # TODO analyze what exceptions can here paying special attention to the exceptions that happen when proxy
        #  is used
        pass
    code = resp_dict['code']
    if code == 0:
        # successful request
        book_metadata = resp_dict['bookInfo']
        book_name = book_metadata['bookName']
        book_sub_name = book_metadata['bookSubName']
        volumes_dict = resp_dict['volumeItems']
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
                                                      chapter_name))
            volumes.append(classes.Volume(chapters, volume_index, book.id, volume_name))
        return volumes
    elif code == 1:
        # TODO check if 1 is error and log the error to database for later review
        pass
    else:
        exceptions.UnknownResponseCode(code, resp_dict['msg'])


async def __chapter_metadata_retriever(book_id: int, chapter_id: int, session: aiohttp.ClientSession = None,
                                       proxy_connector: aiohttp_socks.ProxyConnector =
                                       aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True),
                                       cookies: dict = None, return_chapter_meta: bool = True) -> dict:
    """Retrieves the chapter content json"""
    api = '/'.join((main_api, 'GetContent'))
    params = {'bookId': book_id, 'chapterId': chapter_id, '_': time()}
    if session:
        # TODO check if a cookie can be retrieved from the session
        async with session.get(api, params=params) as req:
            resp_bin = await req.read()
    else:
        if cookies:
            params['_csrfToken'] = cookies['_csrfToken']
        else:
            cookies = {}
        async with aiohttp.request('GET', api, params=params, connector=proxy_connector, cookies=cookies) as resp:
            resp_bin = await resp.read()
    resp_str = resp_bin.decode()
    resp_dict = json.loads(resp_str)
    resp_code = resp_dict['code']
    if resp_code == 0:
        if return_chapter_meta:
            return resp_dict['data']['chapterInfo']
        else:
            return resp_dict['data']['bookInfo']
    else:
        # TODO check exceptions codes
        raise exceptions.UnknownResponseCode(resp_code, resp_dict['msg'])


async def chapter_retriever(book_id: int, chapter_id: int,
                            session: aiohttp.ClientSession = None, account: classes.Account = None,
                            proxy: Proxy = None) -> classes.Chapter:
    if account is None:
        cookies = {}
    else:
        cookies = account.cookies
    if proxy is None:
        proxy_connector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)
    else:
        proxy_connector = proxy.generate_connector(force_close=True, enable_cleanup_closed=True)

    # TODO check after usage what excepts can happen here
    chapter_info = await __chapter_metadata_retriever(book_id, chapter_id, session, proxy_connector, cookies)

    chapter_name = chapter_info['chapterName']
    is_owned = bool(chapter_info['isAuth'])
    notes_dict = chapter_info['notes']
    uut = notes_dict['UUT']
    if uut is 0:
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
    price = chapter_info['price']
    vip_status = chapter_info['vipStatus']
    priv_level = chapter_info['chapterLevel']
    index = chapter_info['chapterIndex']
    translator_list: list = chapter_info['translatorItems']
    if len(translator_list) == 0:
        translator = None
    else:
        translator = translator_list[0]['name']
    editor_list: list = chapter_info['editorItems']
    if len(editor_list) == 0:
        editor = None
    else:
        editor = editor_list[0]['name']
    return classes.Chapter(priv_level, chapter_id, book_id, index, vip_status, chapter_name, is_owned, content_str,
                           price, note_obj, editor, translator)


async def __chapter_buy_request(book_id: int, chapter_id: int, *, session: aiohttp.ClientSession = None,
                                cookies: dict = None, proxy_connector: aiohttp_socks.ProxyConnector =
                                aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True),
                                unlock_type: int = 5, chapter_type: int = 2, chapter_price: int = 1):
    """Will buy a chapter with fastpass unless the rest of the data are modified    """
    api_url = 'https://www.webnovel.com/apiajax/SpiritStone/useSSAjax'

    # check to see if the csrftken can be extracted from a session
    form_data_dict = {'bookId': book_id, 'unlockType': unlock_type}
    if cookies:
        form_data_dict['_csrfToken'] = cookies['_csrfToken']
    else:
        if session:
            pass

    form_data = aiohttp.FormData(form_data_dict)
    form_data.add_field('chapters', [{'chapterPrice': chapter_price, 'chapterId': chapter_id,
                                      'chapterType': chapter_type}])

    if session:
        async with session.post(api_url, data=form_data) as req:
            content_dict = decode_qi_content(await req.read())
    else:
        async with aiohttp.request('POST', api_url, data=form_data, cookies=cookies, connector=proxy_connector) as req:
            content_dict = decode_qi_content(await req.read())
    request_code = content_dict['code']

    # code 0 is success | code 2 is already bought | code 1 is fail or possibly insufficient fp/ss
    if request_code == 0:
        data = content_dict['data']
        paragraphs_dict = content_dict['contents']
        return '\n'.join([paragraph['content'] for paragraph in paragraphs_dict])
    elif request_code == 1:
        raise exceptions.FailedChapterBuy()
    elif request_code == 2:
        raise exceptions.AlreadyBoughtChapter()
    else:
        raise exceptions.UnknownResponseCode(request_code, content_dict['msg'])


async def chapter_buyer(book_id: int, chapter_id: int, session: aiohttp.ClientSession = None,
                        account: classes.Account = None, proxy: Proxy = None, *, use_ss=False) -> classes.Chapter:
    cookies = None
    if account is not None:
        cookies = account.cookies

    if proxy is None:
        proxy_connector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)
    else:
        proxy_connector = proxy.generate_connector(force_close=True, enable_cleanup_closed=True)

    # TODO check what possible excepts can happen here
    chapter = await chapter_retriever(book_id, chapter_id, session, account, proxy)
    if chapter.is_preview:
        chapter.content = await __chapter_buy_request(book_id, chapter_id, session=session, cookies=cookies,
                                                      proxy_connector=proxy_connector)
        chapter.is_preview = False
    else:
        return chapter
