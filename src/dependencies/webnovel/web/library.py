import asyncio
import aiohttp
import aiohttp_socks
import typing
import json
from urllib.parse import quote
from dependencies.webnovel import classes
from dependencies.proxy_manager import Proxy

main_api_url = "https://www.webnovel.com/apiajax/Library"


# TODO compact most of the request making code

# TODO deal with the connector to be able to self close or something... Needs further thinking

def __request_data_generator(session: aiohttp.ClientSession, account: classes.QiAccount) -> (bool, dict):
    """Returns the initial return values indicates if a session should be used the other is the payload data"""
    if session is None and account is None:
        raise ValueError(f"No valid value was passed to either session or account")
    # TODO: Ask bum why only csrf token is being sent.
    if session:
        assert isinstance(session, aiohttp.ClientSession)
        csrf_token = ''
        for cookie in session.cookie_jar:
            if cookie.key == '_csrfToken':
                csrf_token = cookie.value
        return True, {'_csrfToken': csrf_token}

    elif account:
        assert isinstance(account, classes.QiAccount)
        return False, {'_csrfToken': account.cookies['_csrfToken']}


def __parse_library_page(library_page_list: typing.List[dict]) -> typing.List[typing.Union[classes.SimpleBook,
                                                                                           classes.SimpleComic]]:
    items = []
    for item in library_page_list:
        type_ = item['novelType']
        if type_ == 0:
            book_obj = classes.SimpleBook(item['bookId'], item['bookName'], item['totalChapterNum'],
                                          item['coverUpdateTime'])
            items.append(book_obj)
        elif type_ == 100:
            comic_obj = classes.SimpleComic(item['bookId'], item['comicName'], item['coverUpdateTime'],
                                            item['newChapterIndex'])
            items.append(comic_obj)
        else:
            raise ValueError(f"Unknown item type found {item}")
    return items


async def retrieve_library_page(page_index: int = 1, session: aiohttp.ClientSession = None,
                                account: classes.QiAccount = None, proxy: Proxy = None) -> (
        typing.Tuple[typing.List[typing.Union[classes.SimpleBook, classes.SimpleComic]]], bool):
    """Retrieves a page from the library
        :arg page_index is the page number that will be requested from the library
        :arg session receives a session object from aiohttp that already contains the cookies for the respective
            account
        :arg account receives an account object, will be ignored if a session object is given; if a session object is
            not given it will use the account object to generate a request
        :arg proxy accepts an aiohhtp proxy connector object, will be ignored if session is given
        :returns a tuple containing a list which containing a dict for every book present in the library page and a
            bool representing if this is the last page on the library
    """

    # aiohttp_socks.ProxyConnector =
    # aiohttp.TCPConnector(force_close=True)
    api_url = '/'.join([main_api_url, 'LibraryAjax'])
    use_session, payload_data = __request_data_generator(session, account)
    payload_data['pageIndex'] = page_index
    payload_data['orderBy'] = 2
    while True:
        try:

            if proxy:
                proxy_connector = proxy.generate_connector()
            else:
                proxy_connector = aiohttp.TCPConnector()

            if use_session:
                async with session.post(api_url, data=payload_data) as req:
                    response_bin = await req.read()
                    response_str = response_bin.decode()
                    response = json.loads(response_str)
            else:
                async with aiohttp.request('POST', api_url, data=payload_data, cookies=account.cookies,
                                           connector=proxy_connector) as req:
                    response_bin = await req.read()
                    response_str = response_bin.decode()
                    response = json.loads(response_str)
        except json.JSONDecodeError:
            pass
        else:
            break
    result = response['code']
    req_data = response['data']
    req_books = response['books']
    assert isinstance(req_books, list)
    if result == 0:
        is_last_page = bool(req_data['isLast'])
        parsed_items = __parse_library_page(req_books)
        return parsed_items, is_last_page
    elif result == 1006:
        raise Exception(F"Unknown error")
    else:
        raise ValueError(f"Unknown value of {result} as a response")


