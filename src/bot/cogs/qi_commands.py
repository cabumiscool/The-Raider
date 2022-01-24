import asyncio
import re
from typing import Union, List, Tuple, Dict, Optional

import discord
import privatebinapi
from discord.ext import commands
from discord.ext.commands import Context

from bot.bot_utils import generate_embed, emoji_selection_detector
from dependencies.database import database_exceptions, Database
from dependencies.utils import generic_buyer
from dependencies.webnovel.classes import SimpleBook, Book
from dependencies.webnovel.utils import book_string_to_book_id
from dependencies.webnovel.web.book import full_book_retriever, generate_thumbnail_url_or_file, trail_read_books_finder
from . import bot_checks

NUMERIC_EMOTES = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']

range_match = re.compile(r'\[?\**`?(\d+)[ \-]*(\d*)`?\**]?,? ?')
bloat_content_match = re.compile(r'((:sparkles: )?\**\d+\** chapter[s]? missing from )')
title_range_match = re.compile(
    r'[`"\' ]?([\w\d,!.:()’?´+\-\' ]+?)[\'"` ]? ?[\s\- ]+((?:\[?\**`?\d+[ \-]*\d*`?\**]?,? ?)+)\n')


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
        book_string_and_ranges.setdefault(book_string, [])
        book_string_and_ranges[book_string].extend(chapter_indices)
    return book_string_and_ranges


