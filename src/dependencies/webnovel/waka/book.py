import aiohttp

# import aiohttp_socks
# import asyncio
from dependencies.proxy_classes import Proxy
from .. import classes
from ..exceptions import UnknownResponseCode
from ..utils import decode_qi_content

API_ENDPOINT = 'https://m.ficool.com/app/api/book'

default_connector_settings = {'force_close': True, 'enable_cleanup_closed': True}


# TODO study if the following methods exist on waka api
async def chapter_list_retriever():
    pass


async def full_book_retriever():
    pass


async def chapter_retriever(book_id: int, chapter_id: int, volume_index: int, session: aiohttp.ClientSession = None,
                            proxy: Proxy = None):
    api = '/'.join((API_ENDPOINT, 'chapter'))
    params = {'bookId': str(book_id), 'chapterId': str(chapter_id)}

    if session:
        async with session.get(api, params=params) as request:
            data_dict = decode_qi_content(await request.read())

    else:
        if proxy:
            proxy_connector = proxy.generate_connector(**default_connector_settings)
            async with aiohttp.request('GET', api, params=params, connector=proxy_connector) as request:
                data_dict = decode_qi_content(await request.read())
        else:
            raise ValueError("Neither a session object or a proxy object was given. One of either is necessary")

    request_code = data_dict['result']

    if request_code != 0:
        message = data_dict['message']
        raise UnknownResponseCode(request_code, message)

    dict_content = data_dict['data']

    chapter_dict_content: dict
    chapter_dict_content = dict_content['chapter']
    vip_status = chapter_dict_content['lockType']  # probably the equivalent of vip status in qi data
    name = chapter_dict_content['name']
    index = chapter_dict_content['index']
    price = chapter_dict_content['price']
    content = chapter_dict_content['content']
    has_rich_content = chapter_dict_content['hasRichContent']
    extra_note = chapter_dict_content.get('extraWords', None)

    # For Formatting plain text chapters
    if has_rich_content != 1:
        content = content.replace("\r\n", "</p>\n<p>")
        content = f"<p>{content}</p>"

    try:
        editors = '/'.join(chapter_dict_content['editors'])
    except TypeError:
        editors = f"{chapter_dict_content['editors']} | value couldn't be parsed... tell a dev!"
    try:
        translators = '/'.join(chapter_dict_content['translators'])
    except TypeError:
        translators = f"{chapter_dict_content['translators']} | value couldn't be parsed... tell a dev!"

    chapter_note = classes.ChapterNote(0, '', '', extra_note, '', '')

    return classes.Chapter(1, chapter_id, book_id, index, vip_status, name, True, content, price, volume_index,
                           chapter_note, editors, translators)
