import asyncio
from typing import Union, List, Tuple, AnyStr

import discord
from discord.ext.commands import Context


def generate_embed(title: str, author: discord.Member, *fields: Tuple[AnyStr, AnyStr], description: str = None,
                   color: int = 0, image_url: str = None) -> discord.Embed:
    """
    It generates an embed with the given parameters
    
    :param title: str - The title of the embed
    :type title: str
    :param author: discord.Member - The author of the embed
    :type author: discord.Member
    :param : title: str, author: discord.Member, *fields: Tuple[AnyStr, AnyStr], description: str =
    None, color: int = 0, image_url: str = None
    :type : Tuple[AnyStr, AnyStr]
    :param description: The description of the embed
    :type description: str
    :param color: The color of the embed, defaults to 0
    :type color: int (optional)
    :param image_url: The URL of the image you want to embed
    :type image_url: str
    :return: A discord.Embed object.
    """
    for field in fields:
        assert len(field) == 2

    if description is None:
        description = ""
    embed = discord.Embed(title=title, color=color, description=description)
    embed.set_footer(text=author.display_name, icon_url=author.avatar_url)

    if image_url is not None:
        embed.set_image(url=image_url)

    for field in fields:
        embed.add_field(name=field[0], value=field[1])
    return embed


async def emoji_selection_detector(ctx: Context, emoji_list: List[Union[discord.Emoji, discord.PartialEmoji, str]],
                                   embed: discord.Embed = None, wait_for: int = 30, *, message_content: str = None,
                                   show_reject: bool = True) -> Union[None, discord.Emoji, discord.PartialEmoji, str]:
    """
    It sends a message with a list of emojis, and waits for the user to react with one of the emojis
    
    :param ctx: The context object
    :type ctx: Context
    :param emoji_list: A list of emojis that you want to use
    :type emoji_list: List[Union[discord.Emoji, discord.PartialEmoji, str]]
    :param embed: The embed object to be sent
    :type embed: discord.Embed
    :param wait_for: The amount of time to wait for a reaction, defaults to 30
    :type wait_for: int (optional)
    :param message_content: The message content to send
    :type message_content: str
    :param show_reject: If True, the ❌ emoji will be added to the message. If False, it won't be added,
    defaults to True
    :type show_reject: bool (optional)
    :return: The emoji that was selected.
    """
    def reaction_check(reaction, user_obj):
        """
        If the author of the message is the same as the user object and the reaction emoji is in the
        emoji list or the emoji is ❌, return True. Otherwise, return False
        
        :param reaction: The reaction object
        :param user_obj: The user object of the person who reacted
        :return: A boolean value.
        """
        if ctx.author.id == user_obj.id and reaction.emoji in [*emoji_list, '❌']:
            return True
        return False

    message = await ctx.send(content=message_content, embed=embed)
    await asyncio.gather(*[asyncio.create_task(message.add_reaction(emote)) for emote in emoji_list])
    if show_reject:
        await message.add_reaction('❌')
    try:
        reaction_used, user = await ctx.bot.wait_for('reaction_add', check=reaction_check, timeout=wait_for)
        await message.delete()
        if show_reject and reaction_used.emoji == '❌':
            return None
        if reaction_used.emoji in emoji_list:
            return reaction_used.emoji
    except asyncio.TimeoutError:
        return None


async def text_response_waiter(ctx: Context, message_monitor: discord.Message, wait_for: int = 30) -> discord.Message:
    """
    It waits for a reply to a message, and returns the reply
    
    :param ctx: Context - The context of the command
    :type ctx: Context
    :param message_monitor: The message that the bot will wait for a reply to
    :type message_monitor: discord.Message
    :param wait_for: The amount of time to wait for a response, defaults to 30
    :type wait_for: int (optional)
    :return: The message that was sent in response to the question
    """
    def response_check(message: discord.Message):
        if message.reference is None:
            return False
        if message.reference.message_id == message_monitor.id:
            return True
        return False
    full_wait_tume = wait_for
    portions = full_wait_tume
    range_ = list(range(1, 8))
    range_.reverse()
    for x in range_:
        if full_wait_tume % x == 0:
            portions = full_wait_tume / x
            break

    m = await ctx.send(f"Will wait for {full_wait_tume} seconds for a response! "
                       f"Please reply to the message asking the question!")
    while True:
        try:
            message_used = await ctx.bot.wait_for('message', check=response_check, timeout=portions)
            await m.edit(content="Reply Received!!")
            return message_used
        except asyncio.TimeoutError:
            full_wait_tume -= portions
            if full_wait_tume != 0:
                await m.edit(content=f"Will wait for {full_wait_tume} seconds for a response! "
                                     f"Please reply to the message asking the question!")
            else:
                await m.edit(content="I was left alone :( I wil now ignore any reply to the message")
                return None

