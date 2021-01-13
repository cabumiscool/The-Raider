import typing
import asyncio
import aiohttp
import aiohttp_socks
from dependencies.proxy_classes import Proxy

from background_process.base_service import BaseService
from background_process.background_objects import ProxyErrorReport
from dependencies.database.database import Database

urls_to_test_against = {1: 'https://m.ficool.com', 2: 'https://www.webnovel.com'}
default_proxy_arguments = {'force_close': True, 'enable_cleanup_closed': True}


class SemiWorking:
    """Used to return if a proxy is almost working"""


class DummyException(Exception):
    """Space taker"""


async def test_wrapper(proxy: Proxy) -> typing.Tuple[Proxy, typing.Union[bool, SemiWorking],
                                                     typing.Union[None, int, Exception]]:
    connector = proxy.generate_connector(**default_proxy_arguments)
    working = False
    error = None
    try:
        async with aiohttp.request('GET', urls_to_test_against[proxy.region], connector=connector,
                                   timeout=aiohttp.ClientTimeout(30)) as request:
            code = request.status
            working = True
    except Exception as e:
        error = e
    if code == 200 and working is True:
        return proxy, True, None
    elif working is True and code != 200:
        return proxy, SemiWorking(), code
    else:
        return proxy, False, error


class ProxyManager(BaseService):
    def __init__(self, database: Database):
        super().__init__("Proxy Manager Service", loop_time=10)
        self.database = database

    async def main(self):
        tasks = []
        proxies_to_check = await self.database.retrieve_all_expired_proxies()
        for proxy in proxies_to_check:
            tasks.append(asyncio.create_task(test_wrapper(proxy)))

        results_of_tests = await asyncio.gather(*tasks)
        for result in results_of_tests:
            result: typing.Tuple[Proxy, typing.Union[bool, SemiWorking], typing.Union[None, int, Exception]]
            if type(result[1]) == SemiWorking:
                self._output_queue.append(ProxyErrorReport(DummyException, f"A proxy failed to connect to target "
                                                                           f"address but connected to the proxy "
                                                                           f"server. It returned code {result[2]}",
                                                           'Happened at the tester wrapper', result[0].id))
            elif result[1] is False:
                result[2]: Exception
                self._output_queue.append(ProxyErrorReport(result[2], f"Proxy failed ot connect",
                                                           "Happened at the tester wrapper", result[0].id))
            else:
                await self.database.mark_as_working_proxy(result[0])
