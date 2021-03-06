import traceback

import discord
from discord import ChannelType
from discord.ext import tasks, commands
from datetime import datetime, timedelta, time
from database import Member, Queue, Server, Related, session
import config

# Configuration
intents = discord.Intents().default()
intents.voice_states = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
cfg = config.Config.get_instance()
logger = config.logger


# Class to contain the bot loop, updating the queue display every few seconds
class UpdateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.updater.start()
        logger.info("Bot loop cog started.")

    # cog loader
    def cog_unload(self) -> None:
        self.updater.cancel()

    # loop method
    @tasks.loop(seconds=cfg.get_refresh_timer())
    async def updater(self) -> None:
        for server in session.query(Server).all():
            if validate_server(server):
                try:
                    await check_voicechannel(server)
                except (TypeError, AttributeError):
                    logger.error(traceback.format_exc())


def __check_member_type(member: (int, Member, discord.Member)) -> Member:
    if member is None:
        raise TypeError
    else:
        if isinstance(member, int):
            return session.query(Member).filter_by(id=member).first()
        elif isinstance(member, discord.Member):
            return session.query(Member).filter_by(id=member.id).first()
        elif isinstance(member, Member):
            return member
        else:
            raise TypeError


# Returns if a message is owned by the bot
def own_messages(msg: discord.Message) -> bool:
    return msg.author == bot.user


# Returns the time difference between a stamp and now
def check_time_difference(timestamp: datetime) -> timedelta:
    return datetime.now() - timestamp


def calc_times(session: time) -> tuple:
    now = datetime.now()
    compiled = datetime(year=now.year, month=now.month, day=now.day,
                        hour=session.hour, minute=session.minute, second=0)
    if compiled <= now:
        compiled_next = compiled + timedelta(days=1)
        compiled_prev = compiled
    else:
        compiled_next = compiled
        compiled_prev = compiled - timedelta(days=1)
    return compiled_next, compiled_prev


def calc_next_time_diff(session: datetime) -> timedelta:
    return session - datetime.now()


def check_time_between(earliest: time, latest: time) -> bool:
    current_datetime = datetime.now()
    current_time = time(hour=current_datetime.hour, minute=current_datetime.minute)
    if earliest > latest:
        if current_time <= latest or current_time >= earliest:
            return True
    else:
        if earliest <= current_time <= latest:
            return True
    return False


def queue_active_status() -> tuple:
    queue_window = timedelta(minutes=30)
    us_start = cfg.get_sre_us_start()
    us_window_start = (datetime.combine(datetime.today(), us_start) - queue_window).time()
    us_end = cfg.get_sre_us_end()
    eu_start = cfg.get_sre_eu_start()
    eu_window_start = (datetime.combine(datetime.today(), eu_start) - queue_window).time()
    eu_end = cfg.get_sre_eu_end()
    # Pre-queue time for US SRE
    if check_time_between(us_window_start, us_start):
        diff = convert_seconds(calc_next_time_diff(calc_times(us_start)[0]))
        return True, f"```Pre-session queue tracking is active for USTZ SRE. Session starts in {diff[1]}h {diff[2] + 1}m\n\n"
    # Active time for US SRE
    if check_time_between(us_start, us_end):
        diff = convert_seconds(calc_next_time_diff(calc_times(us_end)[0]))
        return True, f"```Queue tracking for USTZ SRE is active now. Session ends in {diff[1]}h {diff[2] + 1}m\n\n"
    # Pre-queue time for EU SRE
    if check_time_between(eu_window_start, eu_start):
        diff = convert_seconds(calc_next_time_diff(calc_times(eu_start)[0]))
        return True, f"```Pre-session queue tracking is active for EUTZ SRE. Session starts in {diff[1]}h {diff[2] + 1}m\n\n"
    # Active time for EU SRE
    if check_time_between(eu_start, eu_end):
        diff = convert_seconds(calc_next_time_diff(calc_times(eu_end)[0]))
        return True, f"```Queue tracking for EUTZ SRE is active now. Session ends in {diff[1]}h {diff[2] + 1}m\n\n"
    # Inactive times
    if check_time_between(us_end, eu_window_start):
        diff = convert_seconds(calc_next_time_diff(calc_times(eu_window_start)[0]))
        return False, f"```Queue tracking is currently inactive. EUTZ tracking activates in {diff[1]}h {diff[2] + 1}m\n\n"
    if check_time_between(eu_end, us_window_start):
        diff = convert_seconds(calc_next_time_diff(calc_times(us_window_start)[0]))
        return False, f"```Queue tracking is currently inactive. USTZ tracking activates in {diff[1]}h {diff[2] + 1}m\n\n"
    return False, f"```Queue is currently unavailable.\n\n"


