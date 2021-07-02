from discord.ext import commands
from discord.ext.commands import Context

from fuzzywuzzy.process import extractBests

import asyncio
import typing

from dependencies.database.database import Database

from dependencies.webnovel import classes

from bot.bot_utils import generate_embed, emoji_selection_detector


NUMERIC_EMOTES = {'1⃣': 0, '2⃣': 1, '3⃣': 2, '4⃣': 3, '5⃣': 4}
NUMERIC_EMOTES_LIST = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣']


def book_name_matcher(string_to_match: str, options: list):
    possible_matches = extractBests(string_to_match, options)
    if len(possible_matches) == 1 or possible_matches[0][1] > possible_matches[1][1] + 3:
        return [possible_matches[0]]
    else:
        return possible_matches


class ChapterPingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db

    @commands.group()
    async def ping(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send('No valid operation was requested')

    @ping.group()
    async def book(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send('No valid operation was requested')

    @book.command()
    async def add(self, ctx: Context, *args: str):
        complete_sting = ' '.join(args)
        if complete_sting == '':
            await ctx.send("You didn't tell me any book :(.... do you think I have psychic powers?")
            return
        data_dict = await self.db.get_all_books_ids_and_names_dict()
        possible_matches_rated = book_name_matcher(complete_sting, [key for key, value in data_dict.items()])
        possible_matches = [[*data_dict[key], grade] for key, grade in possible_matches_rated]
        if len(possible_matches) == 0:
            await ctx.send("Couldn't find an exact match :(")
            return
        elif len(possible_matches) == 1:
            book_tuple = possible_matches[0]
        else:
            description = 'Please select the book you requested for'
            fields = []
            for x in range(0,5):
                name = f"{NUMERIC_EMOTES_LIST[x]} {possible_matches[x][0]}"
                value = f"Score : {possible_matches[x][3]}"
                if possible_matches[x][1] is not None:
                    value = '\n'.join([value, f'Abbreviation : {possible_matches[x][1]}'])
                fields.append((name, value))
            embed = generate_embed("Book selection", ctx.author, *fields, description=description)
            book_index = NUMERIC_EMOTES.get(await emoji_selection_detector(ctx, NUMERIC_EMOTES_LIST, embed))
            if book_index is None:
                await ctx.send("You didn't select any book, perhaps you realized the book you wanted was too lame? "
                               "Or was it that you don't have the correct name?")
                return
            book_tuple = possible_matches[book_index]

        # Will add an integrity verification in the meantime the sql check is written
        ping_list_book_dict = await self.db.retrieve_user_pings(ctx.author.id)
        if ping_list_book_dict is not None:
            ping_list_book_ids = ping_list_book_dict['books']
        else:
            ping_list_book_ids = []
        if book_tuple[2] in ping_list_book_ids:
            await ctx.send("You already have this book on your ping list. Do you love so much this book that you want "
                           "to be pinged multiple times for the same chapter? :thinking:")
            return

        await ctx.send(f"Adding book `{book_tuple[0]}`")
        await self.db.insert_ping_request(book_tuple[2], ctx.author.id)
        await ctx.send(f"Successfully added the book `{book_tuple[0]}`! Prepare to hear for me even in your nightmares!"
                       f":smiling_imp:")

    @book.command()
    async def remove(self, ctx: Context, *args: str):
        pings_data = await self.db.retrieve_user_pings(ctx.author.id)
        if pings_data is None:
            await ctx.send("Hmmm, you are not in my contacts list... I can't remove what isn't there in the first "
                           "place.\nYour ping list is empty.")
            return
        complete_sting = ' '.join(args)
        if complete_sting == '':
            await ctx.send("You didn't tell me any book :frown:.... do you think I have psychic powers?")
            return
        book_ids = pings_data['books']
        books_obj = []
        tasks = []
        for book_id in book_ids:
            tasks.append(asyncio.create_task(self.db.retrieve_simple_book(book_id)))
        books_obj.extend(await asyncio.gather(*tasks))
        books_obj: typing.List[classes.SimpleBook]

        book_args = []
        book_dict = {None: None}
        for book_obj in books_obj:
            book_arg_list = [book_obj.name, book_obj.id]
            book_dict[book_obj.id] = book_obj
            book_dict[book_obj.name] = book_obj
            if book_obj.qi_abbreviation is True:
                book_args.extend([*book_arg_list, book_obj.abbreviation])
                book_dict[book_obj.abbreviation] = book_obj
            else:
                book_args.extend([*book_arg_list, None])

        possible_matches_rated = book_name_matcher(complete_sting, book_args)
        possible_matches = []
        possible_matches_duplicated = []
        for key, grade in possible_matches_rated:
            if key is None:
                continue
            if key in possible_matches_duplicated:
                continue
            possible_matches_duplicated.append(key)
            possible_matches.append([book_dict[key], grade])

        if len(possible_matches) == 0:
            await ctx.send("Couldn't find an exact match :(")
            return
        elif len(possible_matches) == 1:
            book_obj = possible_matches[0][0]
        else:
            description = 'Please select the book you requested for'
            fields = []
            for x in range(0, len(possible_matches)):
                name = f"{NUMERIC_EMOTES_LIST[x]} {possible_matches[x][0].name}"
                value = f"Score : {possible_matches[x][1]}"
                if possible_matches[x][1] is not None:
                    value = '\n'.join([value, f'Abbreviation : {possible_matches[x][0].abbreviation}'])
                fields.append((name, value))
            embed = generate_embed("Book selection", ctx.author, *fields, description=description)
            book_index = NUMERIC_EMOTES.get(await emoji_selection_detector(ctx,
                                                                           NUMERIC_EMOTES_LIST[0:len(possible_matches)],
                                                                           embed))
            if book_index is None:
                await ctx.send("You didn't select any book, could it be you were hallucinating you had that book on "
                               "your reading list?")
                return
            book_obj = possible_matches[book_index][0]

        await ctx.send(f"Removing `{book_obj.name}` from your ping list.")
        await self.db.remove_ping_request(book_obj.id, ctx.author.id)
        await ctx.send("Successfully removed the book that was going to hell from your ping list. :)")

    @ping.group()
    async def list(self, ctx: Context):
        pings_data = await self.db.retrieve_user_pings(ctx.author.id)
        if pings_data is None:
            await ctx.send("Hmmm, you are not in my contacts list... Request me to ping you about something before "
                           "asking what I know about you")
            return
        book_ids = pings_data['books']
        books_obj = []
        tasks = []
        for book_id in book_ids:
            tasks.append(asyncio.create_task(self.db.retrieve_simple_book(book_id)))
        books_obj.extend(await asyncio.gather(*tasks))
        messages_rows = [f"{'#':5}\t{'Name':70}\tAbbreviation"]
        number = 0
        for book_obj in books_obj:
            book_obj: classes.SimpleBook
            number += 1
            message_row = f"{number:<5}\t{book_obj.name:70}"
            if book_obj.qi_abbreviation is True:
                messages_rows.append('\t'.join([message_row, book_obj.abbreviation]))
            else:
                messages_rows.append(message_row)
        ping_table_string = "```%s```" % "\n".join(messages_rows)
        message = f"**{ctx.author.name}'s Ping List:**{ping_table_string}"
        await ctx.author.send(message)

    @list.command(name='book', hidden=True)
    async def book_list(self):
        pass


def setup(bot):
    cog = ChapterPingCog(bot)
    bot.add_cog(cog)
