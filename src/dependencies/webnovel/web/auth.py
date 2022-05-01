import asyncio
import json
import random
import time

import aiohttp

# import aiohttp_socks

# Defining the urls that will be used in the functions.
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
    """
    Takes a session object and returns a dictionary of cookies
    
    :param session: aiohttp.ClientSession
    :type session: aiohttp.ClientSession
    :return: A dictionary of cookies.
    """
    cookies_dict = {}
    for cookie in session.cookie_jar:
        cookie_key = cookie.key
        cookie_value = cookie.value
        cookies_dict[cookie_key] = cookie_value
    return cookies_dict


async def __general_post_request__(url: str, data: dict, session: aiohttp.ClientSession):
    """
    Sends a POST request to a given URL with a given data, and returns the response as a dictionary
    
    :param url: str - the url to send the request to
    :type url: str
    :param data: dict = {
    :type data: dict
    :param session: aiohttp.ClientSession
    :type session: aiohttp.ClientSession
    :return: A dictionary
    """
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
    """
    Makes a GET request to a URL, and returns the JSON response as a dictionary
    
    :param url: str = the url to make the request to
    :type url: str
    :param session: aiohttp.ClientSession
    :type session: aiohttp.ClientSession
    :param params: dict = None, headers: dict = None
    :type params: dict
    :param headers: dict = None
    :type headers: dict
    :return: A dictionary
    """
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
    """
    Builds a dictionary with the required parameters for the login request
    
    :param csrf_token: The csrf token that you got from the login page
    :type csrf_token: str
    :param ticket: The ticket that was returned from the first request
    :type ticket: str
    :return: A dictionary of data that will be used to make a POST request to the login endpoint.
    """
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
    """
    Takes a ticket and a session, gets the csrf token from the session, builds a data object, and
    then makes a request to the server with the data object and the ticket
    
    :param ticket: str
    :type ticket: str
    :param session: aiohttp.ClientSession
    :type session: aiohttp.ClientSession
    :return: A tuple of two values. The first value is the response from the server. The second value is
    the ticket.
    """
    cookies = __get_cookies_from_session__(session)
    csrf_token = cookies['_csrfToken']
    data = __build_general_base_data__(csrf_token, ticket)
    response = await __general_json_get_request(check_status_url, session=session, params=data)
    if response['code'] == 0:
        data = response['data']
        ticket = data['ticket']
    return response, ticket


async def check_code(session: aiohttp.ClientSession, ticket: str, webnovel_email: str, webnovel_password: str):
    """
    Checks the code sent to the user's email.
    
    :param session: aiohttp.ClientSession
    :type session: aiohttp.ClientSession
    :param ticket: the ticket you got from the first step
    :type ticket: str
    :param webnovel_email: The email address you use to login to webnovel
    :type webnovel_email: str
    :param webnovel_password: The password of the account you want to login to
    :type webnovel_password: str
    :return: A tuple of two values. The first value is a dictionary containing the response from the
    server. The second value is a string containing the ticket.
    """
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
    """
    Sends a trust email to the user's email address
    
    :param session: aiohttp.ClientSession
    :type session: aiohttp.ClientSession
    :param ticket: the ticket you got from the previous step
    :type ticket: str
    :param encry_param: the encrypted parameter that is used to send the email
    :type encry_param: str
    :return: The response is a JSON object.
    """
    cookies = __get_cookies_from_session__(session)
    csrf_token = cookies['_csrfToken']
    data = __build_general_base_data__(csrf_token, ticket)
    data['encry'] = encry_param
    response = await __general_json_get_request(send_trust_email_url, session, params=data)
    return response


async def check_trust(session: aiohttp.ClientSession, ticket: str, encry_param: str, key_code: str):
    """
    Takes a session, a ticket, an encrypted parameter, and a key code, and returns a response and a
    ticket
    
    :param session: aiohttp.ClientSession
    :type session: aiohttp.ClientSession
    :param ticket: The ticket from the previous step
    :type ticket: str
    :param encry_param: This is the encrypted parameter that is returned from the get_trust_code
    function
    :type encry_param: str
    :param key_code: The code that is sent to your phone
    :type key_code: str
    :return: A tuple of two values. The first is a dictionary of the response from the server. The
    second is the ticket.
    """
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