# Validates that a server is configured
def validate_server(server: Server) -> bool:
    return server.id not in (-1, None) and server.text_channel not in (-1, None) and server.voice_channel not in (
    -1, None)


# Validates that a user is allowed to configure a server
def validate_user(member_id: int, server: Server) -> bool:
    member = __check_member_type(member_id)
    server = session.query(Server).filter_by(id=server.id).first()
    related = session.query(Related).filter_by(server_id=server.id).all()
    permitted = []
    for item in related:
        if item.admin:
            permitted.append(item.member_id)
    if member.superuser:
        return True
    else:
        if member.id in permitted:
            return True
    return False


# Converts a timedelta of only seconds to hours, minutes and seconds
def convert_seconds(delta: timedelta) -> tuple:
    mins, secs = divmod(delta.seconds, 60)
    hrs, mins = divmod(mins, 60)
    days, hrs = divmod(hrs, 24)
    return days, hrs, mins, secs


# Compiles the queue printout
def compile_queue(sid: int, start_message: str, active: bool) -> str:
    queued = session.query(Queue).filter_by(server_id=sid).all()
    if active:
        if len(queued) == 0:
            message = start_message + f"Queue is currently empty.\n\n"
        else:
            message = start_message + f"Current queue:\n\n"
            iterator = 0
            timeout_list = []
            for item in queued:
                if item.timeout_start is None:
                    iterator += 1
                    message = message + f"    {str(iterator) + ')':<5}" + stringify_queue(item, timeout=False)
                else:
                    timeout_list.append(stringify_queue(item, timeout=True))
            if iterator == 0:
                message = start_message + f"Queue is currently empty.\n\n"
            if len(timeout_list) > 0:
                message = message + "\n\nUsers on queue timeout:\n\n"
                for string in timeout_list:
                    message = message + string
        return message + "```"
    else:
        return start_message + "```"


# Stringifies a queue item
def stringify_queue(queue_item: Queue, timeout: bool) -> str:
    nickname = session.query(Related).filter_by(member_id=queue_item.member_id,
                                                server_id=queue_item.server_id).first().nick
    if timeout:
        calc_secs = (queue_item.timeout_start + timedelta(seconds=queue_item.server.timeout_duration)) - datetime.now()
        vals = convert_seconds(calc_secs)
        line = f"         {nickname:<25} {vals[2]}m {vals[3]}s remaining\n"
    else:
        calc_secs = check_time_difference(queue_item.join_time)
        vals = convert_seconds(calc_secs)
        line = f"{nickname:<25} {vals[1]}h {vals[2]}m {vals[3]}s\n"
    return line


# Adds a queue item, or resets it if it was timing out
def add_queue(member_id: int, server_id) -> None:
    member = __check_member_type(member_id)
    queue = session.query(Queue).filter_by(member_id=member.id, server_id=server_id).first()
    if queue is not None:
        if queue.timeout_start is not None:
            queue.timeout_start = None
            session.commit()
            logger.info(f"{member.ref} was removed from queue timeout and added back into the queue.")
    else:
        queue = Queue(join_time=datetime.now(), member_id=member.id, server_id=server_id)
        session.add(queue)
        session.commit()
        logger.info(f"{member.ref} was added to queue.")


