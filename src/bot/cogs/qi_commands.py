import re
from typing import Union, List, Tuple, Dict

from discord.ext import commands
from discord.ext.commands import Context
import privatebinapi

from bot.bot_utils import generate_embed, emoji_selection_detector
from dependencies.database.database import Database
from dependencies.database import database_exceptions
from dependencies.webnovel.classes import SimpleBook
from dependencies.webnovel.web import book
from dependencies.webnovel.utils import book_string_to_book_id
from . import bot_checks

NUMERIC_EMOTES = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']

range_match = re.compile(r'\[?\**`?(\d+)[ \-]*(\d*)`?\**]?,? ?')
bloat_content_match = re.compile(r'((:sparkles: )?\**\d+\** chapter[s]? missing from )')
title_range_match = re.compile(r'[`"\']?([\w\d,!.:()’?\-\' ]+?)[\'"`]? ?[\s\- ]+((?:\[?\**`?\d+[ \-]*\d*`?\**]?,? ?)+)')


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
        for index, book_id, score in enumerate(possible_matches):
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

    @commands.command(aliases=['b'])
    @bot_checks.is_whitelist()
    @bot_checks.check_permission_level(2)
    async def buy(self, ctx: Context, *args):
        user_input = " ".join(args)
        parsed_chapter_requests = book_string_and_range_matcher(user_input)
        book_chapter_requests = {}
        for book_string in parsed_chapter_requests:
            book_obj = await self.__interactive_book_chapter_string_to_book(ctx, book_string)
            if book_obj:
                if book_chapter_requests.get(book_obj.id) is None:
                    book_chapter_requests[book_obj.id] = []

                for range_start, range_end in parsed_chapter_requests[book_string]:
                    chapter_ids = await self.db.get_chapter_ids_from_index(book_obj.id, range_start, range_end)
                    chapter_ids_list = [chapter_ids[i:i + 20] for i in range(0, len(chapter_ids), 20)]
                    book_chapter_requests[book_obj.id].extend(chapter_ids_list)

        for book_id in book_chapter_requests:
            for chapter_ids in book_chapter_requests[book_id]:
                paste_data = ''
                for chapter_id in chapter_ids:
                    # TODO: retrieve_buyer_account in database.py needs work
                    account = await self.db.retrieve_buyer_account()
                    chapter = await book.chapter_buyer(book_id, chapter_id, account=account)
                    paste_data += chapter.content
                link = privatebinapi.send(paste_data)
                await ctx.send(link)

    @commands.command(aliases=['qi', 'q'])
    @bot_checks.check_permission_level(6)
    async def qi_book(self, ctx: Context, book_id: int):
        await ctx.send(f'Book ID Received: {book_id}')
        book_in_db = True
        try:
            db_book = await self.db.retrieve_complete_book(book_id)
        except database_exceptions.NoEntryFoundInDatabaseError:
            book_in_db = False
        except Exception as e:
            raise e

        if book_in_db is False:
            await ctx.send(f"Book - {book_id} is not available in the Database. Retrieving from qi and adding")
            full_book = await book.full_book_retriever(book_id)
            await self.db.insert_new_book(full_book)
            await ctx.send(f"successfully added {full_book.name} to database")
        else:
            await ctx.send(f'book found at db with the name of:  {db_book.name}.    enabled?:  '
                           f'{bool(db_book.library_number)}')

    @commands.command(aliases=['batch_add, many_add'])
    async def batch_add_books(self, ctx: Context, *book_ids):
        pass


def setup(bot):
    cog = QiCommands(bot)
    bot.add_cog(cog)
