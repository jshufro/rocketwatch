from discord import ExtensionNotLoaded, ExtensionNotFound, ExtensionAlreadyLoaded
from discord.ext import commands

from utils.slash_permissions import owner_only_slash


class Reloader(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # todo add auto complet
    @owner_only_slash()
    async def load(self, ctx, module: str):
        """Loads a module."""
        try:
            self.bot.load_extension(f"plugins.{module}.{module}")
            await ctx.respond(f"Loaded {module} Plugin!", ephemeral=True)
        except ExtensionAlreadyLoaded:
            await ctx.respond(f"Plugin {module} already loaded!", ephemeral=True)
        except ExtensionNotFound:
            await ctx.respond(f"Plugin {module} not found!", ephemeral=True)

    @owner_only_slash()
    async def unload(self, ctx, module: str):
        """Unloads a module."""
        try:
            self.bot.unload_extension(f"plugins.{module}.{module}")
            await ctx.respond(f"Unloaded {module} Plugin!", ephemeral=True)
        except ExtensionNotLoaded:
            await ctx.respond(f"Plugin {module} not loaded!", ephemeral=True)

    @owner_only_slash()
    async def reload(self, ctx, module: str):
        """Reloads a module."""
        try:
            self.bot.reload_extension(f"plugins.{module}.{module}")
            await ctx.respond(f"Reloaded {module} Plugin!", ephemeral=True)
        except ExtensionNotLoaded:
            await ctx.respond(f"Plugin {module} not loaded!", ephemeral=True)


def setup(bot):
    bot.add_cog(Reloader(bot))
