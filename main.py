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
    def cog_unload(self):
        self.updater.cancel()

    # loop method
    @tasks.loop(seconds=cfg.get_refresh_timer())
    async def updater(self):
        for server in session.query(Server).all():
            if validate_server(server):
                queue_channel = bot.get_channel(server.text_channel)
                for queue_item in session.query(Queue).filter_by(server_id=server.id).all():
                    if queue_item.timeout_start is not None and queue_item.timeout_start + timedelta(minutes=5) < datetime.now():
                        session.delete(queue_item)
                        session.commit()
                await update_message(server.id, queue_channel)


# Returns if a message is owned by the bot
def own_messages(msg):
    return msg.author == bot.user


# Returns the time difference between a stamp and now
def check_time_difference(timestamp: datetime) -> timedelta:
    return datetime.now() - timestamp


# Validates that a server is configured
def validate_server(server: Server):
    return server.id not in (-1, None) and server.text_channel not in (-1, None) and server.voice_channel not in (-1, None)


# Validates that a user is allowed to configure a server
def validate_user(user: Member, server: Server):
    user = session.query(Member).filter_by(id=user.id).first()
    server = session.query(Server).filter_by(id=server.id).first()
    related = session.query(Related).filter_by(server_id=server.id).all()
    permitted = []
    for item in related:
        if item.admin:
            permitted.append(item.member_id)
    if user.superuser:
        return True
    else:
        if user.id in permitted:
            return True
    return False


# Converts a timedelta of only seconds to hours, minutes and seconds
def convert_seconds(delta: timedelta):
    mins, secs = divmod(delta.seconds, 60)
    hrs, mins = divmod(mins, 60)
    days, hrs = divmod(hrs, 24)
    return days, hrs, mins, secs


# Compiles the queue printout
def compile_queue(sid: int):
    queued = session.query(Queue).filter_by(server_id=sid).all()
    if len(queued) == 0:

        message = f"```Queue is currently empty.\n\n```"
    else:
        message = f"```Current queue:\n\n"
        iterator = 0
        timeout_list = []
        for item in queued:
            if item.timeout_start is None:
                iterator += 1
                message += f"    {str(iterator) + ')':<5}" + stringify_queue(item, timeout=False)
            else:
                timeout_list.append(stringify_queue(item, timeout=True))
        if iterator == 0:
            message = f"```Queue is currently empty."
        if len(timeout_list) > 0:
            message = message + "\n\nUsers on queue timeout:\n\n"
            for string in timeout_list:
                message = message + string
        message = message + "```"
    return message


# Stringifies a queue item
def stringify_queue(queue_item: Queue, timeout: bool):
    nickname = session.query(Related).filter_by(member_id=queue_item.member_id,
                                                server_id=queue_item.server_id).first().nick
    if timeout:
        calc_secs = (queue_item.timeout_start + timedelta(minutes=5)) - datetime.now()
        vals = convert_seconds(calc_secs)
        line = f"         {nickname:<25} {vals[2]}m {vals[3]}s remaining\n"
    else:
        calc_secs = check_time_difference(queue_item.join_time)
        vals = convert_seconds(calc_secs)
        line = f"{nickname:<25} {vals[1]}h {vals[2]}m {vals[3]}s\n"
    return line


# Adds a queue item, or resets it if it was timing out
def add_queue(member: Member, server_id):
    queue = session.query(Queue).filter_by(member_id=member.id, server_id=server_id).first()
    member = session.query(Member).filter_by(id=member.id).first()
    if queue is not None:
        if queue.timeout_start is not None:
            queue.timeout_start = None
            session.commit()
            logger.info(f"{member.ref} was removed from queue timeout.")
    else:
        queue = Queue(join_time=datetime.now(), member_id=member.id, server_id=server_id)
        session.add(queue)
        session.commit()
        logger.info(f"{member.ref} was added to queue.")


# Removes a queue item
def remove_queue(member: Member, server_id):
    queue = session.query(Queue).filter_by(member_id=member.id, server_id=server_id).first()
    member = session.query(Member).filter_by(id=member.id).first()
    server = session.query(Server).filter_by(id=server_id).first()
    # User must be in queue for more than 5 minutes to allow a timeout countdown.
    if check_time_difference(queue.join_time).seconds > server.timeout_wait:
        queue.timeout_start = datetime.now()
        session.commit()
        logger.info(f"{member.ref} was added to queue timeout.")
    else:
        if queue.timeout_start is None or check_time_difference(queue.timeout_start).seconds > server.timeout_duration:
            member = session.query(Member).filter_by(id=member.id).first()
            related = session.query(Related).filter_by(member_id=member.id, server_id=server_id).first()
            time_diff = check_time_difference(queue.join_time) - timedelta(seconds=server.timeout_duration)
            if time_diff.days >= 0:
                related.queue_count = related.queue_count + 1
                related.queue_time = related.queue_time + time_diff
                session.commit()
        session.delete(queue)
        session.commit()
        queue_time = convert_seconds(check_time_difference(queue.join_time))
        logger.info(f"{member.ref} was removed from the queue after {queue_time[0]}d {queue_time[1]}h {queue_time[2]}m {queue_time[3]}s.")


# Updates a member and their nickname for a certain server
def update_member(member: discord.member, server: Server):
    if session.query(Member).filter_by(id=member.id).first() is None:
        new_member = Member(id=member.id, ref=member.name + '#' + member.discriminator)
        # nick = Nickname(nick=member.display_name, member_id=new_member.id, server_id=1)
        session.add(new_member)
        logger.info(f"{new_member.ref} added as member to {server.id}")
    # Update nickname
    nickname = session.query(Related).filter_by(member_id=member.id, server_id=server.id).first()
    if nickname is not None:
        nickname.nick = member.display_name
    else:
        nickname = Related(server_id=server.id, member_id=member.id, nick=member.display_name)
        session.add(nickname)
    session.commit()


