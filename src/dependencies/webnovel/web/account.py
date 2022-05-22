import typing

import aiohttp
from bs4 import BeautifulSoup

from dependencies.proxy_classes import Proxy
from ..classes import QiAccount, SimpleBook, Book
from ..exceptions import UnknownResponseCode
from ..utils import decode_qi_content

# import aiohttp_socks


# A dictionary that is used to create a connector.
default_connector_settings = {'force_close': True, 'enable_cleanup_closed': True}


def retrieve_csrftoken_from_session(session: aiohttp.ClientSession):
    """
    Retrieves the CSRF token from the session's cookie jar
    
    :param session: aiohttp.ClientSession
    :type session: aiohttp.ClientSession
    :return: The csrf_token is being returned.
    """
    assert isinstance(session, aiohttp.ClientSession)
    csrf_token = ''
    for cookie in session.cookie_jar:
        if cookie.key == '_csrfToken':
            csrf_token = cookie.value
    return csrf_token


async def retrieve_energy_stone_books() -> list:
    """
    Gets the HTML of the voting page, parses it with BeautifulSoup, finds all the vote buttons, and
    returns a list of the book IDs
    :return: A list of book ids.
    """
    books_ids = []
    async with aiohttp.request("get", "https://www.webnovel.com/vote") as resp:
        page_html = await resp.read()
    soup = BeautifulSoup(page_html, "lxml")
    vote_buttons = soup.find_all("a", attrs={"title": "vote"})
    for vote in vote_buttons:
        books_ids.append(int(vote.attrs["data-bookid"]))
    return books_ids


async def retrieve_power_stone_books() -> list:
    """
    Makes a request to the power stone ranking page, parses the html, and returns a list of the book
    ids.
    :return: A list of integers.
    """
    books_ids = []
    async with aiohttp.request("get", "https://www.webnovel.com/ranking/novel/monthly/power_rank") as resp:
        page_html = await resp.read()
    soup = BeautifulSoup(page_html, "lxml")
    book_covers = soup.find_all("a", attrs={"data-report-uiname": "bookcover"})
    for cover in book_covers:
        books_ids.append(int(cover.attrs["data-report-did"]))
    return books_ids


async def retrieve_farm_status(session: aiohttp.ClientSession = None, account: QiAccount = None, proxy: Proxy = None):
    """
    Checks if you can claim your daily rewards, and if you can get power stones and energy stones
    
    :param session: aiohttp.ClientSession = None, account: QiAccount = None, proxy: Proxy = None
    :type session: aiohttp.ClientSession
    :param account: QiAccount = None
    :type account: QiAccount
    :param proxy: Proxy = None
    :type proxy: Proxy
    :return: The return value is a tuple of three booleans.
    """
    task_list_url = 'https://www.webnovel.com/go/pcm/task/getTaskList'
    task_list_params = {'taskType': 1}

    if proxy:
        assert isinstance(proxy, Proxy)
        proxy_connector = proxy.generate_connector(**default_connector_settings)
    else:
        proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

    if session:
        task_list_params['_csrfToken'] = retrieve_csrftoken_from_session(session)
        async with session.get(task_list_url, params=task_list_params) as request:
            response_dict = decode_qi_content(await request.read())
    else:
        if account:
            task_list_params['_csrfToken'] = account.cookies['_csrfToken']
            async with aiohttp.request('GET', task_list_url, params=task_list_params, connector=proxy_connector,
                                       cookies=account.cookies) as request:
                response_dict = decode_qi_content(await request.read())
        else:
            raise ValueError(f"Missing either a session or account")

    if response_dict['code'] != 0:
        raise UnknownResponseCode(response_dict['code'], response_dict['msg'])
    task_list = response_dict['data']['taskList']

    claim_status = task_list[0]["completeStatus"] != 1
    power_stone_status = task_list[5]["completeStatus"] != 1
    energy_stone_status = task_list[6]["completeStatus"] != 1

    return claim_status, power_stone_status, energy_stone_status


async def claim_login(session: aiohttp.ClientSession = None, account: QiAccount = None, proxy: Proxy = None):
    """
    Takes in a session or account, and if it has a session, it will use the session to claim login,
    if it has an account, it will use the account to claim login
    
    :param session: aiohttp.ClientSession = None, account: QiAccount = None, proxy: Proxy = None
    :type session: aiohttp.ClientSession
    :param account: QiAccount = None
    :type account: QiAccount
    :param proxy: Proxy = None
    :type proxy: Proxy
    :return: A boolean value.
    """
    claim_url = 'https://www.webnovel.com/go/pcm/spiritStone/checkIn'
    claim_data = {}
    if proxy:
        assert isinstance(proxy, Proxy)
        proxy_connector = proxy.generate_connector(**default_connector_settings)
    else:
        proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

    if session:
        claim_data['_csrfToken'] = retrieve_csrftoken_from_session(session)
        async with session.post(claim_url, data=claim_data) as request:
            response_dict = decode_qi_content(await request.read())
    else:
        if account:
            claim_data['_csrfToken'] = account.cookies['_csrfToken']
            async with aiohttp.request('POST', claim_url, data=claim_data, cookies=account.cookies,
                                       connector=proxy_connector) as request:
                response_dict = decode_qi_content(await request.read())
        else:
            raise ValueError(f"Missing either a session or account")
    # response_dict = await post_request(session, Farmer.claim_url, claim_data)
    code = response_dict.get("code", '')
    if code == 0 or code == 2:
        return True
    else:
        # log and print dict
        return False


