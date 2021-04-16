import asyncio
from typing import Union, List, Tuple, AnyStr

import discord
from discord.ext.commands import Context


def generate_embed(title: str, author: discord.Member, *fields: Tuple[AnyStr, AnyStr], description: str = None,
                   color: int = 0) -> discord.Embed:
    for field in fields:
        assert len(field) == 2
    embed = discord.Embed(title=title, color=color, description=description)
    embed.set_footer(text=author.display_name, icon_url=author.avatar_url)
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
