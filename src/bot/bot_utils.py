import asyncio
from typing import Union, List, Tuple, AnyStr

import discord
from discord.ext.commands import Context


def generate_embed(title: str, author: discord.Member, *fields: Tuple[AnyStr, AnyStr], description: str = None,
                   color: int = 0, image_url: str = None) -> discord.Embed:
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
    def reaction_check(reaction, user_obj):
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


async def text_response_waiter(ctx: Context, message_monitor: discord.Message, wait_for: int = 30):
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

