import asyncio
from typing import Union

from discord import Color, Member, Embed
from discord.ext.commands import Context



def generate_embed(title: str, author: Member, *, description: str, color: Union[Color, int]) -> Embed:
    return Embed(
        title=title,
        color=color,
        description=description
    ).set_footer(text=author.display_name, icon_url=author.avatar_url)


async def numeric_emoji_selector(ctx: Context, count: int, wait_for: int = 30, *, message_content: str = None,
                                 embed: Embed = None, show_reject: bool = True) -> Union[None, int]:

    def reaction_check(reaction, user_obj):
        if ctx.author.id == user_obj.id and reaction.emoji in [*NUMERIC_EMOTES[:count], '✕']:
            return True

    m = await ctx.send(content=message_content, embed=embed)
    await asyncio.gather(m.add_reaction(NUMERIC_EMOTES[x] for x in range(count)))
    if show_reject:
        await m.add_reaction('❌')
    try:
        reaction_used, user = await ctx.bot.wait_for('reaction_add', check=reaction_check, timeout=wait_for)
        await m.delete()
    except asyncio.TimeoutError:
        return None
    for x in range(count):
        if reaction_used.emoji == NUMERIC_EMOTES[x]:
            return x
    return None
