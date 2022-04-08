import asyncio
import io
import re
import os
import pickle
from typing import Union, List, Tuple, Dict, Optional

import discord
import privatebinapi
from discord.ext import commands
from discord.ext.commands import Context

from bot.bot_utils import generate_embed, emoji_selection_detector, text_response_waiter
from dependencies.database import database_exceptions, Database
from dependencies.utils import generic_buyer, generic_buyer_obj, paste_generator
from dependencies.webnovel.classes import SimpleBook, Book, Chapter
from dependencies.webnovel.utils import book_string_to_book_id
from dependencies.webnovel.web.book import full_book_retriever, generate_thumbnail_url_or_file, trail_read_books_finder
from . import bot_checks

from dependencies.webnovel.web.font_decoder import decoder as font_decoder_module
from dependencies.webnovel.web.font_decoder import utils as font_utilities

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
        self.font_cache = []
        self.letters_bitwise = {}
        self.retrieved_dataset = False
        self.being_retrieved = False
        try:
            os.mkdir("chapters")
        except FileExistsError:
            pass

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

    @commands.command(aliases=['b'], enabled=False)
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
                await self.refresh_book(ctx, book_obj.id)

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


    @commands.command(aliases=['bd'])
    @bot_checks.is_whitelist()
    @bot_checks.check_permission_level(2)
    async def buy_decode(self, ctx: Context, *, user_input: str = None):
        cache_chapters = os.listdir("chapters")
        chapters_from_cache = []

        if self.retrieved_dataset is False:
            if self.being_retrieved is True:
                await ctx.send("The data set is still being retrieved!!! Please Wait!!")
            else:
                self.being_retrieved = True
                self.font_cache = await self.db.retrieve_top_50_fonts()
                self.letters_bitwise = await self.db.retrieve_char_bitwise()
                self.retrieved_dataset = True

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
        if len(parsed_chapter_requests) > 1:
            await ctx.send("Please only request 1 book at a time! Try again!")
            return

        book_chapter_requests = {}
        books_objs = {}
        for book_string, ranges in parsed_chapter_requests.items():
            book_obj = await self.__interactive_book_chapter_string_to_book(ctx, book_string)
            if not book_obj:
                continue
            if book_chapter_requests.get(book_obj.id) is None:
                book_chapter_requests[book_obj.id] = []
                await self.refresh_book(ctx, book_obj.id)

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
                chap_objs_non_priv_non_cache = []
                for chapter in chap_objs_non_priv:
                    if f"{chapter.parent_id}_{chapter.id}" in cache_chapters:
                        chapters_from_cache.append(chapter)
                    else:
                        chap_objs_non_priv_non_cache.append(chapter)

                batch_chap_objs = [chap_objs_non_priv_non_cache[i:i + 20]
                                   for i in range(0, len(chap_objs_non_priv_non_cache),
                                                  20) if chap_objs_non_priv_non_cache[i:i + 20]]

                # Batching chapter by 20
                if chap_objs_non_priv_non_cache:
                    book_chapter_requests[book_obj.id].extend(batch_chap_objs)

        if len(book_chapter_requests) < 1:
            await ctx.send("No book found!!!")

        async_tasks = []
        no_chapters_found_book_names = set()
        for book_id, chapter_lists in book_chapter_requests.items():
            for chapters in chapter_lists:
                if len(chapters) == 0:
                    no_chapters_found_book_names.add(books_objs[book_id].name)
                    continue
                tsk = asyncio.create_task(generic_buyer_obj(self.db, books_objs[book_id], *chapters))
                async_tasks.append(tsk)
        lists = await asyncio.gather(*async_tasks)
        lists: List[List[Union[Chapter, str]]]
        ###
        # paste_tasks = [asyncio.create_task(ctx.send(paste)) for paste in pastes]
        # await asyncio.gather(*paste_tasks)
        ###
        chapters_to_decode = []
        async_tasks.clear()
        for list_ in lists:
            for chapter in list_:
                if type(chapter) == Chapter:
                    chapters_to_decode.append(chapter)
                    try:
                        with open(f"chapters/{chapter.parent_id}_{chapter.id}", "wb") as file:
                            file.write(pickle.dumps(chapter))
                    except FileNotFoundError:
                        os.makedirs("chapters")
                        with open(f"chapters/{chapter.parent_id}_{chapter.id}", "wb") as file:
                            file.write(pickle.dumps(chapter))
                else:
                    async_tasks.append(asyncio.create_task(ctx.send(chapter)))

        for chapter_to_load in chapters_from_cache:
            with open(f"chapters/{chapter_to_load.parent_id}_{chapter_to_load.id}", "rb") as file:
                chapters_to_decode.append(pickle.load(file))

        print(True)
        async_tasks.clear()
        pastes = []
        for chapter in chapters_to_decode:
            content_info_helper = font_utilities.ContentInfo.from_content_info(chapter.content)
            decoder = font_decoder_module.MetricsBasedDecoder(content_info_helper.get_font())
            for font in self.font_cache:
                font_file = io.BytesIO()
                font_file.write(font[1])
                font_file.seek(0)
                decoder.add_sample(font_file, font[0])
            obfs = content_info_helper.unscramble()
            tl_map, order_map, unknown_glyphs = decoder._build_map()
            book = await self.db.retrieve_simple_book(chapter.parent_id)
            if len(unknown_glyphs) == 0:
                decoded_content = obfs.translate(tl_map)
                chapter.encrypt_type = 0
                chapter.content = decoded_content
                async_tasks.append(asyncio.create_task(paste_generator(book.name, chapter)))
                # url = await privatebin.upload_to_privatebin(decoded_content)
                # await ctx.send(url)
            else:
                letters_to_be_added = []
                await ctx.send("There are some things I don't know how to read :( Could you help me?")
                for order_num, (char, image_obj) in unknown_glyphs.items():
                    image_obj.seek(0)
                    message = await ctx.send("Please reply me what character this image is, **This is CASE SENSITIVE**",
                                             file=discord.File(image_obj, "image.png"))
                    char_message = await text_response_waiter(ctx, message, 180)
                    letters_to_be_added.append((order_num, char, image_obj, char_message.clean_content,
                                                content_info_helper.get_font()))
                    print(True)
                confirmation_list = [(char, image_obj) for order_num,
                                     coded_char, image_obj, char, font_file in letters_to_be_added]
                await ctx.send("You told me the following images are the following: ")
                for (char, image_obj) in confirmation_list:
                    image_obj.seek(0)
                    await ctx.send(char, file=discord.File(image_obj, "image.png"))
                message = await ctx.send("Reply to this message with `yes` if you are sure so that I can "
                                         "save this for future chapters")
                confirmation = await text_response_waiter(ctx, message, 120)
                if confirmation is None:
                    await ctx.send("Did not receive confirmation, will skip the chapter")
                elif confirmation.clean_content.lower() == "yes":
                    await ctx.send("Learning new letters......")
                    print(True)
                    for item_to_add in letters_to_be_added:
                        order_map[item_to_add[0]] = item_to_add[3]
                        tl_map[ord(item_to_add[1])] = item_to_add[3]
                    order_nums = list(order_map.keys())
                    order_nums.sort()
                    letters_to_join = []
                    for x in order_nums:
                        letters_to_join.append(order_map[x])
                    font_letters = ''.join(letters_to_join)
                    bitwise_letters = list(self.letters_bitwise.keys())
                    bitwise_values = list(self.letters_bitwise.values())
                    font_num = 0
                    for char in letters_to_join:
                        if char in bitwise_letters:
                            font_num = font_num | self.letters_bitwise[char]
                        else:
                            starting_num = 1
                            while True:
                                if starting_num not in bitwise_values:
                                    self.letters_bitwise[char] = starting_num
                                    await self.db.insert_new_char_bitwise(starting_num, char)
                                    bitwise_values.append(starting_num)
                                    break
                                else:
                                    starting_num = starting_num << 1
                            font_num = font_num | starting_num
                    print(True)
                    font = content_info_helper.get_font()
                    font.seek(0)
                    font_bytes = font.read()
                    await self.db.insert_new_font(font_bytes, font_num, font_letters, chapter.id)
                    self.font_cache.append((font_letters, font_bytes))

                    decoded_content = obfs.translate(tl_map)
                    chapter.encrypt_type = 0
                    chapter.content = decoded_content
                    async_tasks.append(asyncio.create_task(paste_generator(book.name, chapter)))
                else:
                    await ctx.send(f"Received negative confirmation, ignoring chapter {chapter.index} of {book.name}.")
                # print("There is an unknown glyph in the paste!!!!!")
        pastes = await asyncio.gather(*async_tasks)
        async_tasks.clear()
        for paste in pastes:
            async_tasks.append(asyncio.create_task(ctx.send(paste)))
        await asyncio.gather(*async_tasks)
        print(True)

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

    @commands.command()
    @bot_checks.check_permission_level(8)
    async def build_sample(self, ctx: Context):
        chapters = os.listdir("chapters")
        chapters_obj = []
        fonts = []
        if len(chapters) > 5:
            for x in range(0, 5):
                with open(f"chapters/{chapters[x]}", "rb") as file:
                    chapters_obj.append(pickle.load(file))
        else:
            for chapter in chapters:
                with open(f"chapters/{chapter}", "rb") as file:
                    chapters_obj.append(pickle.load(file))

        for chapter in chapters_obj:
            util_obj = font_utilities.ContentInfo.from_content_info(chapter.content)
            while True:
                message = await ctx.send(content="Please reply me the content of this font in its glyph order.",
                                         file=discord.File(util_obj.get_font(), filename="font.ttf"))
                data = await text_response_waiter(ctx, message, 300)
                if data is None:
                    return
                message = await ctx.send(f"Are you sure the content of the font is:  `{data.clean_content}` ? "
                                         f"Please reply with a `yes` if you ae sure.")
                confirmation = await text_response_waiter(ctx, message, 120)
                if confirmation is None:
                    return
                if confirmation.clean_content.lower() == 'yes':
                    fonts.append((util_obj.get_font().read(), data.clean_content, chapter.id))
                    break
                else:
                    await ctx.send("Aborting!! initiating the process again")

        for individual_font_data in fonts:
            number = 0
            chars_list = list(set(list(individual_font_data[1])))
            bit_wise_letters = self.letters_bitwise.keys()
            bitwise_values = self.letters_bitwise.values()
            for char in chars_list:
                if char in bit_wise_letters:
                    number = number | self.letters_bitwise[char]
                else:
                    starting_num = 1
                    while True:
                        if starting_num not in bitwise_values:
                            self.letters_bitwise[char] = starting_num
                            await self.db.insert_new_char_bitwise(starting_num, char)
                            break
                        else:
                            starting_num = starting_num << 1
                    number = number | starting_num
            await self.db.insert_new_font(individual_font_data[0], number, individual_font_data[1],
                                          individual_font_data[2])
        print("Sample Imported")


    @commands.command(aliases=['ib'], enabled=False)
    @bot_checks.is_whitelist()
    @bot_checks.check_permission_level(2)
    async def id_buy(self, ctx: Context, book_id: int, starting_index: int):
        book_obj = await full_book_retriever(book_id)
        chapter_obj = book_obj.retrieve_chapter_by_index(starting_index)
        paste = await generic_buyer(self.db, book_obj, chapter_obj)
        await ctx.send(paste)

    @commands.command(aliases=['bl'],  enabled=False)
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
        msg = f"Metadata update `{qi_book.name}`: "
        if len(chapters_to_add) != 0:
            msg += f" {len(chapters_to_add)} + "
            await self.db.batch_add_chapters(*chapters_to_add)
        if len(chapters_to_update) != 0:
            msg += f" {len(chapters_to_update)} ⟳ "
            await self.db.batch_update_chapters(*chapters_to_update)
        if len(chapters_to_remove) != 0:
            msg += f" {len(chapters_to_remove)} − "
            await self.db.batch_delete_chapters(*chapters_to_remove)
        await ctx.send(msg)

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
