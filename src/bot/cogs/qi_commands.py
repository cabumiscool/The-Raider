import asyncio
import re
import time
from operator import attrgetter
from typing import Union, List, Tuple, Dict

import privatebinapi
from discord.ext import commands
from discord.ext.commands import Context

from bot.bot_utils import generate_embed, emoji_selection_detector
from dependencies.database import database_exceptions
from dependencies.database.database import Database
from dependencies.privatebin import upload_to_privatebin
from dependencies.webnovel.classes import SimpleBook, SimpleChapter
from dependencies.webnovel.utils import book_string_to_book_id
from dependencies.webnovel.waka import book as waka_book
from dependencies.webnovel.web import book
from . import bot_checks

NUMERIC_EMOTES = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']

range_match = re.compile(r'\[?\**`?(\d+)[ \-]*(\d*)`?\**]?,? ?')
bloat_content_match = re.compile(r'((:sparkles: )?\**\d+\** chapter[s]? missing from )')
title_range_match = re.compile(
    r'[`"\' ]?([\w\d,!.:()’?\-\' ]+?)[\'"` ]? ?[\s\- ]+((?:\[?\**`?\d+[ \-]*\d*`?\**]?,? ?)+)\n')

paste_metadata = '<h3 data-book-Id="%s" data-chapter-Id="%s" data-almost-unix="%s" ' \
                 'data-SS-Price="%s" data-index="%s" data-is-Vip="%s" data-source="qi_latest" data-from="%s" ' \
                 '>Chapter %s:  %s</h3>'
data_from = ['qi', 'waka-waka']


def book_string_and_range_matcher(user_string: str) -> Dict[str, List[Tuple[int, int]]]:
    clean_input = bloat_content_match.sub('', user_string)
    title_ranges_pairs = title_range_match.findall(clean_input)
    book_string_and_ranges = {}
    for book_string, ranges in title_ranges_pairs:
        chapter_indices = []
        ranges_list = range_match.findall(ranges)
        for chapter_range in ranges_list:
            range_start = int(chapter_range[0])
            if chapter_range[1] == '':
                range_end = range_start
            else:
                range_end = int(chapter_range[1])
            chapter_indices.append((range_start, range_end))
        book_string_and_ranges[book_string] = chapter_indices
    return book_string_and_ranges


class QiCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db

    async def __interactive_book_chapter_string_to_book(self, ctx: Context, book_string: str, limit: int = 5
                                                        ) -> Union[SimpleBook, None]:
        all_matches_dict = await self.db.retrieve_all_book_string_matches()
        possible_matches = await book_string_to_book_id(all_matches_dict, book_string, limit)

        if possible_matches is None:
            return None
        if len(possible_matches) == 1:
            book_obj = await self.db.retrieve_simple_book(possible_matches[0][0])
            return book_obj

        description = 'Please select the required book:'
        embed = generate_embed(f'Book Selection for {book_string}', ctx.author, description=description, color=200)
        for index, (book_id, score) in enumerate(possible_matches):
            book_obj = await self.db.retrieve_simple_book(book_id)
            score = possible_matches[index][1]
            name = f"{NUMERIC_EMOTES[index]} {book_obj.name}"
            value = f"Score : `{score}`\n" \
                    f"Abbreviation : `{book_obj.abbreviation}`"
            embed.add_field(name=name, value=value)

        chosen_emote = await emoji_selection_detector(ctx, NUMERIC_EMOTES[:len(possible_matches)], embed, 30)
        if chosen_emote is None:
            return None
        return await self.db.retrieve_simple_book(possible_matches[NUMERIC_EMOTES.index(chosen_emote)][0])

    async def buy_wrapper(self, book_: SimpleBook, *chapters: SimpleChapter):
        waka_proxy = await self.db.retrieve_proxy(1)

        # TODO move somewhere else
        async def individual_buyer(chapter: SimpleChapter):
            buyer_account = await self.db.retrieve_buyer_account()
            while True:
                working_account = await buyer_account.async_check_valid()
                if working_account:
                    break
                else:
                    buyer_account = await self.db.retrieve_buyer_account()

            if chapter.is_privilege:
                chapter_obj = await waka_book.chapter_retriever(book_id=chapter.parent_id, chapter_id=chapter.id,
                                                                volume_index=chapter.volume_index, proxy=waka_proxy)
            else:
                chapter_obj = await book.chapter_buyer(book_id=chapter.parent_id, chapter_id=chapter.id,
                                                       account=buyer_account)

            await self.db.release_account(buyer_account)

            return chapter_obj

        async_tasks = [asyncio.create_task(individual_buyer(chapter)) for chapter in chapters]
        ranges = [chapter.index for chapter in chapters]
        ranges.sort()
        chapters = await asyncio.gather(*async_tasks)
        chapters.sort(key=attrgetter('index'))
        chapters_strings = []
        for chapter in chapters:
            metadata = paste_metadata % (
                chapter.parent_id, chapter.id, time.time(), chapter.price, chapter.index,
                chapter.is_vip, data_from[chapter.is_privilege], chapter.index, chapter.name)
            chapters_strings.append('\n'.join((metadata, chapter.content)))

        complete_string = '\n'.join(chapters_strings)

        paste_response = await upload_to_privatebin(complete_string)
        # paste_response = await privatebinapi.send_async(server='https://vim.cx/', text=complete_string,
        #                                                 formatting="markdown")
        if ranges[0] == ranges[-1]:
            range_str = f'{ranges[0]}'
        else:
            range_str = f'{ranges[0]}-{ranges[-1]}'
        paste_url = f"!paste {book_.name} - {range_str} <{paste_response}>"

        return paste_url

    @commands.command(aliases=['b'])
    @bot_checks.is_whitelist()
    @bot_checks.check_permission_level(2)
    async def buy(self, ctx: Context):
        user_input = ctx.message.content
        user_input = user_input[user_input.find(' '):]
        if not user_input.endswith('\n'):  # To make regex parsing easier
            user_input += '\n'
        parsed_chapter_requests = book_string_and_range_matcher(user_input)
        book_chapter_requests = {}
        books_objs = {}
        for book_string in parsed_chapter_requests:
            book_obj = await self.__interactive_book_chapter_string_to_book(ctx, book_string)
            if book_obj:
                if book_chapter_requests.get(book_obj.id) is None:
                    book_chapter_requests[book_obj.id] = []

                if books_objs.get(book_obj.id) is None:
                    books_objs[book_obj.id] = book_obj

                for range_start, range_end in parsed_chapter_requests[book_string]:
                    chapter_objs = await self.db.get_chapter_objs_from_index(book_obj.id, range_start, range_end)
                    # chapter_ids_list = [chapter_ids[i:i + 20] for i in range(0, len(chapter_ids), 20)]  # Not sure
                    # if understood this logic correctly and copied it for the change
                    book_chapter_requests[book_obj.id].extend(chapter_objs)

        async_tasks = []
        for book_id, chapters_list in book_chapter_requests.items():
            async_tasks.append(asyncio.create_task(self.buy_wrapper(books_objs[book_id], *chapters_list)))

        pastes = await asyncio.gather(*async_tasks)
        paste_tasks = [asyncio.create_task(ctx.send(paste)) for paste in pastes]
        await asyncio.gather(*paste_tasks)

    @commands.command(aliases=['ib'])
    @bot_checks.is_whitelist()
    @bot_checks.check_permission_level(2)
    async def id_buy(self, ctx: Context, book_id: int, starting_index: int):
        book_obj = await book.full_book_retriever(book_id)
        chapter_obj = book_obj.retrieve_chapter_by_index(starting_index)
        paste = await self.buy_wrapper(book_obj, chapter_obj)
        await ctx.send(paste)

    @commands.command(aliases=['bl'])
    @bot_checks.check_permission_level(3)
    async def buy_link(self, ctx: Context, pastebin_link: str):
        paste = await privatebinapi.get_async(pastebin_link)
        await self.buy(ctx, paste['text'])

    @commands.command(aliases=['qi', 'q'])
    @bot_checks.check_permission_level(6)
    async def qi_book(self, ctx: Context, book_id: int):
        await ctx.send(f'Book ID Received: {book_id}')
        try:
            db_book = await self.db.retrieve_complete_book(book_id)
            await ctx.send(f'Book found in db with the name of:  {db_book.name}.    Enabled?:  '
                           f'{bool(db_book.library_number)}')
        except database_exceptions.NoEntryFoundInDatabaseError:
            await ctx.send(f"Book - {book_id} is not available in the Database. Retrieving from qi and adding...")
            full_book = await full_book_retriever(book_id)
            await self.db.insert_new_book(full_book)
            await ctx.send(f"Added {full_book.name} to database")

    @commands.command(aliases=['batch_add, many_add'])
    async def batch_add_books(self, ctx: Context, *book_ids):
        pass

    @commands.command(enabled=False)
    async def test_q(self, ctx: Context):
        books_list = await self.db.retrieve_all_simple_books()
        print(True)


def setup(bot):
    cog = QiCommands(bot)
    bot.add_cog(cog)
