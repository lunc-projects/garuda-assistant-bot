"""Tests for the Garuda fork: garuda.py data commands (mocked LCD),
the knowledge base, address provenance against the garuda-watch
sources, and the Garuda-only / no-games guarantees in bot.py.
Run: python3 test_garuda.py"""
import asyncio
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")

# --- Stub httpx + telegram so bot.py can be imported without the
# Railway-only dependencies (same trick as the LUNC bot's tests) ---
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

import garuda
import kb

fails = []
def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond: fails.append(name)

# --- Address provenance: every constant must appear in the watch sources ---
WATCH = os.path.expanduser("~/workspace/garuda-watch")
ADDRS = {
    "GOV_CONTRACT": garuda.GOV_CONTRACT,
    "DEX_PAIR_FACTORY": garuda.DEX_PAIR_FACTORY,
    "DEX_ROUTER": garuda.DEX_ROUTER,
    "CROSS_STAKING_FACTORY": garuda.CROSS_STAKING_FACTORY,
    "NFT_STAKING_FACTORY": garuda.NFT_STAKING_FACTORY,
    "REGULAR_STAKING_FACTORY": garuda.REGULAR_STAKING_FACTORY,
    "FARMING_FACTORY": garuda.FARMING_FACTORY,
}
if os.path.isdir(WATCH):
    corpus = ""
    for f in ("check.py", "check_staking.py", "check_regular.py", "check_platform.py", "watched_set.py"):
        corpus += open(os.path.join(WATCH, f)).read()
    for name, addr in ADDRS.items():
        check(f"{name} appears in garuda-watch sources", addr in corpus)
    plat = json.load(open(os.path.join(WATCH, "baseline_platform.json")))
    check("KNOWN_FARM_COUNT matches baseline_platform farms",
          garuda.KNOWN_FARM_COUNT == len(plat["farms"]))
    stk = json.load(open(os.path.join(WATCH, "baseline_staking.json")))
    check("cross factory expected code = baseline 11750",
          garuda.EXPECTED[garuda.CROSS_STAKING_FACTORY]["code_id"] == stk["staking_factory"]["code_id"] == "11750")
    check("NFT factory expected code = baseline 11451",
          garuda.EXPECTED[garuda.NFT_STAKING_FACTORY]["code_id"] == stk["nft_factory"]["code_id"] == "11451")
    check("cross staking_code_id expectation noted (11751)",
          "11751" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "garuda.py")).read())
    reg = json.load(open(os.path.join(WATCH, "baseline_regular.json")))
    check("regular factory expected code = baseline 10921",
          garuda.EXPECTED[garuda.REGULAR_STAKING_FACTORY]["code_id"] == reg["factory"]["code_id"] == "10921")
    dex = json.load(open(os.path.join(WATCH, "baseline.json")))
    check("DEX factory expected code = baseline 11411",
          garuda.EXPECTED[garuda.DEX_PAIR_FACTORY]["code_id"] == dex["factory"]["code_id"] == "11411")
    check("KNOWN_PAIR_COUNT matches baseline pairs",
          garuda.KNOWN_PAIR_COUNT == len(dex["pairs"]))
else:
    print("SKIP provenance checks (garuda-watch dir not present)")

# --- Mocked LCD: data-command builders ---
INFO = {
    garuda.REGULAR_STAKING_FACTORY: {"code_id": "10921", "admin": garuda.GOV_CONTRACT},
    garuda.CROSS_STAKING_FACTORY: {"code_id": "11750", "admin": garuda.GOV_CONTRACT},
    garuda.NFT_STAKING_FACTORY: {"code_id": "11451", "admin": garuda.GOV_CONTRACT},
    garuda.DEX_PAIR_FACTORY: {"code_id": "11411", "admin": garuda.GOV_CONTRACT},
    garuda.GOV_CONTRACT: {"code_id": "11543", "admin": "terra1u5jfafg63d8wprcujcqpu0nmdlasehd4kqrf82"},
    garuda.DEX_ROUTER: {"code_id": "9822", "admin": "terra1jh69dnxuypyaekz5azvkvt5265updxlsk8wnyy"},
    garuda.FARMING_FACTORY: {"code_id": "10899", "admin": garuda.GOV_CONTRACT},
}
async def fake_info(addr):
    return INFO[addr]
async def fake_smart(addr, msg):
    if addr == garuda.REGULAR_STAKING_FACTORY and "registered_token" in msg:
        return {"tokens": [{"token_address": "terra1tokAAA", "staking_address": "terra1poolAAA"},
                           {"token_address": "terra1tokBBB", "staking_address": "terra1poolBBB"}]}
    if addr == garuda.CROSS_STAKING_FACTORY and "registered_token" in msg:
        off = msg["registered_token"].get("offset", 0)
        return {"staking_addresses": ["terra1cross1", "terra1cross2"] if off == 0 else []}
    if addr == garuda.CROSS_STAKING_FACTORY and "config" in msg:
        return {"staking_code_id": 11751}
    if addr == garuda.DEX_PAIR_FACTORY and "pairs" in msg:
        return {"pairs": [{"x": 1}, {"y": 2}, {"z": 3}]}
    if "token_info" in msg:
        return {"symbol": "TKN", "decimals": 6, "name": "Token", "total_supply": "1000"}
    return {}
garuda.contract_info = fake_info
garuda.smart = fake_smart

