#!/usr/bin/env python3
"""Offline tests for the Garuda bot's owner-only /botstats — plain
asserts, no network, no Telegram. Mirrors the DO bot's test shape.

Run: python3 test_botstats.py
Covers: usage_counts against a seeded DB; the /botstats card (users
seen, active groups, AI questions today, Wallet Security watches
registered, last successful sweep); owner gating (non-owner and
no-owner-configured both get silence); and the registration guards
(botstats stays out of the public command list, Wallet Security
handlers + jobs are wired).
"""
import asyncio, os, sys, tempfile, types

_tmp = tempfile.mkdtemp(prefix="garuda-botstats-test-")
os.environ["DB_PATH"] = os.path.join(_tmp, "messages.db")
os.environ["OWNER_TELEGRAM_ID"] = "606060"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Stub httpx + telegram so bot.py imports without the Railway-only deps
# (same trick as test_garuda.py).
_httpx = types.ModuleType("httpx")


class _AsyncClient:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def get(self, *a, **k): raise RuntimeError("network stubbed in tests")
    async def post(self, *a, **k): raise RuntimeError("network stubbed in tests")


_httpx.AsyncClient = _AsyncClient
sys.modules.setdefault("httpx", _httpx)

_tg = types.ModuleType("telegram")


class _Any:
    def __init__(self, *a, **k): self.kwargs = k
    def __call__(self, *a, **k): return _Any()


for _n in ("Update", "InlineKeyboardButton", "InlineKeyboardMarkup", "ChatPermissions"):
    setattr(_tg, _n, _Any)
sys.modules.setdefault("telegram", _tg)
_const = types.ModuleType("telegram.constants")


class _PM:
    MARKDOWN = "Markdown"
    HTML = "HTML"


_const.ParseMode = _PM
sys.modules.setdefault("telegram.constants", _const)
_ext = types.ModuleType("telegram.ext")
for _n in ("Application", "CommandHandler", "MessageHandler", "CallbackQueryHandler", "filters"):
    setattr(_ext, _n, _Any)


class _ContextTypes:
    DEFAULT_TYPE = object()


_ext.ContextTypes = _ContextTypes
sys.modules.setdefault("telegram.ext", _ext)

import store
import ratelimit
import bot

passed = 0


def check(cond, label):
    global passed
    assert cond, f"FAILED: {label}"
    passed += 1
    print(f"  ok: {label}")


print("== seed usage + wallet security state ==")
store.log_message(-1001, 11, "Ann", "hello", 1)
store.log_message(-1001, 12, "Bob", "hi all", 2)
store.log_message(-1002, 13, "Cid", "yo", 3)
store.set_setting(555, "gov_alerts", "on")
WALLET = "terra1kur3cr4vask4lgs3tr4gww7lr0zvc944gjfcqc"
store.wallet_watch_add(42, WALLET, 1_800_000_000)
store.ws_meta_set("last_sweep_ok_ts", "1800000000")
ratelimit.reset()
check(ratelimit.allowed_for_rank(11, -1001, owner_id=606060, rank=2), "AI call 1 allowed")
check(ratelimit.allowed_for_rank(12, -1001, owner_id=606060, rank=2), "AI call 2 allowed")
check(ratelimit.questions_today() == 2, "AI questions today counts allowed calls")

print("== /botstats handler ==")


class _Msg:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class _User:
    def __init__(self, uid): self.id = uid


class _Chat:
    type = "private"


class _Update:
    def __init__(self, uid):
        self.effective_user = _User(uid)
        self.effective_message = _Msg()
        self.message = self.effective_message
        self.effective_chat = _Chat()


class _Ctx:
    args = []


check(bot.OWNER_ID == 606060, "owner id picked up from env")
upd = _Update(606060)
asyncio.run(bot.on_botstats(upd, _Ctx()))
check(len(upd.effective_message.replies) == 1, "owner gets the /botstats card")
_txt = upd.effective_message.replies[0]
check("Users seen: 4" in _txt, "card shows users seen (3 group talkers + 1 DM user)")
check("Active groups I'm in and logging: 2" in _txt, "card shows active groups")
check("AI questions today (UTC): 2" in _txt, "card shows AI questions today")
check("Wallet Security watches registered: 1" in _txt, "card shows the watch count (counts only)")
check("Wallet Security last successful sweep: 2027-01-15 08:00 UTC" in _txt,
      "card shows the last successful Wallet Security sweep time")
check(WALLET not in _txt, "card NEVER shows a watched wallet address")

upd = _Update(606061)
asyncio.run(bot.on_botstats(upd, _Ctx()))
check(upd.effective_message.replies == [], "non-owner gets silence")

_saved = bot.OWNER_ID
try:
    bot.OWNER_ID = 0
    upd = _Update(606060)
    asyncio.run(bot.on_botstats(upd, _Ctx()))
    check(upd.effective_message.replies == [], "no owner configured = silence for everyone")
finally:
    bot.OWNER_ID = _saved

print("== Wallet Security handlers: group use redirects to DM ==")
upd = _Update(42)
upd.effective_chat = type("G", (), {"type": "supergroup"})()
asyncio.run(bot.on_watch(upd, _Ctx()))
check(len(upd.message.replies) == 1 and "DM me to set up Wallet Security" in upd.message.replies[0],
      "/watch in a group redirects to DM and registers nothing")
check(store.wallet_watches_for_user(42) != [] and
      all(w["address"] != WALLET for w in store.wallet_watches_for_user(606061)),
      "group /watch created no watch for anyone else")

print("== registration guards ==")
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")).read()
check('CommandHandler("botstats", on_botstats)' in _src, "botstats handler is registered")
_cmds = _src.split("set_my_commands([", 1)[1].split("])", 1)[0]
check("botstats" not in _cmds, "botstats is NOT in the public command list")
check("botstats" not in bot.HELP, "botstats is NOT in /help")
for cmd in ("security", "watch", "watching", "unwatch"):
    check(f'CommandHandler("{cmd}",' in _src, f"/{cmd} handler is registered")
check("job_wallet_security" in _src and "SWEEP_INTERVAL_SECONDS" in _src,
      "the ~15-minute Wallet Security sweep job is wired")
check("job_wallet_watchdog" in _src, "the missed-sweep watchdog job is wired")
check("post_shutdown" in _src, "the graceful-shutdown downtime notice is wired")
check("Wallet Security" in bot.HELP and "/watch" in bot.HELP, "HELP documents Wallet Security")

print(f"\nALL {passed} CHECKS PASSED")
