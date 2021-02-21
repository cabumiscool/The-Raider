import asyncio

from typing import Union
from operator import attrgetter

import aiohttp
import aiohttp_socks


class InvalidIpAddress(Exception):
    """Raised when a given ip address is invalid"""


class Proxy:
    _connection_types = {'http': aiohttp_socks.ProxyType.HTTP, 'socks4': aiohttp_socks.ProxyType.SOCKS4,
                         'socks5': aiohttp_socks.ProxyType.SOCKS5}
    _regions = ['Unknown', 'Waka', 'U.S.']

    def __init__(self, id_: int, ip: str, port: Union[str, int], connection_type: str, uptime: Union[int, str],
                 latency: Union[int, str], speed: Union[int, str], region: int):
        if isinstance(ip, str):
            ip_parts = ip.split('.')
            if len(ip_parts) == 4:
                for part in ip_parts:
                    try:
                        int(part)
                    except ValueError:
                        raise InvalidIpAddress(f'The Ip address of {ip} is invalid') from ValueError
            else:
                raise InvalidIpAddress(f'The Ip address of {ip} is invalid')
        else:
            raise ValueError(f"Was expecting an object of type 'str' instead received a type '{type(ip).__name__}'")
        self.id = id_
        self._ip = ip
        self._port = int(port)

        self.test_url = 'https://www.webnovel.com/'
        try:
            self._type = self._connection_types[connection_type.lower()]
            self.type_str = connection_type.lower()
        except KeyError:
            raise ValueError('Invalid proxy type was input') from KeyError
        self.uptime = int(uptime)
        self.latency = int(latency)
        self.speed = int(speed)
        self.region = int(region)

    def generate_connector(self, **kwargs) -> aiohttp_socks.ProxyConnector:
        """Generates a connector
            :arg kwargs accept all the valid keywords for tcp connector from aiohttp and aiohttp_socks"""
        return aiohttp_socks.ProxyConnector(self._type, self._ip, self._port, **kwargs)

    async def test(self):
        async with aiohttp.request('GET', self.test_url, connector=self.generate_connector(),
                                   timeout=aiohttp.ClientTimeout(30)) as req:
            try:
                await req.read()
            except asyncio.TimeoutError:
                return False
            else:
                return req.status == 200

    def return_ip(self):
        return self._ip

    def return_port(self):
        return self._port


class DummyProxy:
    @staticmethod
    def generate_connector(**kwargs) -> aiohttp_socks.ProxyConnector:
        return aiohttp.TCPConnector(**kwargs)

    @staticmethod
    async def test():
        return True


class ProxyManager:
    def __init__(self, target_url_to_test_against: str, *proxies: Proxy, region: str = None,
                 loop: asyncio.AbstractEventLoop = None):
        self._running = True
        self._test_target = target_url_to_test_against
        self.region = region
        sort_by_latency = sorted(proxies, key=attrgetter('latency'))
        sort_by_speed = sorted(sort_by_latency, key=attrgetter('speed'), reverse=True)
        self._all_proxies = sorted(sort_by_speed, key=attrgetter('uptime'), reverse=True)
        if loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._working_proxies = []
        self._failed_proxies = []
        self._init = False
        self._in_check = False
        self._init_task = self._loop.create_task(self.__all_proxies_check())
        self._service = self._loop.create_task(self.__retry_proxy_service())

    async def __init_check(self):
        if self._init is True:
            return
        if self._in_check:
            try:
                await self._init_task
            except:
                self._init_task = self._loop.create_task(self.__all_proxies_check())
                await self._init_task
        else:
            self._init_task = self._loop.create_task(self.__all_proxies_check())
            await self._init_task

    async def __proxy_check(self, proxy: Proxy):
        connector = proxy.generate_connector()
        try:
            async with connector as conn:  # added as a context manager to prevent an annoying non-critical error
                # from popping up
                async with aiohttp.request('get', self._test_target, connector=conn,
                                           timeout=aiohttp.ClientTimeout(30)) as request:
                    # await request.read()
                    request_code = request.status
        # TODO: BUM add proper catching of exceptions
        except:
            return False, proxy
        if request_code == 200:
            return True, proxy
        return False, proxy

    async def __all_proxies_check(self):
        self._in_check = True
        tasks = []
        for proxy in self._all_proxies:
            tasks.append(self._loop.create_task(self.__proxy_check(proxy)))
        results = await asyncio.gather(*tasks)
        for result in results:
            if result[0] is True:
                self._working_proxies.append(result[1])
            else:
                self._failed_proxies.append(result[1])

    async def __retry_proxy_service(self):
        while self._running:
            proxy_to_check = self._failed_proxies.pop(0)
            result, proxy = await self.__proxy_check(proxy_to_check)
            if result is True:
                self._working_proxies.append(proxy)
            else:
                self._failed_proxies.append(proxy)

    async def retrieve_proxy(self):
        await self.__init_check()
        return self._all_proxies[0]

    def return_proxy(self, proxy: Proxy):
        if proxy in self._all_proxies:
            self._all_proxies.remove(proxy)
            self._failed_proxies.append(proxy)
        else:
            return

# if __name__ == '__main__':
#     with open('usa_proxies', 'r') as file:
#         lines = []
#         for line in file:
#             lines.append(line.split('\t'))
#     proxies_list = []
#     for proxy_list in lines:
#         proxy_obj = Proxy(proxy_list[0], proxy_list[1], proxy_list[2], proxy_list[4], proxy_list[5].replace('\n', ''),
#                           proxy_list[3])
#         proxies_list.append(proxy_obj)
#     # loop = asyncio.get_event_loop()
#     #
#     # loop.run_until_complete(manager.test())
#
#     async def test(*_proxies):
#         manager = ProxyManager('https://www.webnovel.com/', *_proxies, region='USA')
#         await asyncio.sleep(30)
#         proxy = await manager.retrieve_proxy()
#         print(True)
#     asyncio.run(test(*proxies_list))
