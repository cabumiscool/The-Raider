import asyncio
import aiohttp
import typing
from background_process.base_service import BaseService
from dependencies.database.database import Database
from dependencies.webnovel import classes
from dependencies.proxy_classes import Proxy
from dependencies.webnovel.web import book
from dependencies.webnovel.waka import book as wbook


class BuyManager:
    def __init__(self, chapter: classes.SimpleChapter, session: aiohttp.ClientSession):
        self.chapter = chapter
        self._session = session
        self._task = asyncio.create_task(book.chapter_buyer(chapter.parent_id, chapter.id, session=self._session))

    def is_done(self):
        return self._task.done()

    def return_chapter(self) -> classes.Chapter:
        return self._task.result()

    def is_error(self) -> bool:
        return bool(self._task.exception())


# TODO Finish writing the handler in case of error
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
        self._uncompleted_chapters_to_return = []

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

    def has_uncompleted_chapters(self) -> bool:
        return len(self._uncompleted_chapters_to_return) > 0

    def return_uncompleted_chapters(self):
        return self._completed_chapters

    async def retrieve_done(self) -> list:
        for buy_manager in self._buys:
            buy_manager: BuyManager
            if buy_manager.is_done():
                if buy_manager.is_error():
                    if await self._account.async_check_valid():
                        if self._account.fast_pass_count > 0:
                            if self._slots != self._account.fast_pass_count:
                                self._slots = self._account.fast_pass_count

                            self._buys.append(BuyManager(buy_manager.chapter, self._session))
                            self._slots -= 1
                        else:
                            self._slots = 0
                            self._uncompleted_chapters_to_return.append(buy_manager.chapter)
                            self._buys.remove(buy_manager)
                    else:
                        self._slots = 0
                        self._uncompleted_chapters_to_return.append(buy_manager.chapter)
                        self._buys.remove(buy_manager)
                else:
                    self._completed_chapters.append(buy_manager.return_chapter())
                    self._completed_buys.append(buy_manager)
        return self.__return__completed_chapter()

    def buy(self, chapter: classes.SimpleChapter):
        self._buys.append(BuyManager(chapter, self._session))
        self._slots -= 1


class WakaBuyManager:
    def __init__(self, chapter: classes.SimpleChapter, session: aiohttp.ClientSession):
        self.chapter = chapter
        self._session = session
        self._task = asyncio.create_task(wbook.chapter_retriever(chapter.parent_id, chapter.id, chapter.volume_index,
                                                                 session=self._session))

    def is_done(self):
        return self._task.done()

    def return_chapter(self) -> classes.Chapter:
        return self._task.result()

    def is_error(self):
        return bool(self._task.exception())


class WakaBuyerPool:
    def __init__(self, waka_proxy: Proxy):
        self._proxy = waka_proxy
        self._buyers = []
        self._done_managers = []
        self._chapters = []
        self._connector = waka_proxy.generate_connector()
        self._session = aiohttp.ClientSession(connector=self._connector)

    def retrieve_done(self) -> list:
        for manager in self._buyers:
            manager: WakaBuyManager
            if manager.is_done():
                if manager.is_error():
                    self._buyers.append(WakaBuyManager(chapter=manager.chapter, session=self._session))
                    self._buyers.remove(manager)
                    manager.return_chapter()
                else:
                    self._chapters.append(manager.return_chapter())
                    self._done_managers.append(manager)

        for manager_to_delete in self._done_managers:
            self._buyers.remove(manager_to_delete)
        self._done_managers.clear()
        chapters_to_return = self._chapters.copy()
        self._chapters.clear()
        return chapters_to_return

    def buy(self, chapter: classes.SimpleChapter):
        self._buyers.append(WakaBuyManager(chapter, self._session))


class BuyerService(BaseService):
    def __init__(self, database: Database):
        super().__init__("Buyer Service Module")
        self.database = database
        self.pools = []
        self.priv_buyer = None

    async def main(self):
        if self.priv_buyer is None:
            self.priv_buyer = WakaBuyerPool(await self.database.retrieve_proxy(1))
        cache_content = self._retrieve_input_queue()
        cache_content: typing.List[classes.SimpleChapter]

        # will assign the chapters from the input qi to a pool
        for chapter in cache_content:
            if chapter.is_privilege:
                self.priv_buyer.buy(chapter)
            else:
                for pool in self.pools:
                    pool: typing.Union[BuyerPool, WakaBuyerPool]
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

        # will look for empty pools and clean up
        pool_to_delete = []
        for pool in self.pools:
            if pool.is_empty():
                if pool.has_uncompleted_chapters():
                    uncompleted_chapters = pool.return_uncompleted_chapters()
                    pool_to_delete.append(pool)
                    self.add_to_queue(*uncompleted_chapters)
                else:
                    pool_to_delete.append(pool)

        for pool in pool_to_delete:
            self.pools.remove(pool)