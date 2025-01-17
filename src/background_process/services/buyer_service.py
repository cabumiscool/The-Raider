import asyncio
import time
import typing

import aiohttp

from dependencies.database.database import Database
from dependencies.proxy_classes import Proxy
from dependencies.webnovel import classes
from dependencies.webnovel.waka import book as wbook
from dependencies.webnovel.web import book
from .base_service import BaseService
from ..background_objects import NoAvailableBuyerAccountError

default_connector_settings = {'force_close': True, 'enable_cleanup_closed': True}


class QueueItem:
    def __init__(self, chapter: classes.SimpleChapter):
        # This declares in what state does the item finds itself at the moment:
        # 0: none  |  1: attempted buy  | 2: bought
        self._state = 0
        self._item: classes.SimpleChapter = chapter

    def is_new(self):
        return self._state == 0

    def is_in_process(self):
        return self._state == 1

    def is_completed(self):
        return self._state == 2

    def set_as_in_process(self):
        self._state = 1

    def set_as_completed(self):
        self._state = 2

    def is_priv(self):
        return self._item.is_privilege

    def return_chapter_id(self):
        return self._item.id

    def return_item(self):
        return self._item


class InnerBuyQueue:
    def __init__(self):
        self._items: typing.Dict[int: QueueItem] = {}

    def add_item(self, item: QueueItem):
        self._items[item.return_chapter_id()] = item

    def marked_as_complete(self, chapter_id: int):
        self._items[chapter_id].set_as_completed()

    def clean_queue(self):
        chapter_ids = []
        for chapter_id, queue_item in self._items.items():
            queue_item: QueueItem
            if queue_item.is_completed():
                chapter_ids.append(chapter_id)

        for chapter_id in chapter_ids:
            del self._items[chapter_id]

    def hard_clean_queue(self):
        self._items.clear()

    def return_new_chapters(self, amount: int = 40) -> list:
        chapters_to_return = []
        if amount > 40 or amount <= 0:
            raise ValueError("it is invalid to request more than 40 chapters at once or less or equal to 0")

        for chapter_id, queue_item in self._items.items():
            queue_item: QueueItem
            chapter_id: int
            if queue_item.is_new():
                chapters_to_return.append(queue_item.return_item())
                self._items[chapter_id].set_as_in_process()

            if len(chapters_to_return) >= amount:
                break

        return chapters_to_return

    def return_used_chapters(self) -> list:
        chapters_to_return = []

        for chapter_id, queue_item in self._items.items():
            queue_item: QueueItem
            chapter_id: int
            if queue_item.is_in_process():
                chapters_to_return.append(queue_item.return_item())
                self._items[chapter_id].queue_item.set_as_in_process()

        return chapters_to_return


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


# TODO Finish writing the handler in case of error | could be done.... need to check in detail
class BuyerPool:
    def __init__(self, account: classes.QiAccount, proxy: Proxy = None):
        self._proxy = proxy
        self._account = account
        self._slots = account.fast_pass_count
        if self._proxy:
            self._connector = proxy.generate_connector(**default_connector_settings)
        else:
            self._connector = aiohttp.TCPConnector(**default_connector_settings)
        self._buys = []
        self._completed_chapters = []
        self._completed_buys = []
        self._uncompleted_chapters_to_return = []
        self._created_time = time.time()

        # TODO find if there is a non deprecated form, ps. the deprecated form is creating it from an sync code,
        #  creating it from an async code is legal
        self._session = aiohttp.ClientSession(connector=self._connector, cookies=account.cookies)

    def __return__completed_chapter(self) -> list:
        return_list = self._completed_chapters.copy()
        self._completed_chapters.clear()
        for buy_manager in self._completed_buys:
            self._buys.remove(buy_manager)
        self._completed_buys.clear()
        return return_list

    def available_capacity(self) -> bool:
        if time.time() - self._created_time >= 180:
            self._slots = 0
        return self._slots > 0

    def return_number_of_items_in_pool(self):
        return len(self._buys)

    def is_empty(self) -> bool:
        return len(self._buys) == 0

    def has_queue(self) -> bool:
        return len(self._buys) > 1

    def has_uncompleted_chapters(self) -> bool:
        return len(self._uncompleted_chapters_to_return) > 0

    def return_uncompleted_chapters(self):
        return self._uncompleted_chapters_to_return

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
                            self._buys.remove(buy_manager)
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

    def return_account(self):
        return self._account

    async def close(self):
        await self._session.close()


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
        self._done_managers = set()
        self._chapters = []
        self._connector = waka_proxy.generate_connector(**default_connector_settings)
        self._session = aiohttp.ClientSession(connector=self._connector)

    def retrieve_done(self) -> list:
        for manager in self._buyers:
            manager: WakaBuyManager
            if manager.is_done():
                if manager.is_error():
                    self._buyers.append(WakaBuyManager(chapter=manager.chapter, session=self._session))
                    self._done_managers.add(manager)
                    manager.return_chapter()
                else:
                    self._chapters.append(manager.return_chapter())
                    self._done_managers.add(manager)
                    # self._done_managers.append(manager)

        for manager_to_delete in self._done_managers:
            try:
                self._buyers.remove(manager_to_delete)
            except ValueError:
                pass
        self._done_managers.clear()
        chapters_to_return = self._chapters.copy()
        self._chapters.clear()
        return chapters_to_return

    def buy(self, chapter: classes.SimpleChapter):
        self._buyers.append(WakaBuyManager(chapter, self._session))


