import asyncio
import logging
import os
import threading
import time as _time
from datetime import datetime, time as dtime, timedelta

from flask import Flask
from telegram import BotCommand, MenuButtonCommands, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import charts, core, fmt
from store import Store

log = logging.getLogger("studybot")
HTML = ParseMode.HTML
ST = core.new_state()
STORE = Store()
LOCK = asyncio.Lock()
CLIENT = None  # telethon userbot
_last_notice = 0.0

COMMANDS = [
    ("today", "Tick your lectures"), ("plan", "Today's detailed plan"), ("pending", "Pending lectures"),
    ("extra", "Bonus lectures (extra)"), ("progress", "Today's progress"), ("countdown", "Days left & syllabus %"),
    ("chart", "Charts: /chart week, /chart maths"), ("week", "Weekly report"),
    ("streak", "Current streak"), ("lockstatus", "Chat lock status"), ("help", "All commands"),
]


async def save():
    try:
        await STORE.save(ST)
    except Exception:
        log.exception("save failed")


async def say(bot, text, **kw):
    if ST.get("owner"):
        try:
            return await bot.send_message(ST["owner"], text, parse_mode=HTML, **kw)
        except Exception:
            log.exception("send failed")


def owner_only(fn):
    async def wrap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if ST.get("owner") is None:
            ST["owner"] = uid
            await save()
        elif uid != ST["owner"]:
            return
        return await fn(update, ctx)
    return wrap


# ---------------- daily flow ----------------
async def send_day(bot):
    now = core.now_ist()
    await say(bot, fmt.plan_text(ST, now))
    await say(bot, fmt.checklist_text(ST), reply_markup=fmt.checklist_kb(ST))


async def new_day(bot, app):
    async with LOCK:
        changed = core.rollover(ST, core.now_ist())
        if changed:
            await save()
    if changed:
        await send_day(bot)
        schedule_lock_jobs(app)


async def midnight_job(ctx: ContextTypes.DEFAULT_TYPE):
    await new_day(ctx.bot, ctx.application)


def schedule_lock_jobs(app):
    jq = app.job_queue
    for n in ("lock_warn", "lock_end"):
        for j in jq.get_jobs_by_name(n):
            j.schedule_removal()
    fu = ST.get("free_until")
    if not fu or core.is_complete(ST):
        return
    fu, now = core.parse(fu), core.now_ist()
    if fu - timedelta(minutes=2) > now:
        jq.run_once(warn_job, when=fu - timedelta(minutes=2), name="lock_warn")
    if fu > now:
        jq.run_once(end_job, when=fu, name="lock_end")


async def warn_job(ctx):
    await say(ctx.bot, fmt.sb("⏳ 2 minutes of free chatting left."))


async def end_job(ctx):
    now = core.now_ist()
    if core.locked(ST, now):
        await say(ctx.bot, fmt.lock_text(ST, now))


# ---------------- commands ----------------
@owner_only
async def cmd_start(update, ctx):
    async with LOCK:
        started = core.rollover(ST, core.now_ist())
        await save()
    intro = (f"{fmt.hd('👋 Study Bot Ready')}\n\n"
             f"{fmt.sb('i will send your plan every day at 12:00 am. tick lectures only after you finish them.')}\n\n{fmt.HELP}")
    await update.message.reply_text(intro, parse_mode=HTML)
    if ST.get("day"):
        await send_day(ctx.bot)
        schedule_lock_jobs(ctx.application)
    else:
        await update.message.reply_text(
            fmt.sb(f"first plan arrives automatically at 12:00 am on {core.START_DATE.strftime('%d %b %Y')}. nothing else to do."),
            parse_mode=HTML)


async def need_start(update):
    if not ST.get("day"):
        await update.message.reply_text(fmt.sb(f"plan starts at 12:00 am on {core.START_DATE.strftime('%d %b')}."), parse_mode=HTML)
        return True


def preview_now():
    return datetime.combine(core.START_DATE, dtime(0, 5), core.IST)


PREVIEW_NOTE = fmt.sb("preview · real tasks start at 12:00 am on 01 nov") + "\n\n"


