"""Summary no-mentions + brevity tests (owner rule, 2026-10-28):
summaries must be shorter and must NEVER carry @usernames — Telegram
re-tags those people. Covers strip_mentions() unit cases, the
summarize()/extractive paths, the /summary and /tldr send paths, and
the brevity/no-@ wording of the summary prompt.
Run: python3 test_summary_mentions.py"""
import asyncio
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")

# --- Stub httpx + telegram so bot.py can be imported without the
# Railway-only dependencies (same trick as test_garuda.py) ---
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

import ai_client
import store
import bot

fails = []
def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond: fails.append(name)

S = ai_client.strip_mentions

# --- strip_mentions unit cases ---
check("start-of-line handle stripped", S("@alice said hi") == "alice said hi")
check("mid-sentence handle stripped", S("ask @bob_1984 about it") == "ask bob_1984 about it")
check("multiple handles stripped",
      S("@alice and @carol_dev agreed, cc @dave_2") == "alice and carol_dev agreed, cc dave_2")
check("email untouched", S("mail me at name@example.com please") == "mail me at name@example.com please")
check("handle after opening punctuation stripped", S("(@dave_2) check this") == "(dave_2) check this")
check("handle after newline stripped", S("line one\n@alice again") == "line one\nalice again")
check("two-char @word left alone (not a handle)", S("hi @ab there") == "hi @ab there")
check("empty string safe", S("") == "")
check("plain text unchanged", S("no mentions here") == "no mentions here")

# --- prompt wording: brevity + no-@ rules present, old @name instruction gone ---
check("prompt caps length (~450 chars)", "450 characters" in ai_client.SUMMARY_SYSTEM)
check("prompt caps lines (5 short lines)", "5 short lines" in ai_client.SUMMARY_SYSTEM)
check("prompt bans @usernames", "NEVER write @usernames" in ai_client.SUMMARY_SYSTEM)
check("prompt no longer asks for @name", "@name" not in ai_client.SUMMARY_SYSTEM)

# --- summarize() sanitizes the AI output ---
async def _fake_chat_mentions(messages, temperature=0.3, lang="en"):
    return "⚡ TL;DR — @alice raised fees\n• @bob_1984 agreed with @alice"
_real_chat = ai_client.chat
ai_client.chat = _fake_chat_mentions
try:
    rows = [{"ts": 1, "user_name": "Alice", "text": "fees?"}]
    out = asyncio.run(ai_client.summarize(rows))
finally:
    ai_client.chat = _real_chat
check("summarize() output has no @handle", "@alice" not in out and "@bob_1984" not in out)
check("summarize() output keeps the bare names", "alice raised fees" in out and "bob_1984 agreed" in out)

# --- extractive_summary() sanitizes quoted message text ---
rows = [{"ts": 1, "user_name": "Carol", "text": "ping @carol_dev about the pool"}]
out = ai_client.extractive_summary(rows)
check("extractive output has no @handle", "@carol_dev" not in out)
check("extractive output keeps the bare name", "carol_dev about the pool" in out)

# --- /summary send path passes through the sanitizer ---
CHAT = -100999
store.log_message(CHAT, 7, "Alice", "we should raise fees", 1)
store.log_message(CHAT, 8, "Bob", "agreed", 2)

sent = []
class _Msg:
    async def reply_text(self, text, **k): sent.append(text)
class _Chat: id = CHAT
class _User: id = 42
upd = types.SimpleNamespace(effective_chat=_Chat(), effective_user=_User(), message=_Msg())
ctx = types.SimpleNamespace(args=[])

async def _guard_ok(update): return True
_real_guard = bot.ai_guard
bot.ai_guard = _guard_ok
ai_client.chat = _fake_chat_mentions
try:
    asyncio.run(bot.on_summary(upd, ctx))
finally:
    ai_client.chat = _real_chat
    bot.ai_guard = _real_guard
joined = "\n".join(sent)
check("/summary sent a summary", "TL;DR" in joined)
check("/summary sent text has no @handle", "@alice" not in joined and "@bob_1984" not in joined)
check("/summary sent text keeps bare names", "alice raised fees" in joined)

# --- /tldr send path passes through the sanitizer ---
sent2 = []
class _Msg2:
    reply_to_message = types.SimpleNamespace(text="a very long message " * 40)
    async def reply_text(self, text, **k): sent2.append(text)
upd2 = types.SimpleNamespace(effective_chat=_Chat(), effective_user=_User(), message=_Msg2())

async def _fake_chat_tldr(messages, temperature=0.3, lang="en"):
    return "@alice confirmed the plan and @bob_1984 seconded it"
bot.ai_guard = _guard_ok
ai_client.chat = _fake_chat_tldr
try:
    asyncio.run(bot.on_tldr(upd2, ctx))
finally:
    ai_client.chat = _real_chat
    bot.ai_guard = _real_guard
check("/tldr replied", len(sent2) == 1 and sent2[0].startswith("⚡ TL;DR:"))
check("/tldr sent text has no @handle", "@alice" not in sent2[0] and "@bob_1984" not in sent2[0])
check("/tldr sent text keeps bare names", "alice confirmed the plan" in sent2[0])

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
