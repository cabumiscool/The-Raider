import re
from typing import Union

from discord.ext import commands
from discord.ext.commands import Context

from bot.bot_utils import generate_embed, emoji_selection_detector

from dependencies.webnovel.classes import Book
from dependencies.webnovel.utils import book_string_matcher
from dependencies.database import Database
from . import bot_checks


NUMERIC_EMOTES = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']


class QiCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db

    @commands.command(aliases=['b'])
    @bot_checks.check_permission_level(2)
    async def buy(self, ctx: Context, *args) -> Union[SimpleBook, None]:
        pass

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

        chosen_index = await numeric_emoji_selector(ctx, len(possible_matches), 30, embed=embed)
        if chosen_index is None:
            return None
        else:
            return possible_matches[chosen_index][0]
