import typing

import aiohttp
# import aiohttp_socks

from dependencies.webnovel.classes import QiAccount, SimpleBook, Book
from dependencies.webnovel.exceptions import UnknownResponseCode
from dependencies.webnovel.utils import decode_qi_content
from dependencies.proxy_classes import Proxy

from bs4 import BeautifulSoup


default_connector_settings = {'force_close': True, 'enable_cleanup_closed': True}


async def retrieve_energy_stone_books() -> list:
    books_ids = []
    async with aiohttp.request("get", "https://www.webnovel.com/vote") as resp:
        page_html = await resp.read()
    soup = BeautifulSoup(page_html, "lxml")
    vote_buttons = soup.find_all("a", attrs={"title": "vote"})
    for vote in vote_buttons:
        books_ids.append(int(vote.attrs["data-bookid"]))
    return books_ids


async def retrieve_power_stone_books() -> list:
    params_args = {"pageIndex": "1", "type": "1"}
    async with aiohttp.request("get", "https://www.webnovel.com/apiajax/ranking/getRanking",
                               params=params_args) as resp:
        content_bin = await resp.read()
    content_dict = decode_qi_content(content_bin)
    top_20_dict_list = content_dict["data"]["rankingItems"]
    return [int(book["bookId"]) for book in top_20_dict_list]


async def retrieve_farm_status(session: aiohttp.ClientSession = None, account: QiAccount = None, proxy: Proxy = None):
    task_list_url = 'https://www.webnovel.com/apiajax/task/taskList'
    task_list_params = {'taskType': str(1)}

    if proxy:
        assert isinstance(proxy, Proxy)
        proxy_connector = proxy.generate_connector(**default_connector_settings)
    else:
        proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

    if session:
        # TODO get csrftoken from session and add to params
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
    claim_url = 'https://www.webnovel.com/apiajax/SpiritStone/addSSAjax'
    # claim_data = {'_csrfToken': csrf_token, 'type': '1'}
    claim_data = {'type': '1'}
    if proxy:
        assert isinstance(proxy, Proxy)
        proxy_connector = proxy.generate_connector(**default_connector_settings)
    else:
        proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

    if session:
        # TODO: retrieve csrftoken from session
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
    power_stone_vote_url = 'https://www.webnovel.com/apiajax/powerStone/vote'
    # book_id = self.power_stone_books[random.randint(0, len(self.power_stone_books) - 1)]
    # power_stone_vote_data = {'_csrfToken': csrf_token, 'bookId': book_id, "novelType": 0}
    power_stone_vote_data = {'bookId': book_id, "novelType": 0}

    if proxy:
        assert isinstance(proxy, Proxy)
        proxy_connector = proxy.generate_connector(**default_connector_settings)
    else:
        proxy_connector = aiohttp.TCPConnector(**default_connector_settings)

    if session:
        # TODO: retrieve the csrftoken from the session cookies
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
    energy_stone_vote_url = 'https://www.webnovel.com/apiajax/translationVote/vote'
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
        # TODO: extract the csrftoken from the session and add it to the data dict
        async with session.post(energy_stone_vote_url, data=energy_stone_vote_data) as request:
            response_dict = decode_qi_content(await request.read())
    else:
        if account:
            energy_stone_vote_data['_csrfToken'] = account.cookies['_csrfToken']
            async with aiohttp.request('POST', energy_stone_vote_url, data=energy_stone_vote_data,
                                       connector=proxy_connector, cookies=account.cookies)as request:
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