# Removes a queue item
def remove_queue(member_id: int, server_id: int, timeout: bool = True) -> None:
    member = __check_member_type(member_id)
    queue = session.query(Queue).filter_by(member_id=member.id, server_id=server_id).first()
    server = session.query(Server).filter_by(id=server_id).first()
    # If the user is already on timeout
    if queue.timeout_start is not None:
        timeout_diff = check_time_difference(queue.timeout_start)
        queue_duration = check_time_difference(queue.join_time) - timedelta(seconds=server.timeout_wait)
        # Handle valid timeouts, users will be removed from queue and have their data iterated
        if (timeout_diff.total_seconds() > server.timeout_duration and queue_duration.days >= 0) or timeout is False:
            related = session.query(Related).filter_by(member_id=member.id, server_id=server_id).first()
            related.queue_count = related.queue_count + 1
            related.queue_time = related.queue_time + queue_duration
            session.delete(queue)
            session.commit()
            queue_time = convert_seconds(queue_duration)
            logger.info(f"{member.ref} was removed from the queue after {queue_time[0]}d "
                        f"{queue_time[1]}h {queue_time[2]}m {queue_time[3]}s, with their records iterated.")
        # Handle invalid timeouts, users will be removed from queue but not iterated
        elif timeout_diff.total_seconds() < 0 or queue_duration.days < 0:
            session.delete(queue)
            session.commit()
            logger.warning(f"{member.ref} was removed from the queue with invalid timeout duration or wait duration.")
    # The user is not on timeout
    else:
        # User must be in queue for more than 5 minutes to allow a timeout countdown
        if check_time_difference(queue.join_time).seconds > server.timeout_wait:
            if timeout:
                queue.timeout_start = datetime.now()
                session.commit()
                logger.info(f"{member.ref} was added to queue timeout.")
            else:
                related = session.query(Related).filter_by(member_id=member.id, server_id=server_id).first()
                related.queue_count = related.queue_count + 1
                related.queue_time = related.queue_time + check_time_difference(queue.join_time)
                session.delete(queue)
                session.commit()
                queue_time = convert_seconds(check_time_difference(queue.join_time))
                logger.info(f"{member.ref} was removed from the queue after {queue_time[0]}d "
                            f"{queue_time[1]}h {queue_time[2]}m {queue_time[3]}s, with their records iterated.")
        else:
            session.delete(queue)
            session.commit()
            queue_time = convert_seconds(check_time_difference(queue.join_time))
            logger.info(f"{member.ref} was removed from the queue after "
                        f"{queue_time[0]}d {queue_time[1]}h {queue_time[2]}m {queue_time[3]}s.")


# Updates a member and their nickname for a certain server
def update_member(member_id: int, server: Server) -> None:
    member = __check_member_type(member_id)
    guild = bot.get_guild(server.id)
    guild_member = guild.get_member(member_id)
    if member is None:
        new_member = Member(id=guild_member.id, ref=guild_member.name + '#' + guild_member.discriminator)
        # nick = Nickname(nick=member.display_name, member_id=new_member.id, server_id=1)
        session.add(new_member)
        logger.info(f"{new_member.ref} added as member to {server.id}")
    # Update nickname
    nickname = session.query(Related).filter_by(member_id=member_id, server_id=server.id).first()
    if nickname is not None:
        nickname.nick = guild_member.display_name
    else:
        nickname = Related(server_id=server.id, member_id=guild_member.id, nick=guild_member.display_name)
        session.add(nickname)
    session.commit()


# Updates the queue message
async def update_message(server_id: int, queue_channel: discord.TextChannel, message: tuple) -> None:
    channel_history = await queue_channel.history(limit=50).flatten()
    if len(channel_history) > 0:
        last_msg = channel_history[0]
    else:
        last_msg = None
    if own_messages(last_msg):
        await last_msg.edit(content=compile_queue(server_id, message[1], message[0]))
    else:
        await queue_channel.purge(limit=100, check=own_messages)
        await queue_channel.send(compile_queue(server_id, message[1], message[0]))


