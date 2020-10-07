# import asyncio
import aiohttp
import aiohttp_socks
import typing
import json
from urllib.parse import quote
from dependencies.webnovel import classes

main_api_url = "https://www.webnovel.com/apiajax/Library"
# TODO compact most of the request making code


def __request_data_generator(session: aiohttp.ClientSession, account: classes.Account) -> (bool, dict):
    use_session = True
    if session is None:
        if account is None:
            raise ValueError(f"No valid value was passed to either session or "
                             f"account")
        else:
            assert isinstance(account, classes.Account)
            use_session = False
            add_data = {'_csrfToken': account.cookies['_csrfToken']}
    else:
        assert isinstance(session, aiohttp.ClientSession)
        csrf = ''
        for cookie in session.cookie_jar:
            if cookie.key == '_csrfToken':
                csrf = cookie.value
            else:
                continue
        add_data = {'_csrfToken': csrf}
    return use_session, add_data


def __parse_library_page(library_page_list: typing.List[dict]) -> typing.List[typing.Union[classes.Book,
                                                                                           classes.Comic]]:
    items = []
    for item in library_page_list:
        type_ = item['novelType']
        if type_ == 0:
            book_obj = classes.Book(item['bookId'], item['bookName'], item['totalChapterNum'])
            items.append(book_obj)
        elif type_ == 100:
            comic_obj = classes.Comic(item['bookId'], item['comicName'], item['newChapterIndex'])
            items.append(comic_obj)
        else:
            raise ValueError(f"Unknown item type found {item}")
    return items


async def retrieve_library_page(page_index: int = 1, session: aiohttp.ClientSession = None,
                                account: classes.Account = None, proxy: aiohttp_socks.ProxyConnector =
                                aiohttp.TCPConnector(force_close=True)) -> (
        typing.List[typing.Union[classes.Book, classes.Comic]], bool):
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
    api_url = '/'.join([main_api_url, 'LibraryAjax'])
    use_session, payload_data = __request_data_generator(session, account)
    payload_data['pageIndex'] = page_index
    payload_data['orderBy'] = 2
    if use_session:
        async with session.post(api_url, data=payload_data) as req:
            response_bin = await req.read()
            response_str = response_bin.decode()
            response = json.loads(response_str)
    else:
        async with aiohttp.request('POST', api_url, data=payload_data, cookies=account.cookies, connector=proxy) as req:
            response_bin = await req.read()
            response_str = response_bin.decode()
            response = json.loads(response_str)
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


async def add_item_to_library(item: typing.Union[classes.Book, classes.Comic],
                              session: aiohttp.ClientSession = None, account: classes.Account = None,
                              proxy: aiohttp_socks.ProxyConnector = aiohttp.TCPConnector()) -> bool:
    """Add an item to the library
        :arg item receives either a book or a comic object to be added to the library
        :arg session receives an aiohttp session object that includes the cookies of the account, if empty will use the
        account arg to generate a request
        :arg account receives an account object to generate a request with it, will be ignored if a session object is
        given
        :arg proxy accepts an aiohhtp proxy connector object, will be ignored if session is given

        :returns a bool value representing if the request was completed successfully
    """
    assert isinstance(item, classes.Comic) or isinstance(item, classes.Book)
    use_session, payload_data = __request_data_generator(session, account)
    payload_data['bookIds'] = item.id
    payload_data['novelType'] = item.NovelType
    # add_data = {'_csrfToken': csrf, 'bookIds': item_id, 'novelType': type_}
    api_url = '/'.join((main_api_url, 'AddLibraryItemsAjax'))
    if use_session:
        async with session.post(api_url, data=payload_data) as req:
            response_bin = await req.read()
            response_str = response_bin.decode()
            response = json.loads(response_str)
    else:
        async with aiohttp.request('POST', api_url, data=payload_data, cookies=account.cookies, connector=proxy) as req:
            response_bin = await req.read()
            response_str = response_bin.decode()
            response = json.loads(response_str)
    result = response['code']
    if result == 0:
        return True
    elif result == 1006:
        raise Exception(F"Unknown error")
    else:
        raise ValueError(f"Unknown value of {result} as a response")


async def remove_item_from_library(item: typing.Union[classes.Book, classes.Comic],
                                   session: aiohttp.ClientSession = None, account: classes.Account = None,
                                   proxy: aiohttp_socks.ProxyConnector = aiohttp.TCPConnector()) -> bool:
    """Removes an item from the library
        :arg item receives either a book or a comic object to be added to the library
        :arg session receives an aiohttp session object that includes the cookies of the account, if empty will use the
        account arg to generate a request
        :arg account receives an account object to generate a request with it, will be ignored if a session object is
        given
        :arg proxy accepts an aiohhtp proxy connector object, will be ignored if session is given

        :returns a bool value representing if the request was completed successfully
    """
    assert isinstance(item, classes.Comic) or isinstance(item, classes.Book)
    use_session, payload_data = __request_data_generator(session, account)
    full_data = {**payload_data, 'bookItems': '[{"bookId":"%s","novelType":%s}]' % (item.id, item.NovelType)}
    api_url = '/'.join((main_api_url, 'DeleteLibraryItemsAjax'))
    string = "&".join([f'{key}={value}' for key, value in full_data.items()])
    string.replace(' ', '')
    encoded_string = quote(string, encoding='UTF-8', safe='&=')
    # api_url = 'https://httpbin.org/post'
    if use_session:
        async with session.post(api_url, data=encoded_string,
                                headers={'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}) as req:
            response_bin = await req.read()
            response_str = response_bin.decode()
            response = json.loads(response_str)
    else:
        async with aiohttp.request('Post', api_url, data=encoded_string, cookies=account.cookies, connector=proxy,
                                   headers={'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}) as req:
            response_bin = await req.read()
            response_str = response_bin.decode()
            response = json.loads(response_str)
    result = response['code']
    if result == 0:
        return True
    elif result == 1006:
        raise Exception(F"Unknown error")
    else:
        raise ValueError(f"Unknown value of {result} as a response")


async def test1():
    book = classes.Book(6831827102000005, 'Gourmet Food Supplier', 1002, 'GFS', True)
    account = classes.Account(18, 'theseeker.1ljISnxoPW@cock.li', 'qwerty123456',
                              {'_csrfToken': 'uqOW6kXolFEy0P7qnB7Z023a8gA1A3wCOEtYt08x', 'alk':
                                     'ta728c503841914bda8646f7cfde76ae14%7C4311122791', 'alkts': '1601839387', 'uid':
                                     '4311122791', 'ukey': 'utxegYxk2MR'}, 'tt3fd9b58dfaba4c19b9751bbcdd68d2c2', False,
                              1601545517431, 21, 1, 0, 'theseeker@cock.li', 'qwerty123456')
    result = await add_item_to_library(book, account=account)
    print(result)


async def test():
    form_data = aiohttp.FormData({'_csrftoken': 'ajdhfsjalhfdlkjhf4'}, charset='UTF-8')
    form_data.add_field('bookItems', [{"bookId": "16248450905321505", "novelType": 0}, {"bookId": "16248550905321505",
                                                                                        "novelType": 0}])
    async with aiohttp.request('Post', 'https://httpbin.org/post',
                               data=form_data) as req:
        data = await req.read()
        data_t = await req.text()
        print(data)
        print(data_t)