async def claim_power_stone(book_id: typing.Union[int, str], session: aiohttp.ClientSession = None,
                            account: QiAccount = None, proxy: Proxy = None):
    """
    Takes a book_id, and either a session or an account, and then it posts a request to the power
    stone vote url with the book_id and the csrf token
    
    :param book_id: The book id of the book you want to vote for
    :type book_id: typing.Union[int, str]
    :param session: aiohttp.ClientSession = None,
    :type session: aiohttp.ClientSession
    :param account: QiAccount = None, proxy: Proxy = None
    :type account: QiAccount
    :param proxy: Proxy = None
    :type proxy: Proxy
    :return: A coroutine object.
    """
    power_stone_vote_url = 'https://www.webnovel.com/go/pcm/powerStone/vote'
    # book_id = self.power_stone_books[random.randint(0, len(self.power_stone_books) - 1)]
    # power_stone_vote_data = {'_csrfToken': csrf_token, 'bookId': book_id, "novelType": 0}
    power_stone_vote_data = {'bookId': book_id, "novelType": 0}

    if proxy:
        assert isinstance(proxy, Proxy)
        proxy_connector = proxy.generate_connector(**default_connector_settings)
    else:
        proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

    if session:
        power_stone_vote_data['_csrfToken'] = retrieve_csrftoken_from_session(session)
        async with session.post(power_stone_vote_url, data=power_stone_vote_data) as request:
            response_dict = decode_qi_content(await request.read())
    else:
        if account:
            power_stone_vote_data['_csrfToken'] = account.cookies['_csrfToken']
            async with aiohttp.request('POST', power_stone_vote_url, data=power_stone_vote_data,
                                       connector=proxy_connector, cookies=account.cookies) as request:
                response_dict = decode_qi_content(await request.read())
        else:
            raise ValueError(f"Missing either a session or account")
    # response_dict = await post_request(session, Farmer.power_stone_vote_url, power_stone_vote_data)
    code = response_dict.get("code", '')
    if code == 0 or code == 2:
        return True
    else:
        # log and print dict
        return False


async def claim_energy_stone(book: typing.Union[SimpleBook, int, Book], session: aiohttp.ClientSession = None,
                             account: QiAccount = None, proxy: Proxy = None):
    """
    Takes a book object, a session, an account, and a proxy, and returns a boolean
    
    :param book: typing.Union[SimpleBook, int, Book]
    :type book: typing.Union[SimpleBook, int, Book]
    :param session: aiohttp.ClientSession = None,
    :type session: aiohttp.ClientSession
    :param account: QiAccount = None, proxy: Proxy = None
    :type account: QiAccount
    :param proxy: Proxy = None
    :type proxy: Proxy
    :return: A boolean value.
    """

    energy_stone_vote_url = 'https://www.webnovel.com/go/pcm/vote/like'
    # energy_stone_vote_data = {'_csrfToken': csrf_token, 'bookId': book_id}
    assert isinstance(book, (SimpleBook, int, Book))
    if proxy:
        proxy_connector = proxy.generate_connector(**default_connector_settings)
    else:
        proxy_connector = aiohttp.TCPConnector(**default_connector_settings)
    if isinstance(book, int):
        energy_stone_vote_data = {'bookId': str(book)}
    else:
        energy_stone_vote_data = {'bookId': str(book.id)}
    if session:
        energy_stone_vote_data['_csrfToken'] = retrieve_csrftoken_from_session(session)
        async with session.post(energy_stone_vote_url, data=energy_stone_vote_data) as request:
            response_dict = decode_qi_content(await request.read())
    else:
        if account:
            energy_stone_vote_data['_csrfToken'] = account.cookies['_csrfToken']
            async with aiohttp.request('POST', energy_stone_vote_url, data=energy_stone_vote_data,
                                       connector=proxy_connector, cookies=account.cookies) as request:
                response_dict = decode_qi_content(await request.read())
        else:
            raise ValueError(f"Missing either a session or account")
    # book_id = self.energy_stone_books[random.randint(0, len(self.energy_stone_books) - 1)]

    # response_dict = await post_request(session, Farmer.energy_stone_vote_url, energy_stone_vote_data)
    code = response_dict.get("code", '')
    if code == 0 or code == 3020:
        return True
    else:
        # log and print dict
        return False
