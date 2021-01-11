import aiohttp
# import aiohttp_socks
# import asyncio
from dependencies.proxy_classes import Proxy
from dependencies.webnovel import classes
from dependencies.webnovel.utils import decode_qi_content
from dependencies.webnovel.exceptions import UnknownResponseCode

API_ENDPOINT = 'https://m.ficool.com/app/api/book'


# TODO study if the following methods exist on waka api
async def chapter_list_retriever():
    pass


async def full_book_retriever():
    pass


async def chapter_retriever(book_id: int, chapter_id: int, session: aiohttp.ClientSession = None, proxy: Proxy = None):
    api = '/'.join((API_ENDPOINT, 'chapter'))
    params = {'bookId': book_id, 'chapterId': chapter_id}

    if session:
        async with session.get(api, params=params) as request:
            data_dict = decode_qi_content(await request.read())

    else:
        if proxy:
            proxy_connector = proxy.generate_connector()
            async with aiohttp.request('GET', api, params=params, connector=proxy_connector) as request:
                data_dict = decode_qi_content(await request.read())
        else:
            raise ValueError("Neither a session object or a proxy object was given. One of either is necessary")

    request_code = data_dict['result']

    if request_code != 0:
        message = data_dict['message']
        raise UnknownResponseCode(request_code, message)

    dict_content = data_dict['data']
    index = dict_content['index']

    chapter_dict_content = dict_content['chapter']
    vip_status = chapter_dict_content['lockType']  # probably the equivalent of vip status in qi data
    name = chapter_dict_content['name']
    content = chapter_dict_content['content']
    price = chapter_dict_content['price']
    chapter_dict_content: dict
    extra_note = chapter_dict_content.get('extraWords', None)
    editors = '/'.join(chapter_dict_content['editors'])
    translators = '/'.join(chapter_dict_content['translators'])

    chapter_note = classes.ChapterNote(0, '', '', extra_note, '', '')

    return classes.Chapter(1, chapter_id, book_id, index, vip_status, name, True, content, price, chapter_note,
                           editors, translators)