class BuyerService(BaseService):
    def __init__(self, database: Database):
        super().__init__("Buyer Service")
        self._buyer_queue = InnerBuyQueue()
        self.database = database
        self.pools = []
        self.priv_buyer = None
        self.max_buys = 30

    def load_inner_queue(self):
        cache_content = self._retrieve_input_queue()
        cache_content: typing.List[classes.SimpleChapter]
        for chapter in cache_content:
            queue_item = QueueItem(chapter)
            self._buyer_queue.add_item(queue_item)

    async def main(self):
        if self.priv_buyer is None:
            self.priv_buyer = WakaBuyerPool(await self.database.retrieve_proxy(1))

        self.load_inner_queue()

        items_in_pools = 0
        for pool in self.pools:
            items_in_pools += pool.return_number_of_items_in_pool()

        if not self._is_a_restart:
            if self.max_buys - items_in_pools > 0:
                chapters_to_buy = self._buyer_queue.return_new_chapters(self.max_buys - items_in_pools)
            else:
                chapters_to_buy = []
        else:
            chapters_to_buy = self._buyer_queue.return_used_chapters()

        # will assign the chapters from the input queue to a pool
        for chapter in chapters_to_buy:
            if chapter.is_privilege:
                self.priv_buyer.buy(chapter)
            else:
                for pool in self.pools:
                    pool: typing.Union[BuyerPool]
                    if pool.available_capacity():
                        pool.buy(chapter)
                        break
                else:
                    account = await self.database.retrieve_buyer_account()
                    account_try = 0
                    while True:
                        account_working = await account.async_check_valid()
                        if account_working:
                            if account.fast_pass_count == 0:
                                await self.database.update_account_fp_count(0, account)
                                account_try += 1
                                if account_try >= 10:
                                    raise NoAvailableBuyerAccountError("No available account was found for a "
                                                                       "new buyer pool")
                                continue
                            break
                        else:
                            account_try += 1
                            await self.database.expired_account(account)
                            if account_try >= 10:
                                raise NoAvailableBuyerAccountError("No available account was found for a "
                                                                   "new buyer pool")
                            account = await self.database.retrieve_buyer_account()
                    new_pool = BuyerPool(account=account)
                    new_pool.buy(chapter)
                    self.pools.append(new_pool)

        # will add to the output cache the completed values from the pools
        for pool in self.pools:
            completed_chapters = await pool.retrieve_done()
            for chapter in completed_chapters:
                self._buyer_queue.marked_as_complete(chapter.id)
            self._output_queue.extend(completed_chapters)
        self._output_queue.extend(self.priv_buyer.retrieve_done())

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
            pool_account = pool.return_account()
            await pool_account.async_check_valid()
            await self.database.update_account_fp_count(pool_account.fast_pass_count, pool_account)
            await self.database.release_account(pool_account)
            await pool.close()
            self.pools.remove(pool)

        self._buyer_queue.clean_queue()

        await self.database.release_accounts_over_five_in_use_minutes()