staking = asyncio.run(garuda.staking_text())
check("/staking shows regular pool count", "2 pools registered" in staking)
check("/staking shows cross count + repaired codes", "2 staking contracts registered" in staking and "11750" in staking and "11751" in staking)
check("/staking carries finder links", garuda.finder(garuda.REGULAR_STAKING_FACTORY) in staking)

dex = asyncio.run(garuda.dex_text())
check("/dex shows live pair count", "trading pairs registered: 3" in dex)
check("/dex carries router finder link", garuda.finder(garuda.DEX_ROUTER) in dex)

farms = asyncio.run(garuda.farms_text())
check("/farms shows the known farm count, labeled as the watch set",
      str(garuda.KNOWN_FARM_COUNT) in farms and "security watch" in farms)

status = asyncio.run(garuda.status_text())
check("/status all-clear when chain matches baseline", "Everything matches the baseline" in status)
check("/status labels itself a live check", "live check" in status.lower())

# Tamper one code id -> the verdict must flip for that row only.
INFO[garuda.CROSS_STAKING_FACTORY] = {"code_id": "99999", "admin": garuda.GOV_CONTRACT}
status2 = asyncio.run(garuda.status_text())
check("/status flags a changed code id", "CHANGED" in status2 and "differs from the baseline" in status2)
INFO[garuda.CROSS_STAKING_FACTORY] = {"code_id": "11750", "admin": garuda.GOV_CONTRACT}

# --- Knowledge base ---
check("KB answers 'what is garuda'", kb.find_kb_answer("what is garuda defi?") is not None)
inc = kb.find_kb_answer("was garuda hacked in october?")
check("KB incident answer exists", inc is not None)
check("incident states verified figures", inc and "59.1M" in inc and "1,084" in inc and "35" in inc)
check("incident clears the team, names nobody", inc and "did not hack itself" in inc and "no culprit" in inc)
check("KB staking answer separates regular vs cross", "NOT affected" in (kb.find_kb_answer("tell me about staking") or ""))
check("KB unknown question -> None", kb.find_kb_answer("what is the price of bitcoin") is None)
check("kb_as_text covers every entry", all(k in kb.kb_as_text() for k in kb.KB))
check("KB contains no unverified LUNC-bot references", "luncscan" not in kb.kb_as_text().lower())

# --- bot.py: Garuda-only + no games (Steve's rules) ---
bot_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")).read()
for banned in ("freegames", "send_game", "InlineQueryResultGame", "WebAppInfo",
               "LUNC Assistant", "luncscan", "LUNCDash", "on_games", "on_validators",
               "burnalerts", "watchvalidator", "InlineQueryHandler"):
    check(f"bot.py has no '{banned}'", banned not in bot_src)
for needed in ("Garuda Assistant Bot", "on_staking", "on_farms", "garuda.staking_text"):
    check(f"bot.py has '{needed}'", needed in bot_src)
check("bot.py has no /status handler wiring",
      "on_status" not in bot_src and 'CommandHandler("status"' not in bot_src)
check("bot.py uses the no-security descriptions",
      "live DEX, staking and farms data." in bot_src
      and '("status","Garuda security status (live check)")' not in bot_src)

import bot
check("HELP lists the Garuda data commands",
      all(c in bot.HELP for c in ("/dex", "/staking", "/farms")))
check("HELP has no /status command", "/status" not in bot.HELP)
check("HELP has no dropped commands",
      all(c not in bot.HELP for c in ("/validators", "/burn", "/freegames", "/calc")))
check("ASK_SYSTEM carries the KB", "knowledge base" in bot.ASK_SYSTEM and "Garuda" in bot.ASK_SYSTEM)

# --- Owner issue alerts: transient blips need 3 strikes in an hour,
# real errors still page immediately (2026-10-26) ---
class _NetErr(Exception): pass
_NetErr.__module__ = "telegram.error"
_NetErr.__name__ = "NetworkError"

class _FakeBot:
    def __init__(self): self.sent = []
    async def send_message(self, chat_id, text): self.sent.append(text)

async def _alert_flow():
    fb = _FakeBot()
    bot.OWNER_ID = 424242
    bot.ALERTS = bot.alerts_mod.AlertThrottler()
    bot.TRANSIENT = bot.alerts_mod.TransientGate()
    err = _NetErr("httpx.ReadError: ")
    await bot._alert_owner(fb, "a background job or handler", err)
    await bot._alert_owner(fb, "a background job or handler", err)
    after_two = len(fb.sent)
    await bot._alert_owner(fb, "a background job or handler", err)
    after_three = len(fb.sent)
    third_text = fb.sent[-1] if fb.sent else ""
    await bot._alert_owner(fb, "a background job or handler", ValueError("real bug"))
    after_real = len(fb.sent)
    await bot._alert_owner(fb, "a background job or handler", err)
    after_reset_one = len(fb.sent)
    return after_two, after_three, third_text, after_real, after_reset_one

_a2, _a3, _t3, _ar, _ar1 = asyncio.run(_alert_flow())
check("alerts: two transient blips send nothing", _a2 == 0)
check("alerts: 3rd transient blip sends one alert", _a3 == 1)
check("alerts: 3rd-blip alert says it is the 3rd occurrence", "3rd occurrence in an hour" in _t3)
check("alerts: non-network error pages immediately", _ar == 2)
check("alerts: counter reset — one new blip after the alert sends nothing", _ar1 == 2)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
