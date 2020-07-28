import asyncio
from bot.bot import Raider


def run_bot():
    loop = asyncio.get_event_loop()
    bot = Raider()
    bot.run()


if __name__ == '__main__':
    run_bot()