async def check_voicechannel(server: Server) -> None:
    if validate_server(server):
        queue_channel = bot.get_channel(server.text_channel)
        voice_queue = bot.get_channel(server.voice_channel)
        members = [key for key in voice_queue.voice_states]
        message = queue_active_status()
        # If we're tracking users...
        if message[0]:
            for queued_user in session.query(Queue).filter_by(server_id=server.id).all():
                # Members who were previously in queue and still are
                if queued_user.member_id in members:
                    update_member(queued_user.member_id, server)
                    add_queue(queued_user.member_id, server.id)
                    members.remove(queued_user.member_id)
                # Members who were in queue but now are not
                elif queued_user.member_id not in members:
                    remove_queue(queued_user.member_id, server.id)
            # Members who were not previously in queue but have joined
            for member in members:
                update_member(member, server)
                add_queue(member, server.id)
        else:
            for queued_user in session.query(Queue).filter_by(server_id=server.id).all():
                remove_queue(queued_user.member_id, server.id, timeout=False)
        await update_message(server.id, queue_channel, message)


# Command to initialise a server
@bot.command()
async def init_server(ctx: commands.Context) -> None:
    server = session.query(Server).filter_by(id=ctx.guild.id).first()
    if server is None:
        server = Server(id=ctx.guild.id)
        session.add(server)
        session.commit()
        await ctx.send(f"Initialising database for server {ctx.guild.id}")
        logger.info(f"Initialised {server.id}")
    else:
        await ctx.send(f"{ctx.guild.id} has already been initialised.")


@bot.command()
async def set_channel(ctx: commands.Context, group: str, chid: int) -> None:
    if validate_user(ctx.author.id,
                     session.query(Server).filter_by(id=ctx.guild.id).first()):
        if group not in ("queue", "output", "bot", "admin"):
            await ctx.send(f"Incorrect channel type")
        else:
            await config_channel(ctx, group, chid)


async def config_channel(ctx: commands.Context, group: str, chid: int) -> None:
    server = session.query(Server).filter_by(id=ctx.guild.id).first()
    if server is None:
        await ctx.send(f"This server has not yet been initialised.")
    else:
        try:
            if bot.get_channel(chid).guild.id == ctx.guild.id:
                chan_type = ChannelType.text if group in ("output", "bot", "admin") else ChannelType.voice
                if bot.get_channel(chid).type == chan_type:
                    if group == "output":
                        server.text_channel = chid
                    elif group == "bot":
                        server.bot_channel = chid
                    elif group == "admin":
                        server.admin_channel = chid
                    elif group == "queue":
                        server.voice_channel = chid
                    session.commit()
                    await ctx.send(f"Server {group} channel set.")
                    logger.info(f"Set {group} channel {chid} for {server.id}.")
                    if validate_server(server):
                        await check_voicechannel(server)
                else:
                    await ctx.send(f"That channel is not the correct type of channel.")
            else:
                await ctx.send(f"That channel ID is not valid for this server.")
        except (commands.errors.CommandInvokeError, AttributeError):
            await ctx.send(f"Invalid command.")


@bot.command()
async def queue_info(ctx: commands.Context, name=None) -> None:
    server = session.query(Server).filter_by(id=ctx.guild.id).first()
    if name is not None:
        member = session.query(Member).filter_by(id=name[2:-1]).first()
        related = session.query(Related).filter_by(member_id=name[2:-1], server_id=server.id).first()
    else:
        member = session.query(Member).filter_by(id=ctx.author.id).first()
        related = session.query(Related).filter_by(member_id=member.id, server_id=server.id).first()
    if ctx.message.channel.id == server.bot_channel:
        if member is None or related is None:
            await ctx.send(f"No data on the requested user has been found.")
        else:
            time_played = convert_seconds(related.queue_time)
            await ctx.send(f"{related.nick} has queued {related.queue_count} times for a total of "
                           f"{time_played[0]}d {time_played[1]}h {time_played[2]}m {time_played[3]}s")