# Updates the queue message
async def update_message(server_id, queue_channel):
    channel_history = await queue_channel.history(limit=1).flatten()
    if len(channel_history) > 0:
        last_msg = channel_history[0]
    else:
        last_msg = None
    if own_messages(last_msg):
        await last_msg.edit(content=compile_queue(server_id))
    else:
        await queue_channel.purge(limit=100, check=own_messages)
        await queue_channel.send(compile_queue(server_id))


async def check_voicechannel(server):
    if validate_server(server):
        queue_channel = bot.get_channel(server.text_channel)
        await queue_channel.purge(limit=100, check=own_messages)
        voice_queue = bot.get_channel(server.voice_channel)
        members = [bot.get_user(key) for key in voice_queue.voice_states]
        for queued_user in session.query(Queue).filter_by(server_id=server.id).all():
            if queued_user.member_id in [member.id for member in members]:
                update_member(queued_user.member_id, server)
                add_queue(queued_user.member_id, server.id)
                members.remove(queued_user.member_id)
            elif queued_user.member_id not in members:
                remove_queue(queued_user.member_id, server.id)
                members.remove(queued_user.member_id)
        for member in members:
            update_member(member.id, server)
            add_queue(member.id, server.id)
        await update_message(server.id, queue_channel)


# Command to initialise a server
@bot.command()
async def init_server(ctx):
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
async def set_channel(ctx, group: str, chid: int):
    if validate_user(session.query(Member).filter_by(id=ctx.author.id).first(), session.query(Server).filter_by(id=ctx.guild.id).first()):
        if group not in ("queue", "output", "bot", "admin"):
            await ctx.send(f"Incorrect channel type")
        else:
            await config_channel(ctx, group, chid)


async def config_channel(ctx, group: str, chid: int):
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
async def queue_info(ctx, name=None):
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
async def full_queue_info(ctx):
    server = session.query(Server).filter_by(id=ctx.guild.id).first()
    author = session.query(Member).filter_by(id=ctx.author.id).first()
    related = session.query(Related).filter_by(server_id=server.id).all()
    printout = f"```User queue records:\n\n"
    if validate_user(author, server) and ctx.message.channel.id == server.admin_channel:
        for item in related:
            queue_total = convert_seconds(item.queue_time)
            printout = printout + f"{item.nick}: {item.queue_count} times queued, " \
                                  f"{queue_total[0]}d {queue_total[1]}h {queue_total[2]}m {queue_total[3]}s\n"
            if len(printout) > 1500:
                printout = printout + "```"
                await ctx.send(printout)
                printout = "```"
        printout = printout + "```"
        await ctx.send(printout)


@bot.command()
async def reset_queue_info(ctx):
    server = session.query(Server).filter_by(id=ctx.guild.id).first()
    author = session.query(Member).filter_by(id=ctx.author.id).first()
    related = session.query(Related).filter_by(server_id=server.id).all()
    if validate_user(author, server) and ctx.message.channel.id == server.admin_channel:
        for item in related:
            item.queue_count = 0
            item.queue_time = 0
            session.commit()
        logger.warn(f"{ctx.author.id} reset all queue details for {server.id}")
        await ctx.send("All user queue details reset.")


@bot.command()
async def add_admin(ctx, name=None):
    if name is not None:
        if validate_user(ctx.author, ctx.guild):
            relation = session.query(Related).filter_by(member_id=name[2:-1], server_id=ctx.guild.id)
            if relation is not None:
                relation.admin = True
                session.commit()
                logger.warn(f"{ctx.author.id} added {name[2:-1]} as admin for server {ctx.guild.id}")
                await ctx.send(f"Added {name[2:-1]} as admin for server {ctx.guild.id}")


@bot.command()
async def set_timeout_wait(ctx, duration=None):
    if duration is not None:
        try:
            if validate_user(ctx.author, ctx.guild):
                server = session.query(Server).filter_by(id=ctx.guild.id).first()
                if server is not None:
                    server.timeout_wait = int(duration)
                    session.commit()
                    logger.info(f"{ctx.author.id} set timeout wait time set to {duration}s")
                    await ctx.send(f"Timeout wait time set to {duration}s")
        except Exception:
            pass


@bot.command()
async def set_timeout_duration(ctx, duration=None):
    if duration is not None:
        try:
            if validate_user(ctx.author, ctx.guild):
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
async def on_ready():
    session.commit()
    for server in session.query(Server).all():
        await check_voicechannel(server)
        logger.info(f"Cuebot ready in {server.id}")
    bot.add_cog(UpdateCog(bot))


# Event on a voice state change, indicating a user has joined or left a channel
@bot.event
async def on_voice_state_update(member, before, after):
    server_id = before.channel.guild.id if before.channel is not None else after.channel.guild.id
    server = session.query(Server).filter_by(id=server_id).first()
    if server is not None:
        queue_channel = bot.get_channel(server.text_channel)
        # Update member + nickname
        update_member(member, server)
        # Someone leaves the channel
        if before.channel is not None and before.channel.id == session.query(Server).filter_by(id=before.channel.guild.id).first().voice_channel:
            if after.channel is None or after.channel.id != session.query(Server).filter_by(id=after.channel.guild.id).first().voice_channel:
                remove_queue(member, server_id)
                await update_message(server_id, queue_channel)
        # Someone joins the channel
        elif after.channel is not None:
            if after.channel.id == session.query(Server).filter_by(id=after.channel.guild.id).first().voice_channel:
                add_queue(member, server_id)
                await update_message(server_id, queue_channel)

if cfg.get_token() is not None:
    bot.run(cfg.get_token())