@owner_only
async def cmd_today(update, ctx):
    if not ST.get("day"):
        now = preview_now()
        await update.message.reply_text(
            PREVIEW_NOTE.replace("real tasks start", "tick buttons arrive") + fmt.plan_text(core.preview_state(now), now), parse_mode=HTML)
        return
    await update.message.reply_text(fmt.checklist_text(ST), parse_mode=HTML, reply_markup=fmt.checklist_kb(ST))


def simple(render, preview=False):
    """render(state, now) -> html. With preview=True, shows a Day-1 preview until the bot has started."""
    @owner_only
    async def h(update, ctx):
        if preview and not ST.get("day"):
            now = preview_now()
            st, note = core.preview_state(now), PREVIEW_NOTE
        else:
            now, st, note = core.now_ist(), ST, ""
        await update.message.reply_text(note + render(st, now), parse_mode=HTML)
    return h


async def cmd_help(update, ctx):
    if update.effective_user.id == ST.get("owner") or ST.get("owner") is None:
        await update.message.reply_text(fmt.HELP, parse_mode=HTML)


async def cmd_chart(update, ctx):
    if update.effective_user.id != ST.get("owner"):
        return
    subj, last = None, None
    for a in (x.lower() for x in ctx.args):
        for c, n, _ in core.SUBJECTS:
            if a in (n.lower(), c.lower()):
                subj = c
        if a == "week":
            last = 7
        if a == "month":
            last = 30
    buf = await asyncio.to_thread(charts.make_chart, ST, subj, last)
    if buf is None:
        await update.message.reply_text(fmt.sb("charts appear after day 1 begins (12:00 am on 01 nov)."), parse_mode=HTML)
        return
    await update.message.reply_photo(buf, caption=fmt.sb("green candle = day complete · red = fell short"), parse_mode=HTML)


# ---------------- extra ----------------
@owner_only
async def cmd_extra(update, ctx):
    if await need_start(update):
        return
    if not core.is_complete(ST):
        await update.message.reply_text(fmt.sb("finish today's task first. extra lectures unlock after that."), parse_mode=HTML)
        return
    if not any(core.next_fresh(ST, c) for c, _, _ in core.SUBJECTS):
        await update.message.reply_text(fmt.sb("no extra lectures left."), parse_mode=HTML)
        return
    await update.message.reply_text(fmt.extra_text(ST), parse_mode=HTML, reply_markup=fmt.extra_kb(ST))