async def retrieve_all_library_pages(session: aiohttp.ClientSession = None, account: classes.QiAccount = None,
                                     proxy: Proxy = None) -> \
        typing.Tuple[typing.List[typing.Union[classes.SimpleBook, classes.SimpleComic]], int]:
    """Will retrieve all library items associated with the account"""
    page = 1
    items = []
    if session:
        if account:
            tasks = []
            page = account.library_pages
            for page in range(1, account.library_pages + 1):
                tasks.append(asyncio.create_task(retrieve_library_page(page, session)))
            results = await asyncio.gather(*tasks)
            for item_list, last_page in results:
                item_list: list
                last_page: bool
                items.extend(item_list)
        else:
            while True:
                items_list, is_last_page = await retrieve_library_page(page, session)
                items.extend(items_list)
                if is_last_page:
                    break
                else:
                    page += 1
    else:
        if account:
            page = account.library_pages
            if proxy:
                tasks = []
                proxy_connector = proxy.generate_connector()
                async with aiohttp.ClientSession(connector=proxy_connector, cookies=account.cookies) as session:
                    for page in range(1, account.library_pages+1):
                        tasks.append(asyncio.create_task(retrieve_library_page(page, session)))
                    results = await asyncio.gather(*tasks)
                    for item_list, last_page in results:
                        item_list: list
                        last_page: bool
                        items.extend(item_list)
            else:
                tasks = []
                async with aiohttp.ClientSession(cookies=account.cookies) as session:
                    for page in range(1, account.library_pages + 1):
                        tasks.append(asyncio.create_task(retrieve_library_page(page, session)))
                    results = await asyncio.gather(*tasks)
                    for item_list, last_page in results:
                        item_list: list
                        last_page: bool
                        items.extend(item_list)
        else:
            raise ValueError("No valid data was given")

        return items, page


async def add_item_to_library(item: typing.Union[typing.Type[classes.SimpleBook], typing.Type[classes.SimpleComic]],
                              session: aiohttp.ClientSession = None, account: classes.QiAccount = None,
                              proxy: Proxy = None) -> bool:
    """Add an item to the library
        :arg item receives either a book or a comic object to be added to the library
        :arg session receives an aiohttp session object that includes the cookies of the account, if empty will use the
        account arg to generate a request
        :arg account receives an account object to generate a request with it, will be ignored if a session object is
        given
        :arg proxy accepts an aiohhtp proxy connector object, will be ignored if session is given

        :returns a bool value representing if the request was completed successfully
    """

    assert issubclass(type(item), (classes.SimpleBook, classes.SimpleComic)) or isinstance(item, (classes.SimpleBook,
                                                                                            classes.SimpleComic))

    use_session, payload_data = __request_data_generator(session, account)
    payload_data['bookIds'] = item.id
    payload_data['novelType'] = item.NovelType
    # add_data = {'_csrfToken': csrf, 'bookIds': item_id, 'novelType': type_}
    api_url = '/'.join((main_api_url, 'AddLibraryItemsAjax'))
    while True:
        try:
            if proxy:
                proxy_connector = proxy.generate_connector()
            else:
                proxy_connector = aiohttp.TCPConnector()
            if use_session:
                async with session.post(api_url, data=payload_data) as req:
                    response_bin = await req.read()
                    response_str = response_bin.decode()
                    response = json.loads(response_str)
            else:
                async with aiohttp.request('POST', api_url, data=payload_data, cookies=account.cookies,
                                           connector=proxy_connector) as req:
                    response_bin = await req.read()
                    response_str = response_bin.decode()
                    response = json.loads(response_str)
        except json.JSONDecodeError:
            pass
        else:
            break
    result = response['code']
    if result == 0:
        return True
    elif result == 1006:
        raise Exception(F"Unknown error")
    else:
        raise ValueError(f"Unknown value of {result} as a response")


