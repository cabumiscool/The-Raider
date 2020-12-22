import re
from typing import Union, List, Tuple, Dict

from discord.ext import commands
from discord.ext.commands import Context

from bot.bot_utils import generate_embed, emoji_selection_detector

from dependencies.webnovel.classes import Book
from dependencies.webnovel.utils import book_string_matcher
from dependencies.database import Database
from . import bot_checks


NUMERIC_EMOTES = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']

range_matcher = re.compile(r'\[?\**`?(\d+)[ \-]*(\d*)`?\**]?,? ?')
bloat_content_matcher = re.compile(r'((:sparkles: )?\**\d+\** chapter[s]? missing from )')
title_and_ranges_matcher = re.compile(r'`?([\w\d,!.:()’?\-\' ]+?)`? ?[\s\- ]+((?:\[?\**`?\d+[ \-]*\d*`?\**]?,? ?)+)')


def book_string_and_range_matcher(user_string: str) -> Dict[str, List[Tuple[int, int]]]:
    clean_input = bloat_content_matcher.sub('', user_string)
    title_ranges_pairs = title_and_ranges_matcher.findall(clean_input)
    book_string_and_ranges = {}
    for title, ranges in title_ranges_pairs:
        chapter_indices = []
        ranges_list = range_matcher.findall(ranges)
        for chapter_range in ranges_list:
            range_start = int(chapter_range[0])
            range_end = int(chapter_range[1])
            if not range_end:
                range_end = range_start
            chapter_indices.append((range_start, range_end))
        book_string_and_ranges[title] = chapter_indices
    return book_string_and_ranges


class QiCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db

    def __interactive_book_string_to_book(self, ctx: Context, book_string: str, limit: int = 5) -> Union[Book, None]:
        possible_matches = await book_string_matcher(self.db, book_string, limit)
        if possible_matches is None:
            return None
        elif len(possible_matches) == 1:
            return possible_matches[0][0]

        # TODO: Decide on embed colours
        description = 'Please select the required book:'
        embed = generate_embed(f'Book Selection for {book_string}', ctx.author, description=description, color=0)
        for x in range(len(possible_matches)):
            book = possible_matches[x][0]
            score = possible_matches[x][1]
            name = f"{NUMERIC_EMOTES[x]} {book.name}"
            value = f"Score : `{score}`\n" \
                    f"Abbreviation : `{book.abbreviation}`"
            embed.add_field(name=name, value=value)

        chosen_emote = await emoji_selection_detector(ctx, NUMERIC_EMOTES[:len(possible_matches)], embed, 30)
        if chosen_emote is None:
            return None
        else:
            return possible_matches[NUMERIC_EMOTES.index(chosen_emote)][0]

    @commands.command(aliases=['b'])
    @bot_checks.is_whitelist()
    @bot_checks.check_permission_level(2)
    async def buy(self, ctx: Context, *args):
        user_input = " ".join(args)
        parsed_chapter_requests = book_string_and_range_matcher(user_input)
        book_chapter_requests = {}
        for book_string in parsed_chapter_requests:
            book: Book = self.__interactive_book_string_to_book(ctx, book_string)
            if book:
                book_chapter_requests[book.id] = book, parsed_chapter_requests[book_string]

        # TODO: Link up buyer logic with the buyer service in a common location under dependencies or create a new class