def build_book_embed(book: Book, cover_url: str, author: discord.Member):
    if book.qi_abbreviation:
        abbreviation_name = "Abbreviation:"
    else:
        abbreviation_name = "Pseudo Abbreviation"
    priv_fields = [("Is Privilege?:", book.privilege)]
    if book.privilege:
        priv_fields.extend([("# Privilege Chapters:", book.return_priv_chapters_count()),
                            ("Last Non Privilege Chapter:",
                             book.total_chapters - book.return_priv_chapters_count())])
    embed = generate_embed(book.name, author,
                           ("Book Id:", book.id),
                           ("Has Abbreviation:", book.qi_abbreviation),
                           (abbreviation_name, book.abbreviation),
                           ("Total Chapters:", book.total_chapters),
                           ("Book Status", book.book_status_text),
                           ("Type:", book.book_type),
                           ("Read Type:", book.read_type),
                           *priv_fields,
                           image_url=cover_url)
    return embed


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

    @commands.command(aliases=['b'])
    @bot_checks.is_whitelist()
    @bot_checks.check_permission_level(2)
    async def buy(self, ctx: Context, *, user_input: str = None):
        # request parser
        removed_chapters = {}
        if user_input is None:
            user_input = ctx.message.content
        if user_input.startswith('.'):
            user_input = user_input[user_input.find(' '):]
        if not user_input.endswith('\n'):  # To make regex parsing easier
            user_input += '\n'
        parsed_chapter_requests = book_string_and_range_matcher(user_input)

        # retrieves the chapters from the db
        book_chapter_requests = {}
        books_objs = {}
        for book_string, ranges in parsed_chapter_requests.items():
            book_obj = await self.__interactive_book_chapter_string_to_book(ctx, book_string)
            if not book_obj:
                continue
            if book_chapter_requests.get(book_obj.id) is None:
                book_chapter_requests[book_obj.id] = []

            if books_objs.get(book_obj.id) is None:
                books_objs[book_obj.id] = book_obj

            for range_start, range_end in ranges:
                chap_objs = await self.db.get_chapter_objs_from_index(book_obj.id, range_start, range_end)

                # TODO add some sort of feedback when priv chapters are removed
                # removing priv chapters from list
                chap_objs_non_priv = []
                for chapter in chap_objs:
                    if chapter.is_privilege is not True:
                        chap_objs_non_priv.append(chapter)
                    else:
                        if chapter.parent_id in removed_chapters:
                            removed_chapters[chapter.parent_id]['chs'].add(chapter.index)
                        else:
                            removed_chapters[chapter.parent_id] = {"book": book_obj, "chs": {chapter.index}}

                # divides in batches the chapters about to be bought
                batch_chap_objs = [chap_objs_non_priv[i:i + 20]
                                   for i in range(0, len(chap_objs_non_priv), 20) if chap_objs_non_priv[i:i + 20]]

                # Batching chapter by 20
                if chap_objs_non_priv:
                    book_chapter_requests[book_obj.id].extend(batch_chap_objs)

        async_tasks = []
        no_chapters_found_book_names = set()
        for book_id, chapter_lists in book_chapter_requests.items():
            for chapters in chapter_lists:
                if len(chapters) == 0:
                    no_chapters_found_book_names.add(books_objs[book_id].name)
                    continue
                tsk = asyncio.create_task(generic_buyer(self.db, books_objs[book_id], *chapters))
                async_tasks.append(tsk)

        pastes = await asyncio.gather(*async_tasks)
        paste_tasks = [asyncio.create_task(ctx.send(paste)) for paste in pastes]
        await asyncio.gather(*paste_tasks)

        if len(removed_chapters) != 0:
            messages = []
            for book_id, book_data in removed_chapters.items():
                missing_chapters_lsit = list(book_data['chs'])
                missing_chapters_lsit = [str(chapter_ind) for chapter_ind in missing_chapters_lsit]
                missing_chapters_lsit.sort()
                missing_chapters = ", ".join(missing_chapters_lsit)
                messages.append(f"The following chapters for `{book_data['book'].name}` | book id:"
                                f"  `{book_data['book'].id}` could not be bought as "
                                f"they are privilege chapters:  {missing_chapters}")
            for message in messages:
                await ctx.send(message)

        if no_chapters_found_book_names:
            error_msg = "The chapters entries range given for some books were not found on the db. A possible cause " \
                        "is that this book is still in the background queue or a library account has totally expired" \
                        " preventing updates from being found. Affected Books:\n" \
                        "\n".join(no_chapters_found_book_names)
            await ctx.send(error_msg)

    @commands.command(aliases=['ib'])
    @bot_checks.is_whitelist()
    @bot_checks.check_permission_level(2)
    async def id_buy(self, ctx: Context, book_id: int, starting_index: int):
        book_obj = await full_book_retriever(book_id)
        chapter_obj = book_obj.retrieve_chapter_by_index(starting_index)
        paste = await generic_buyer(self.db, book_obj, chapter_obj)
        await ctx.send(paste)

    @commands.command(aliases=['bl'])
    @bot_checks.check_permission_level(3)
    async def buy_link(self, ctx: Context, pastebin_link: str):
        paste = await privatebinapi.get_async(pastebin_link)
        await self.buy(ctx, user_input=paste['text'])

    @commands.command(aliases=['qi', 'q'])
    @bot_checks.check_permission_level(6)
    async def qi_book(self, ctx: Context, book_id: int):
        await ctx.send(f'Book ID Received: {book_id}')
        try:
            db_book = await self.db.retrieve_complete_book(book_id)
            await ctx.send(f'Book already in DB. Name:  {db_book.name}.    Enabled?:  {bool(db_book.library_number)}')
        except database_exceptions.NoEntryFoundInDatabaseError:
            await ctx.send(f"Book - {book_id} is not available in the Database. Retrieving from qi and adding...")
            full_book = await full_book_retriever(book_id)
            await self.db.insert_new_book(full_book)
            await ctx.send(f"Added {full_book.name} to database")

    @commands.command()
    @bot_checks.check_permission_level(6)
    async def grab_trial(self, ctx: Context, add_to_db: Optional[str]):
        """
        Grabs the latest trail novel IDs. Can be followed by any value to add the books to DB
        """
        trial_book_ids = await trail_read_books_finder()
        if len(trial_book_ids) == 0:
            return await ctx.reply('No trailer books were parsed!')
        await ctx.reply('**Trail Book IDs Found:**\n' + '\n'.join([str(book_id) for book_id in trial_book_ids]))

        for book_id in trial_book_ids:
            try:
                db_book = await self.db.retrieve_complete_book(book_id)
                await ctx.send(f'Book: `{db_book.name}` in DB.    Enabled?:  {bool(db_book.library_number)}')
            except database_exceptions.NoEntryFoundInDatabaseError:
                full_book = await full_book_retriever(book_id)
                await self.db.insert_new_book(full_book)
                await ctx.send(f"Added `{full_book.id}` - `{full_book.name}` to database")

    @bot_checks.check_permission_level(6)
    @commands.command()
    async def refresh_book(self, ctx: Context, book_id: int):
        qi_book = await full_book_retriever(book_id)
        await ctx.send(f"Checking metadata of {qi_book.name}")
        db_book = await self.db.retrieve_complete_book(book_id)
        qi_book_volumes = qi_book.return_volume_list()
        db_book_volumes = db_book.return_volume_list()

        qi_book_chapter_list = []
        for volume in qi_book_volumes:
            qi_book_chapter_list.extend(volume.return_all_chapter_objs())
        qi_book_chapter_dict = {chapter.id: chapter for chapter in qi_book_chapter_list}

        db_book_chapter_list = []
        for volume in db_book_volumes:
            db_book_chapter_list.extend(volume.return_all_chapter_objs())
        db_book_chapter_dict = {chapter.id: chapter for chapter in db_book_chapter_list}

        chapters_to_add = []
        chapters_to_update = []
        chapters_to_remove = []

        for chapter_id, chapter_obj in qi_book_chapter_dict.items():
            if chapter_id not in db_book_chapter_dict:
                chapters_to_add.append(chapter_obj)
                continue
            db_chapter_obj = db_book_chapter_dict[chapter_id]
            del db_book_chapter_dict[chapter_id]
            if chapter_obj != db_chapter_obj:
                chapters_to_update.append(chapter_obj)
        for chapter_id, chapter_obj in db_book_chapter_dict.items():
            chapters_to_remove.append(chapter_obj)

        await self.db.update_book(qi_book)
        await ctx.send(f"Metadata updated for {qi_book.name}")
        if len(chapters_to_add) != 0:
            await ctx.send(f"Adding {len(chapters_to_add)} chapter of book {qi_book.name}")
            await self.db.batch_add_chapters(*chapters_to_add)
        if len(chapters_to_update) != 0:
            await ctx.send(f"Updating metadata of {len(chapters_to_update)} chapters for book {qi_book.name}")
            await self.db.batch_update_chapters(*chapters_to_update)
        if len(chapters_to_remove) != 0:
            await ctx.send(f"Deleting {len(chapters_to_remove)} chapters from the db of book {qi_book.name}")
            await self.db.batch_delete_chapters(*chapters_to_remove)
        await ctx.send(f"Metadata successfully updated for {qi_book.name}")

    @commands.group(brief='Checks the metadata of an object either from qi or db, for more info use [help check]')
    @bot_checks.check_permission_level(6)
    async def check(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send('No valid operation was requested')

    @check.group(brief='Checks the metadata of objects from qi')
    @bot_checks.check_permission_level(6)
    async def qi(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send('No valid operation was requested')

    @check.group(brief='Checks the metadata of objects from the internal db')
    @bot_checks.check_permission_level(6)
    async def db(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send('No valid operation was requested')

    @qi.command(brief='Retrieves the metadata of the given book id from qi and displays it',
                name='book')
    @bot_checks.check_permission_level(6)
    async def qi_book_check(self, ctx: Context, book_id: int):
        book: Book = await full_book_retriever(book_id)
        author = ctx.author
        cover_url = await generate_thumbnail_url_or_file(book.id)
        embed = build_book_embed(book, cover_url, author)
        await ctx.send(embed=embed)

    @db.command(brief='Retrieves the metadata of the given book id from the internal db and displays it')
    @bot_checks.check_permission_level(6)
    async def book(self, ctx: Context, book_id: int):
        book: Book = await self.db.retrieve_complete_book(book_id)
        author = ctx.author
        cover_url = await generate_thumbnail_url_or_file(book.id)
        embed = build_book_embed(book, cover_url, author)
        await ctx.send(embed=embed)

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
