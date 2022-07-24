import logging
from datetime import datetime

import aiohttp
from discord.app_commands import Choice, choices
from discord.ext import commands
from discord.ext.commands import Context
from discord.ext.commands import hybrid_command

from utils.cfg import cfg
from utils.embeds import Embed
from utils.visibility import is_hidden

log = logging.getLogger("forum")
log.setLevel(cfg["log_level"])


class Forum(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.domain = "https://dao.rocketpool.net"

    @hybrid_command()
    @choices(period=[
        Choice(name="all time", value="all"),
        Choice(name="yearly", value="yearly"),
        Choice(name="quarterly", value="quarterly"),
        Choice(name="monthly", value="monthly"),
        Choice(name="weekly", value="weekly"),
        Choice(name="daily", value="daily")
    ])
    async def top_forum_posts(self, ctx: Context, period: Choice[str] = "monthly"):
        """
        Get the top posts from the forum.
        """
        await ctx.defer(ephemeral=is_hidden(ctx))
        if isinstance(period, Choice):
            period = period.value

        # retrieve the top posts from the forum for the specified period
        async with aiohttp.ClientSession() as session:
            res = await session.get(f"{self.domain}/top.json?period={period}")
            res = await res.json()

        # create the embed
        e = Embed()
        e.title = f"Top Forum Stats ({period})"
        # top 10 topics
        tmp_desc = "\n".join(
            f"{i + 1}. [{topic['fancy_title']}]({self.domain}/t/{topic['slug']})\n"
            f"Last Reply: <t:{int(datetime.fromisoformat(topic['last_posted_at'].replace('Z', '+00:00')).timestamp())}:R>\n"
            f"`{topic['like_count']}` 🤍\t `{topic['views']}` 👀\t `{topic['posts_count']}` 💬\n"
            for i, topic in enumerate(res["topic_list"]["topics"][:5]))
        e.add_field(name=f"Top {min(5, len(res['topic_list']['topics']))} Posts", value=tmp_desc, inline=False)
        # top 5 users
        tmp_desc = "".join(f"{i + 1}. [{user['name'] or user['username']}]"
                           f"({self.domain}/u/{user['username']})\n"
                           for i, user in enumerate(res["users"][:5]))
        e.add_field(name=f"Top {min(5, len(res['users']))} Users", value=tmp_desc, inline=False)
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(Forum(bot))
