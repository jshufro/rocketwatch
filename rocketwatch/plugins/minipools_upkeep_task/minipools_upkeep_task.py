import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import pymongo
from discord.ext import commands, tasks
from discord.ext.commands import hybrid_command
from motor.motor_asyncio import AsyncIOMotorClient
from multicall import Call, constants

# enable multiprocessing
from utils.embeds import Embed, el_explorer_url
from utils.readable import s_hex
from utils.shared_w3 import w3
from utils.visibility import is_hidden

constants.NUM_PROCESSES = 4
from utils.cfg import cfg
from utils.reporter import report_error
from utils.rocketpool import rp
from utils.time_debug import timerun

log = logging.getLogger("minipools_upkeep_task")
log.setLevel(cfg["log_level"])


class MinipoolsUpkeepTask(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = AsyncIOMotorClient(cfg["mongodb_uri"]).get_database("rocketwatch")
        self.sync_db = pymongo.MongoClient(cfg["mongodb_uri"]).get_database("rocketwatch")
        self.event_loop = None

        if not self.run_loop.is_running() and bot.is_ready():
            self.run_loop.start()

    @commands.Cog.listener()
    async def on_ready(self):
        if self.run_loop.is_running():
            return
        self.run_loop.start()

    @timerun
    def get_minipools_from_db(self):
        # get all minipools from db
        m = self.sync_db.minipools.find({}).distinct("address")
        return m

    @timerun
    def get_minipool_stats(self, minipools):
        m_d = rp.get_contract_by_name("rocketMinipoolDelegate")
        m = rp.assemble_contract("rocketMinipool", address=minipools[0])
        function_pairs = [
            (rp.seth_sig(m_d.abi, "getNodeFee"), "getNodeFee"),
            (rp.seth_sig(m.abi, "getDelegate"), "getDelegate"),
            (rp.seth_sig(m.abi, "getPreviousDelegate"), "getPreviousDelegate"),
            (rp.seth_sig(m.abi, "getUseLatestDelegate"), "getUseLatestDelegate"),
        ]
        minipool_stats = {}
        batch_size = 2500
        for i in range(0, len(minipools), batch_size):
            i_end = min(i + batch_size, len(minipools))
            log.debug(f"getting minipool stats for {i}-{i_end}")
            addresses = minipools[i:i_end]
            calls = [
                Call(a, seth_sig, [((a, func_name), None)])
                for a in addresses
                for seth_sig, func_name in function_pairs
            ]
            res = rp.multicall2_do_call(calls)
            # add data to mini pool stats dict (address => {func_name: value})
            # strip get from function name
            for (address, func_name), value in res.items():
                if address not in minipool_stats:
                    minipool_stats[address] = {}
                if func_name.startswith("get"):
                    func_name = func_name[3:]
                minipool_stats[address][func_name] = value
        return minipool_stats

    # every 15 minutes
    @tasks.loop(seconds=60 * 15)
    async def run_loop(self):
        executor = ThreadPoolExecutor()
        loop = asyncio.get_event_loop()
        futures = [loop.run_in_executor(executor, self.upkeep_minipools)]
        try:
            await asyncio.gather(*futures)
        except Exception as err:
            await report_error(err)

    def upkeep_minipools(self):
        logging.info("Updating minipool states")
        # the bellow fixes multicall from breaking
        if not self.event_loop:
            self.event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.event_loop)
        a = self.get_minipools_from_db()
        b = self.get_minipool_stats(a)
        # update data in db using unordered bulk write
        # note: this data is kept in the "meta" field of each minipool
        bulk = [
            pymongo.UpdateOne(
                {"address": address},
                {"$set": {"meta": stats}},
                upsert=True
            ) for address, stats in b.items()
        ]

        self.sync_db.minipools.bulk_write(bulk, ordered=False)
        logging.info("Updated minipool states")

    @hybrid_command()
    async def delegate_stats(self, ctx):
        await ctx.defer(ephemeral=is_hidden(ctx))
        # get stats about delegates
        # we want to show the distribution of minipools that are using each delegate
        distribution_stats = await self.db.minipools.aggregate([
            {"$match": {"meta.Delegate": {"$exists": True}}},
            {"$group": {"_id": "$meta.Delegate", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]).to_list(None)
        # and the percentage of minipools that are using the useLatestDelegate flag
        use_latest_delegate_stats = await self.db.minipools.aggregate([
            {"$match": {"meta.UseLatestDelegate": {"$exists": True}}},
            {"$group": {"_id": "$meta.UseLatestDelegate", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]).to_list(None)
        e = Embed()
        e.title = "Delegate Stats"
        desc = "**Delegate Distribution of Minipools:**\n"
        c_sum = sum(d['count'] for d in distribution_stats)
        s = "\u00A0" * 4
        # latest delegate acording to rp
        rp.uncached_get_address_by_name("rocketMinipoolDelegate")
        for d in distribution_stats:
            # I HATE THE CHECKSUMMED ADDRESS REQUIREMENTS I HATE THEM SO MUCH
            a = w3.toChecksumAddress(d['_id'])
            name = s_hex(a)
            if a == rp.get_address_by_name("rocketMinipoolDelegate"):
                name += " (Latest)"
            desc += f"{s}{el_explorer_url(a, name)}: {d['count']} ({d['count'] / c_sum * 100:.2f}%)\n"
        desc += "\n"
        desc += "**Minipools configured to always use latest delegate:**\n"
        c_sum = sum(d['count'] for d in use_latest_delegate_stats)
        for d in use_latest_delegate_stats:
            # true = yes, false = no
            d['_id'] = "Yes" if d['_id'] else "No"
            desc += f"{s}**{d['_id']}**: {d['count']} ({d['count'] / c_sum * 100:.2f}%)\n"
        e.description = desc
        await ctx.send(embed=e)


async def setup(self):
    await self.add_cog(MinipoolsUpkeepTask(self))
