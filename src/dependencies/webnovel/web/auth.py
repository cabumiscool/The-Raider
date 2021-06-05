import asyncio
import json
import random
import time

import aiohttp

# import aiohttp_socks

check_status_url = 'https://ptlogin.webnovel.com/login/checkStatus'
logout_url = 'https://ptlogin.webnovel.com/login/logout'
login_url = 'https://ptlogin.webnovel.com/login/login'
check_code_url = 'https://ptlogin.webnovel.com/login/checkcode'
check_ticket_url = 'https://ptlogin.webnovel.com/login/checkTicket'
validate_code_url = 'https://ptlogin.webnovel.com/userSdk/getvalidatecode'
register_url = 'https://ptlogin.webnovel.com/login/doregister'
resend_reg_email = 'https://ptlogin.webnovel.com/login/resendregemail'
reset_psw_url = 'https://ptlogin.webnovel.com/login/resetPwsMail'
update_psw_url = 'https://ptlogin.webnovel.com/welcome/ChangePwd'
re_send_email_url = 'https://ptlogin.webnovel.com/login/ReSendEmail'
send_trust_email_url = 'https://ptlogin.webnovel.com/login/sendTrustEmail'
re_send_trust_email_url = 'https://ptlogin.webnovel.com/login/reSendTrustEmail'
check_trust_url = 'https://ptlogin.webnovel.com/login/checkTrust'

default_connector_settings = {'force_close': True, 'enable_cleanup_closed': True}


def __get_cookies_from_session__(session: aiohttp.ClientSession):
    cookies_dict = {}
    for cookie in session.cookie_jar:
        cookie_key = cookie.key
        cookie_value = cookie.value
        cookies_dict[cookie_key] = cookie_value
    return cookies_dict


async def __general_post_request__(url: str, data: dict, session: aiohttp.ClientSession):
    retry_count = 0
    while True:
        try:
            async with session.post(url=url, data=data) as resp:
                response_bin = await resp.read()
                response_str = response_bin.decode()
                response_dict = json.loads(response_str)
                break
        except json.JSONDecodeError:
            await asyncio.sleep(0.1)
            if response_str == '':
                return {}
    retry_count += 1
    if retry_count >= 8:
        raise TimeoutError(f"all the retry attempts have been tried")
    return response_dict


async def __general_json_get_request(url: str, session: aiohttp.ClientSession, params: dict = None,
                                     headers: dict = None):
    retry_count = 0
    while True:
        try:
            async with session.get(url=url, params=params, headers=headers) as resp:
                response_bin = await resp.read()
                response_str = response_bin.decode()
                response_dict = json.loads(response_str)
                break
        except json.JSONDecodeError:
            await asyncio.sleep(0.1)
            if response_str == '':
                return {}
        retry_count += 1
        if retry_count >= 8:
            raise TimeoutError(f"all the retry attempts have been tried")
    return response_dict


def __build_general_base_data__(csrf_token: str, ticket: str):
    return {
        'appId': 900,
        'areaId': 1,
        'source': '',
        'returnurl': "https://www.webnovel.com/loginSuccess",
        'version': '',
        'imei': '',
        'qimei': '',
        'target': 'iframe',
        'format': 'jsonp',
        'ticket': ticket,
        'autotime': '',
        'auto': 1,
        'fromuid': 0,
        '_csrfToken': csrf_token,
        '_': int(time.time() * 1000)
    }


async def check_status(ticket: str, session: aiohttp.ClientSession):
    cookies = __get_cookies_from_session__(session)
    csrf_token = cookies['_csrfToken']
    data = __build_general_base_data__(csrf_token, ticket)
    response = await __general_json_get_request(check_status_url, session=session, params=data)
    if response['code'] == 0:
        data = response['data']
        ticket = data['ticket']
    return response, ticket


async def check_code(session: aiohttp.ClientSession, ticket: str, webnovel_email: str, webnovel_password: str):
    cookies = __get_cookies_from_session__(session)
    csrf_token = cookies['_csrfToken']
    data = __build_general_base_data__(csrf_token, ticket)
    data['username'] = webnovel_email
    data['password'] = webnovel_password
    data['logintype'] = 22
    data['callback'] = "".join(["jQuery19101", str(int(random.uniform(100000000000000, 999999999999999))),
                                "_", str(int(time.time() * 1000))])
    login_header = {'Referer': "https://passport.webnovel.com/emaillogin.html?appid=900&are"
                               "aid=1&returnurl=https%3A%2F%2Fwww.webnovel.com%2Flibrary&aut"
                               "o=1&autotime=0&source=&ver=2&fromuid=0&target=iframe&option="}
    response = await __general_json_get_request(check_code_url, session, params=data, headers=login_header)
    if response['code'] == 0:
        data = response['data']
        ticket = data['ticket']
    elif response['code'] == 11401:
        pass
    else:
        print(f"Check code : {response}")
    return response, ticket


async def send_trust_email(session: aiohttp.ClientSession, ticket: str, encry_param: str):
    cookies = __get_cookies_from_session__(session)
    csrf_token = cookies['_csrfToken']
    data = __build_general_base_data__(csrf_token, ticket)
    data['encry'] = encry_param
    response = await __general_json_get_request(send_trust_email_url, session, params=data)
    return response


async def check_trust(session: aiohttp.ClientSession, ticket: str, encry_param: str, key_code: str):
    cookies = __get_cookies_from_session__(session)
    csrf_token = cookies['_csrfToken']
    data = __build_general_base_data__(csrf_token, ticket)
    data['encry'] = encry_param
    data['trustcode'] = key_code
    response = await __general_json_get_request(check_trust_url, session, params=data)
    if response['code'] == 0:
        data = response['data']
        ticket = data['ticket']
    elif response['code'] == 11318:
        pass
    elif response['code'] == 11401:
        pass
    else:
        print(f"Check Trust: {response}")
    return response, ticket


#  Needs to be finished ported, not needed at the moment
"""
async def account_login():
    data = {
        '_csrfToken': self.__get_cookies__()['_csrfToken'],
        'ticket': self.ticket,
        'guid': self.__get_cookies__()['uid']
    }
    response = await json_get_request(self.session, Login.login_url, data)
    print(f"Login : {response}")
    return response


async def account_logout():
    data = {
        'appId': 900,
        'areaId': 1,
        'source': 'enweb',
        'format': 'redirect'
    }
    response = await json_get_request(self.session, Login.login_url, data)
    print(response)
    return response
"""