@bot.command()
async def full_queue_info(ctx: commands.Context) -> None:
    server = session.query(Server).filter_by(id=ctx.guild.id).first()
    author = __check_member_type(ctx.author.id)
    related = session.query(Related).filter_by(server_id=server.id).order_by(Related.queue_time).all()
    printout = f"```User queue records:\n\n{'Name':25} {'Queue Count':15} {'Total Queue Time'}\n\n"
    if validate_user(author, server) and ctx.message.channel.id == server.admin_channel:
        for item in related:
            if item.queue_count > 0:
                queue_total = convert_seconds(item.queue_time)
                printout = printout + f"{item.nick:25} {str(item.queue_count):15} " \
                                      f"{queue_total[0]}d {queue_total[1]}h {queue_total[2]}m {queue_total[3]}s\n"
                if len(printout) > 1500:
                    printout = printout + "```"
                    await ctx.send(printout)
                    printout = "```"
        printout = printout + "```"
        await ctx.send(printout)


@bot.command()
async def reset_queue_info(ctx: commands.Context) -> None:
    server = session.query(Server).filter_by(id=ctx.guild.id).first()
    author = __check_member_type(ctx.author.id)
    related = session.query(Related).filter_by(server_id=server.id).all()
    if validate_user(author, server) and ctx.message.channel.id == server.admin_channel:
        for item in related:
            item.queue_count = 0
            item.queue_time = timedelta(seconds=0)
            session.commit()
        logger.warning(f"{ctx.author.id} reset all queue details for {server.id}")
        await ctx.send("All user queue details reset.")


@bot.command()
async def add_admin(ctx: commands.Context, name=None) -> None:
    if name is not None:
        if validate_user(ctx.author.id, ctx.guild):
            relation = session.query(Related).filter_by(member_id=name[2:-1], server_id=ctx.guild.id)
            if relation is not None:
                relation.admin = True
                session.commit()
                logger.warning(f"{ctx.author.id} added {name[2:-1]} as admin for server {ctx.guild.id}")
                await ctx.send(f"Added {name[2:-1]} as admin for server {ctx.guild.id}")


@bot.command()
async def set_timeout_wait(ctx: commands.Context, duration=None) -> None:
    if duration is not None:
        try:
            if validate_user(__check_member_type(ctx.author.id), ctx.guild):
                server = session.query(Server).filter_by(id=ctx.guild.id).first()
                if server is not None:
                    server.timeout_wait = int(duration)
                    session.commit()
                    logger.info(f"{ctx.author.id} set timeout wait time set to {duration}s")
                    await ctx.send(f"Timeout wait time set to {duration}s")
        except Exception:
            pass


@bot.command()
async def set_timeout_duration(ctx: commands.Context, duration=None) -> None:
    if duration is not None:
        try:
            if validate_user(__check_member_type(ctx.author.id), ctx.guild):
                server = session.query(Server).filter_by(id=ctx.guild.id).first()
                if server is not None:
                    server.timeout_duration = int(duration)
                    session.commit()
                    logger.info(f"{ctx.author.id} set timeout duration time set to {duration}s")
                    await ctx.send(f"Timeout duration set to {duration}s")
        except Exception:
            pass


# Event on startup, indicating the bot is ready
@bot.event
async def on_ready() -> None:
    session.commit()
    for server in session.query(Server).all():
        if validate_server(server):
            try:
                await check_voicechannel(server)
            except (TypeError, AttributeError):
                logger.error(traceback.format_exc())
        logger.info(f"Cuebot ready in {server.id}")
    bot.add_cog(UpdateCog(bot))


# Event on a voice state change, indicating a user has joined or left a channel
@bot.event
async def on_voice_state_update(member_id: int, before, after) -> None:
    server_id = before.channel.guild.id if before.channel is not None else after.channel.guild.id
    server = session.query(Server).filter_by(id=server_id).first()
    if server is not None:
        if validate_server(server):
            try:
                await check_voicechannel(server)
            except (TypeError, AttributeError):
                logger.error(traceback.format_exc())



if cfg.get_token() is not None:
    bot.run(cfg.get_token())
