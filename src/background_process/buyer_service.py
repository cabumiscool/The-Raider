import asyncio
import aiohttp
import typing
from background_process.base_service import BaseService
from dependencies.database.database import Database
from dependencies.webnovel import classes
from dependencies.proxy_manager import Proxy
from dependencies.webnovel.web import book


class BuyManager:
    def __init__(self, chapter: classes.SimpleChapter, session: aiohttp.ClientSession):
        self.chapter = chapter
        self._session = session
        self._task = asyncio.create_task(book.chapter_buyer(chapter.parent_id, chapter.id, session=self._session))

    def is_done(self):
        return self._task.done()

    def return_chapter(self) -> classes.Chapter:
        return self._task.result()


class BuyerPool:
    def __init__(self, account: classes.QiAccount, proxy: Proxy = None):
        self._proxy = proxy
        self._account = account
        self._slots = account.fast_pass_count
        if self._proxy:
            self._connector = proxy.generate_connector()
        else:
            self._connector = aiohttp.TCPConnector()
        self._buys = []
        self._completed_chapters = []
        self._completed_buys = []

        # TODO find if there is a non deprecated form
        self._session = aiohttp.ClientSession(connector=self._connector, cookies=account.cookies)

    def __return__completed_chapter(self) -> list:
        return_list = self._completed_chapters.copy()
        self._completed_chapters.clear()
        for buy_manager in self._completed_buys:
            self._buys.remove(buy_manager)
        self._completed_buys.clear()
        return return_list

    def available_capacity(self) -> bool:
        return self._slots > 0

    def is_empty(self) -> bool:
        return len(self._buys) == 0

    def has_queue(self) -> bool:
        return len(self._buys) > 1

    async def retrieve_done(self) -> list:
        for buy_manager in self._buys:
            buy_manager: BuyManager
            if buy_manager.is_done():
                self._completed_chapters.append(buy_manager.return_chapter())
                self._completed_buys.append(buy_manager)
        return self.__return__completed_chapter()

    def buy(self, chapter: classes.SimpleChapter):
        self._buys.append(BuyManager(chapter, self._session))
        self._slots -= 1


# TODO finish writing this once the waka module is done
class WakaBuyer:
    def __init__(self):
        self.tasks = []

    def buy(self, chapter: classes.SimpleChapter):
        pass


class BuyerService(BaseService):
    def __init__(self, database: Database):
        super().__init__("Buyer Service Module")
        self.database = database
        self.pools = []
        self.priv_buyer = WakaBuyer()

    async def main(self):
        cache_content = self._retrieve_input_queue()
        cache_content: typing.List[classes.SimpleChapter]

        # will assign the chapters from the input qi to a pool
        for chapter in cache_content:
            if chapter.is_privilege:
                self.priv_buyer.buy(chapter)
            else:
                for pool in self.pools:
                    pool: BuyerPool
                    if pool.available_capacity():
                        pool.buy(chapter)
                        break
                else:
                    account = await self.database.retrieve_buyer_account()
                    while True:
                        account_working = await account.async_check_valid()
                        if account_working:
                            break
                        else:
                            await self.database.expired_account(account)
                            account = await self.database.retrieve_buyer_account()
                    self.pools.append(BuyerPool(account=account))

        # will add to the output cache the completed values from the pools
        for pool in self.pools:
            self._output_queue.append(pool.retrieve_done())