async def on_extra(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ST.get("owner"):
        await q.answer()
        return
    lid = q.data.split(":", 1)[1]
    ch = None
    async with LOCK:
        res = core.try_extra(ST, lid, core.now_ist())
        if res["ok"]:
            ch = core.chapter_finished(ST, lid)
            await save()
    if not res["ok"]:
        why = res["why"]
        if why == "too_soon":
            await q.answer(fmt.reject_text(res), show_alert=True)
        elif why == "plan_first":
            await q.answer("Finish today's task first.", show_alert=True)
        else:
            await q.answer("Not available. Use /extra again.", show_alert=True)
        return
    await q.answer("Done ✅")
    try:
        if any(core.next_fresh(ST, c) for c, _, _ in core.SUBJECTS):
            await q.edit_message_text(fmt.extra_text(ST), parse_mode=HTML, reply_markup=fmt.extra_kb(ST))
        else:
            await q.edit_message_text(fmt.sb("no extra lectures left."), parse_mode=HTML)
    except BadRequest:
        pass
    await say(ctx.bot, fmt.extra_done_text(ST, lid))
    if ch:
        await say(ctx.bot, fmt.chapter_text(ST, ch[0], ch[1], core.LEC[lid].subj))


# ---------------- tick ----------------
async def on_tick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ST.get("owner"):
        await q.answer()
        return
    lid = q.data.split(":", 1)[1]
    async with LOCK:
        now = core.now_ist()
        res = core.try_tick(ST, lid, now)
        if res["ok"]:
            ch = core.chapter_finished(ST, lid)
            await save()
    if not res["ok"]:
        why = res["why"]
        if why == "too_soon":
            await q.answer(fmt.reject_text(res), show_alert=True)
        elif why == "already":
            await q.answer("Already ticked ✅")
        else:
            await q.answer("Not in today's plan. Use /today.", show_alert=True)
        return
    await q.answer("Done ✅")
    try:
        await q.edit_message_text(fmt.checklist_text(ST), parse_mode=HTML, reply_markup=fmt.checklist_kb(ST))
    except BadRequest:
        pass
    await say(ctx.bot, fmt.tick_text(ST, now, lid, res))
    if ch:
        await say(ctx.bot, fmt.chapter_text(ST, ch[0], ch[1], core.LEC[lid].subj))
    schedule_lock_jobs(ctx.application)


# ---------------- userbot (group lock) ----------------
async def start_userbot(app):
    global CLIENT
    sid, aid, ah = os.getenv("SESSION"), os.getenv("API_ID"), os.getenv("API_HASH")
    if not (sid and aid and ah):
        log.warning("SESSION / API_ID / API_HASH missing: userbot (chat lock) disabled")
        return
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    CLIENT = TelegramClient(StringSession(sid), int(aid), ah)
    await CLIENT.connect()
    if not await CLIENT.is_user_authorized():
        log.error("SESSION is not authorized: generate a new one with gen_session.py")
        return
    me = await CLIENT.get_me()
    if ST.get("owner") != me.id:
        ST["owner"] = me.id
        await save()

    @CLIENT.on(events.NewMessage(outgoing=True))
    async def _out(event):
        global _last_notice
        if not event.is_group:  # DMs, channels and Saved Messages are never touched
            return
        now = core.now_ist()
        if not core.locked(ST, now):
            return
        try:
            await event.delete()
        except Exception:
            log.exception("delete failed")
            return
        if _time.time() - _last_notice > 60:
            _last_notice = _time.time()
            nxt = next((i for i in ST["plan"] if i not in ST["done"]), None)
            extra = f"\n{fmt.sb('next: ' + core.LEC[nxt].short)}" if nxt else ""
            await say(app.bot, f"🚫 {fmt.sb('message deleted. group chat is locked until you tick your next lecture.')}{extra}")

    log.info("userbot connected as %s", me.id)


# ---------------- lifecycle ----------------
async def post_init(app: Application):
    global ST
    ST = await STORE.load()
    if os.getenv("OWNER_ID") and not ST.get("owner"):
        ST["owner"] = int(os.getenv("OWNER_ID"))
    await start_userbot(app)
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])
    await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    app.job_queue.run_daily(midnight_job, time=dtime(0, 0, tzinfo=core.IST), name="midnight")
    await new_day(app.bot, app)  # catch up if the service was down at midnight
    schedule_lock_jobs(app)


async def post_shutdown(app: Application):
    if CLIENT:
        await CLIENT.disconnect()


def run_web():
    web = Flask(__name__)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @web.get("/")
    @web.get("/health")
    def home():
        return "ok"

    web.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(os.environ["BOT_TOKEN"]).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("extra", cmd_extra))
    app.add_handler(CommandHandler("plan", simple(lambda s, n: fmt.plan_text(s, n), preview=True)))
    app.add_handler(CommandHandler("pending", simple(lambda s, n: fmt.pending_text(s))))
    app.add_handler(CommandHandler("progress", simple(lambda s, n: fmt.progress_text(s, n), preview=True)))
    app.add_handler(CommandHandler("countdown", simple(lambda s, n: fmt.countdown_text(s, n), preview=True)))
    app.add_handler(CommandHandler("week", simple(lambda s, n: fmt.week_text(s, n))))
    app.add_handler(CommandHandler("streak", simple(lambda s, n: f"{fmt.hd('🔥 Streak')}\n\n{fmt.sb(f'{core.streak(s)} days in a row')}")))
    app.add_handler(CommandHandler("lockstatus", simple(lambda s, n: fmt.lock_text(s, n))))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("chart", cmd_chart))
    app.add_handler(CallbackQueryHandler(on_tick, pattern=r"^t:"))
    app.add_handler(CallbackQueryHandler(on_extra, pattern=r"^x:"))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