async def remove_item_from_library(item: typing.Union[classes.SimpleBook, classes.SimpleComic],
                                   session: aiohttp.ClientSession = None, account: classes.QiAccount = None,
                                   proxy: Proxy = None) -> bool:
    """Removes an item from the library
        :arg item receives either a book or a comic object to be added to the library
        :arg session receives an aiohttp session object that includes the cookies of the account, if empty will use the
            account arg to generate a request
        :arg account receives an account object to generate a request with it, will be ignored if a session object is
            given
        :arg proxy accepts a Proxy object, will be ignored if session is given

        :returns a bool value representing if the request was completed successfully
    """
    supported_types = (classes.SimpleBook, classes.SimpleComic)
    assert issubclass(type(item), supported_types) or isinstance(item, supported_types)
    use_session, payload_data = __request_data_generator(session, account)
    full_data = {**payload_data, 'bookItems': '[{"bookId":"%s","novelType":%s}]' % (item.id, item.NovelType)}
    api_url = '/'.join((main_api_url, 'DeleteLibraryItemsAjax'))
    string = "&".join([f'{key}={value}' for key, value in full_data.items()])
    string.replace(' ', '')
    encoded_string = quote(string, encoding='UTF-8', safe='&=')
    # api_url = 'https://httpbin.org/post'
    while True:
        try:
            if use_session:
                async with session.post(api_url, data=encoded_string,
                                        headers={'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}) as req:
                    response_bin = await req.read()
                    response_str = response_bin.decode()
                    response = json.loads(response_str)
            else:
                if proxy:
                    proxy_connector = proxy.generate_connector()
                else:
                    proxy_connector = aiohttp.TCPConnector()
                async with aiohttp.request('Post', api_url, data=encoded_string, cookies=account.cookies,
                                           connector=proxy_connector,
                                           headers={'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}) as req:
                    response_bin = await req.read()
                    response_str = response_bin.decode()
                    response = json.loads(response_str)
        except json.JSONDecodeError:
            pass
        else:
            break
    result = response['code']
    if result == 0:
        return True
    elif result == 1006:
        raise Exception(F"Unknown error")
    else:
        raise ValueError(f"Unknown value of {result} as a response")


async def batch_remove_books_from_library(*items: typing.Union[classes.SimpleBook,
                                                               classes.SimpleComic],
                                          session: aiohttp.ClientSession = None, account: classes.QiAccount = None,
                                          proxy: Proxy = None) -> bool:

    supported_types = (classes.SimpleBook, classes.SimpleComic)
    use_session, payload_data = __request_data_generator(session, account)
    items_dict_string = []
    for item in items:
        try:
            assert issubclass(type(item), supported_types) or isinstance(item, supported_types)
        except AssertionError:
            continue
        items_dict_string.append('{"bookId":"%s","novelType":%s}' % (item.id, item.NovelType))

    full_data = {**payload_data, 'bookItems': f'[{",".join(items_dict_string)}]'}
    # full_data = {**payload_data, 'bookItems': '[{"bookId":"%s","novelType":%s}]' % (item.id, item.NovelType)}
    api_url = '/'.join((main_api_url, 'DeleteLibraryItemsAjax'))
    string = "&".join([f'{key}={value}' for key, value in full_data.items()])
    string.replace(' ', '')
    encoded_string = quote(string, encoding='UTF-8', safe='&=')
    # api_url = 'https://httpbin.org/post'

    while True:
        try:
            if use_session:
                async with session.post(api_url, data=encoded_string,
                                        headers={'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}) as req:
                    response_bin = await req.read()
                    response_str = response_bin.decode()
                    response = json.loads(response_str)
            else:
                if proxy:
                    proxy_connector = proxy.generate_connector()
                else:
                    proxy_connector = aiohttp.TCPConnector()
                async with aiohttp.request('Post', api_url, data=encoded_string, cookies=account.cookies,
                                           connector=proxy_connector,
                                           headers={'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}) as req:
                    response_bin = await req.read()
                    response_str = response_bin.decode()
                    response = json.loads(response_str)
        except json.JSONDecodeError:
            pass
        else:
            break
    result = response['code']
    if result == 0:
        return True
    elif result == 1006:
        raise Exception(F"Unknown error")
    else:
        raise ValueError(f"Unknown value of {result} as a response")


# account = classes.QiAccount(18, 'theseeker.1ljISnxoPW@cock.li', 'qwerty123456',
#                               {'_csrfToken': '0ILeykdQRIyAoNGv8r5tUlcA2J4UmpDJhDuqwoFN',
#                                'alk': 'ta8ad94e034afc49cb9c10bb892d8b743b%7C4311122791', 'alkts': '1609516860',
#                                'uid': '4311122791', 'ukey': 'uUMXiwm62OY'}, 'tt3fd9b58dfaba4c19b9751bbcdd68d2c2', False,
#                               1601545517431, 21, 1, 0, 'theseeker@cock.li')#, 'qwerty123456')
#
#
# async def test1():
#     book = classes.SimpleBook(6831827102000005, 'Gourmet Food Supplier', 1002, 1101010, 'GFS')
#     book2 = classes.SimpleBook(6831838302000305, 'Commanding Wind and Cloud', 652, 1010101001)
#     result = await add_item_to_library(book, account=account)
#     result2 = await add_item_to_library(book2, account=account)
#     print(result, result2)
#     # result3 = await batch_remove_books_from_library(book, book2, account=account)
#     # print(result3)
#
#
# async def test2():
#     book = classes.SimpleBook(6831827102000005, 'Gourmet Food Supplier', 1002, 1101010, 'GFS')
#     book2 = classes.SimpleBook(6831838302000305, 'Commanding Wind and Cloud', 652, 1010101001)
#     result3 = await batch_remove_books_from_library(book, book2, account=account)
#     print(result3)
#
#
# async def test():
#     form_data = aiohttp.FormData({'_csrftoken': 'ajdhfsjalhfdlkjhf4'}, charset='UTF-8')
#     form_data.add_field('bookItems', [{"bookId": "16248450905321505", "novelType": 0}, {"bookId": "16248550905321505",
#                                                                                         "novelType": 0}])
#     async with aiohttp.request('Post', 'https://httpbin.org/post',
#                                data=form_data) as req:
#         data = await req.read()
#         data_t = await req.text()
#         print(data)
#         print(data_t)
