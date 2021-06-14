import random
import time

import aiohttp

from dependencies.database import Database
from dependencies.webnovel.web import account
from .base_service import BaseService


class CurrencyFarmerService(BaseService):
    def __init__(self, database: Database):
        super().__init__(name="Currency farming service", output_service=False)
        self.db = database
        self.last_updated_energy_books = 0
        self.energy_books = []
        self.power_books = []

    async def main(self):
        if time.time() - self.last_updated_energy_books >= 43200:
            self.energy_books = await account.retrieve_energy_stone_books()
            self.power_books = await account.retrieve_power_stone_books()
            self.last_updated_energy_books = time.time()

        account_to_farm = await self.db.retrieve_account_for_farming()
        if account_to_farm is None:
            return

        account_is_working = await account_to_farm.async_check_valid()
        if account_is_working is False:
            await self.db.expired_account(account_to_farm)
            return

        async with aiohttp.ClientSession(cookies=account_to_farm.cookies) as session:
            claim_farmed, power_stone_farmed, energy_stone_farmed = await account.retrieve_farm_status(session=session)

            if claim_farmed is False:
                await account.claim_login(session=session)

            if power_stone_farmed is False:
                await account.claim_power_stone(book_id=self.power_books[random.randint(0, len(self.power_books) - 1)],
                                                session=session)

            if energy_stone_farmed is False:
                await account.claim_energy_stone(book=self.energy_books[random.randint(0, len(self.energy_books) - 1)],
                                                 session=session)

        await account_to_farm.async_check_valid()

        await self.db.update_account_fp_count(fp_count=account_to_farm.fast_pass_count, account=account_to_farm,
                                              farm_update=True)
