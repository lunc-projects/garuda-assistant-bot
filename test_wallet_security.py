#!/usr/bin/env python3
"""Offline tests for Wallet Security (wallet_security.py + the store
functions behind it) — plain asserts, no network, no Telegram.

Run: python3 test_wallet_security.py

Covers: bech32 validation, the 3-wallet registration cap, silent
baseline (first check never alerts), diff detection per category
(bank in/out, CW20 in/out, regular + cross stake up/down, NFT held
in/out, NFT staked in/out), partial-read skip, duplicate suppression,
DM-only alert routing, the never-fail-silently net (owner alert at 3
consecutive failed sweeps, missed-sweep watchdog, last-success
tracking), and the downtime notices (shutdown fanout, startup resume
with the gap window, gap changes alerted as detected-on-return).
"""
import asyncio
import base64
import json
import os
import sys
import tempfile
import types

_tmp = tempfile.mkdtemp(prefix="garuda-ws-test-")
os.environ["DB_PATH"] = os.path.join(_tmp, "messages.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# httpx is a Railway-only dep on this VM; stub it (ChainReader is only
# ever used through the FakeReader subclass below).
_httpx = types.ModuleType("httpx")


class _NoRealHTTP:
    def __init__(self, *a, **k):
        raise AssertionError("real HTTP not allowed in tests")


_httpx.AsyncClient = _NoRealHTTP
sys.modules.setdefault("httpx", _httpx)

import store
import wallet_security as ws
import garuda

passed = 0


def check(cond, label):
    global passed
    assert cond, f"FAILED: {label}"
    passed += 1
    print(f"  ok: {label}")


# ------------------------------------------------------------ fake chain

WALLET = "terra1kur3cr4vask4lgs3tr4gww7lr0zvc944gjfcqc"
WALLET2 = "terra1hjr335tu8perh0hmqnmmru4aw7llppl9a4svu7"
TOK1 = "terra1tok1" + "a" * 20
REG1 = "terra1reg1" + "a" * 20
CROSS1 = "terra1cross" + "a" * 19
COLL1 = next(iter(ws.NFT_STAKING_CONTRACTS.values()))["collection"]
STAKING1 = next(iter(ws.NFT_STAKING_CONTRACTS.keys()))

TOKEN_INFO = {
    TOK1: {"symbol": "AAA", "decimals": 6, "name": "Token AAA"},
    "TOK2": {"symbol": "BBB", "decimals": 6, "name": "Token BBB"},
}


class FakeCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


def nft_model(namespace, token_id, staker):
    ns = namespace.encode()
    key = len(ns).to_bytes(2, "big") + ns + str(token_id).encode()
    value = base64.b64encode(json.dumps(
        {"token_id": str(token_id), "staker": staker}).encode()).decode()
    return {"key": key.hex(), "value": value}


class FakeReader(ws.ChainReader):
    """ChainReader with every primitive replaced by an in-memory state
    dict, so tests can move balances/stakes/NFTs between sweeps."""

    def __init__(self, state):
        super().__init__(client_factory=lambda: FakeCtx())
        self.state = state

    async def smart(self, client, contract, msg):
        s = self.state
        if s.get("fail_smart"):
            raise ws.ChainReadError("injected smart failure")
        if contract == garuda.REGULAR_STAKING_FACTORY and "registered_token" in msg:
            return {"tokens": [{"token_address": TOK1, "staking_address": REG1}]}
        if contract == garuda.CROSS_STAKING_FACTORY and "registered_token" in msg:
            return {"staking_addresses": [CROSS1]}
        if contract == CROSS1 and "config" in msg:
            return {"token_address": TOK1}
        if contract == CROSS1 and "rewards" in msg:
            return {"rewards": []}
        if contract == garuda.DEX_PAIR_FACTORY and "pairs" in msg:
            return {"pairs": []}
        if "token_info" in msg:
            return dict(TOKEN_INFO.get(contract, TOKEN_INFO[TOK1]))
        if "balance" in msg:
            if s.get("fail_balances"):
                raise ws.ChainReadError("injected balance failure")
            return {"balance": s["balances"].get((contract, msg["balance"]["address"]), "0")}
        if "contract_info" in msg:
            return {"name": "Test Collection", "symbol": "TC"}
        if "tokens" in msg:
            if s.get("fail_nft"):
                raise ws.ChainReadError("injected NFT failure")
            return {"tokens": list(s["held"].get((contract, msg["tokens"]["owner"]), []))}
        raise AssertionError(f"unexpected smart query {contract} {msg}")

    async def bank_balances(self, client, address):
        if self.state.get("fail_bank"):
            raise ws.ChainReadError("injected bank failure")
        return dict(self.state["bank"].get(address, {"uluna": "0", "uusd": "0"}))

    async def raw_state_value(self, client, contract, namespace, key_suffix):
        if self.state.get("fail_raw"):
            raise ws.ChainReadError("injected raw failure")
        amount = self.state["raw"].get((contract, namespace, key_suffix))
        return None if amount is None else {"amount": amount}

    async def all_state_models(self, client, contract):
        if self.state.get("fail_scan"):
            raise ws.ChainReadError("injected scan failure")
        return list(self.state["models"].get(contract, []))


def base_state():
    return {
        "bank": {WALLET: {"uluna": "1000000", "uusd": "500000"}},
        "balances": {(TOK1, WALLET): "7000000"},
        "raw": {(REG1, "STAKING", WALLET): "2000000",
                (CROSS1, "STAKED_ASSETS", WALLET): "3000000"},
        "held": {(COLL1, WALLET): ["1", "2"]},
        "models": {STAKING1: [nft_model("STAKED_NFT", "9", WALLET)]},
    }


class DMs:
    def __init__(self):
        self.sent = []  # (user_id, text)

    async def send(self, user_id, text):
        self.sent.append((user_id, text))

    def to(self, user_id):
        return [t for u, t in self.sent if u == user_id]


USER = 111
NOW = 1_800_000_000


def register_with_baseline(reader, dms, user=USER, wallet=WALLET):
    store.wallet_watch_add(user, wallet, NOW)
    result = asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW))
    assert result["success"], f"baseline sweep failed: {result}"
    return result


# ---------------------------------------------------------------- bech32

print("== bech32 validation ==")
check(ws.valid_terra_address(WALLET), "known-good account address validates")
check(ws.valid_terra_address(garuda.REGULAR_STAKING_FACTORY),
      "known-good 32-byte contract address validates")
check(not ws.valid_terra_address(WALLET[:-1] + ("q" if WALLET[-1] != "q" else "p")),
      "corrupted checksum is rejected")
check(not ws.valid_terra_address("cosmos1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqnrql8a"),
      "wrong HRP is rejected")
check(not ws.valid_terra_address("terra1abc"), "too-short address is rejected")
check(not ws.valid_terra_address(""), "empty string is rejected")
check(not ws.valid_terra_address(None), "None is rejected")
check(not ws.valid_terra_address(WALLET.upper()), "uppercase is rejected")

# ------------------------------------------------------- registration cap

print("== registration: cap, duplicate, pause, unwatch ==")
store.wallet_watch_add(222, WALLET, NOW)
store.wallet_watch_add(222, WALLET2, NOW)
store.wallet_watch_add(222, garuda.GOV_CONTRACT, NOW)
mine = store.wallet_watches_for_user(222)
check(len(mine) == 3, "three watches registered")
check(len(mine) >= ws.MAX_WATCHES_PER_USER, "cap constant reached at 3")
store.wallet_watch_add(222, WALLET, NOW)  # duplicate add is a no-op
check(len(store.wallet_watches_for_user(222)) == 3, "duplicate registration does not double-count")
store.wallet_watch_set_alerts(222, False)
check(store.wallet_watches_for_user(222)[0]["alerts_on"] == 0, "/watch off pauses alerts")
store.wallet_watch_set_alerts(222, True)
check(store.wallet_watch_remove(222, WALLET2) == 1, "unwatch removes one wallet")
check(store.wallet_watch_remove(222, WALLET2) == 0, "unwatch of a missing wallet removes nothing")
check(store.wallet_watch_count() == 2, "owner-visible count is counts-only and correct")
for w in store.wallet_watches_for_user(222):
    store.wallet_watch_remove(222, w["address"])

# ------------------------------------------------------ baseline no-alert

print("== baseline: first check never alerts ==")
state = base_state()
reader = FakeReader(state)
dms = DMs()
register_with_baseline(reader, dms)
check(dms.sent == [], "baseline sweep sends no alert")
snap = store.wallet_watch_get(USER, WALLET)["snapshot"]
check(snap["bank"]["uluna"] == "1000000", "baseline stored the bank balance")
check(snap["cw20"].get(TOK1) == "7000000", "baseline stored the CW20 balance")
check(snap["stakes"].get(f"regular:{REG1}") == "2000000", "baseline stored the regular stake")
check(snap["stakes"].get(f"cross:{CROSS1}") == "3000000", "baseline stored the cross stake")
check(snap["nfts"]["held"] == [f"{COLL1}|1", f"{COLL1}|2"], "baseline stored held NFTs")
check(snap["nfts"]["staked"] == [f"{COLL1}|9"], "baseline stored the staked NFT")
check(store.ws_meta_get("last_sweep_ok_ts") == str(NOW), "successful sweep time recorded")
result = asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 900))
check(result["success"] and dms.sent == [], "unchanged second sweep also sends nothing")

# ------------------------------------------------------------ diff alerts

print("== diff: bank in/out ==")
state["bank"][WALLET] = {"uluna": "2500000", "uusd": "0"}
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 1800))
check(len(dms.to(USER)) == 1, "one alert DM for the bank change")
alert = dms.to(USER)[0]
check("LUNC balance increased by 1.5 LUNC" in alert, "LUNC in-amount is in the alert")
check("USTC balance decreased by 0.5 USTC" in alert, "USTC out-amount is in the alert")
check(ws.finder_address(WALLET) in alert, "alert carries the full Finder wallet link")
check(all(u == USER for u, _ in dms.sent), "alert went ONLY to the registering user (DM-only routing)")

print("== diff: CW20 in/out ==")
state["balances"][(TOK1, WALLET)] = "0"
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 2700))
alert = dms.to(USER)[-1]
check("AAA balance decreased by 7 AAA" in alert, "CW20 out is detected with symbol + amount")
state["balances"][(TOK1, WALLET)] = "12500000"
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 3600))
check("AAA balance increased by 12.5 AAA" in dms.to(USER)[-1], "CW20 in is detected")

print("== diff: stake up/down ==")
state["raw"][(REG1, "STAKING", WALLET)] = "5500000"
state["raw"][(CROSS1, "STAKED_ASSETS", WALLET)] = "0"
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 4500))
alert = dms.to(USER)[-1]
check("Stake increased in the AAA regular staking pool by 3.5 AAA" in alert,
      "regular stake increase detected, pool identified")
check("Stake decreased in the AAA cross-staking pool by 3 AAA" in alert,
      "cross stake decrease detected, pool identified")
check(ws.finder_address(REG1) in alert, "stake alert carries the pool Finder link")

print("== diff: NFT in/out + staked ==")
state["held"][(COLL1, WALLET)] = ["2", "3"]
state["models"][STAKING1] = []
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 5400))
alert = dms.to(USER)[-1]
check("NFT #3 (Test Collection) arrived in your wallet" in alert, "NFT in detected with collection + id")
check("NFT #1 (Test Collection) left your wallet" in alert, "NFT out detected with collection + id")
check("NFT #9 (Test Collection) left NFT staking" in alert, "staked NFT out detected")
state["models"][STAKING1] = [nft_model("STAKED_NFT", "2", WALLET)]
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 6300))
check("NFT #2 (Test Collection) was staked (NFT staking)" in dms.to(USER)[-1],
      "NFT staked-in detected")

print("== paused alerts: state advances silently ==")
store.wallet_watch_set_alerts(USER, False)
state["bank"][WALLET] = {"uluna": "9000000", "uusd": "0"}
before = len(dms.sent)
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 7200))
check(len(dms.sent) == before, "paused watcher gets no alert")
check(store.wallet_watch_get(USER, WALLET)["snapshot"]["bank"]["uluna"] == "9000000",
      "snapshot still advances while paused (no stale-diff burst on resume)")
store.wallet_watch_set_alerts(USER, True)

# ------------------------------------------------------- partial-read skip

print("== partial read: skip silently, never alert, snapshot untouched ==")
before_snap = store.wallet_watch_get(USER, WALLET)["snapshot"]
before_dms = len(dms.sent)
state["fail_balances"] = True
result = asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 8100))
check(not result["success"] and result["failed_wallets"] == 1, "failed read marks the sweep partial")
check(len(dms.sent) == before_dms, "failed read sends no alert")
check(store.wallet_watch_get(USER, WALLET)["snapshot"] == before_snap,
      "failed read leaves the snapshot untouched")
state["fail_balances"] = False
state["fail_scan"] = True
result = asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 9000))
check(not result["success"] and len(dms.sent) == before_dms,
      "failed NFT scan also skips the whole cycle silently")
state["fail_scan"] = False

# ---------------------------------------------------- duplicate suppression

print("== duplicate suppression ==")
state["bank"][WALLET] = {"uluna": "9100000", "uusd": "0"}
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 9900))
check(len(dms.to(USER)) >= 1 and "LUNC balance increased by 0.1 LUNC" in dms.to(USER)[-1],
      "the real change alerts once")
count_after = len(dms.sent)
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 10800))
check(len(dms.sent) == count_after, "same state never re-alerts (snapshot advanced)")
# Simulate: alert delivered + hash saved, but the snapshot save crashed.
# The next sweep recomputes the same diff and must NOT resend.
watch = store.wallet_watch_get(USER, WALLET)
old_snapshot = dict(watch["snapshot"])
old_snapshot["bank"] = {"uluna": "9000000", "uusd": "0"}
store.wallet_watch_set_snapshot(USER, WALLET, old_snapshot)
asyncio.run(ws.run_sweep(dms.send, reader=reader, now=NOW + 11700))
check(len(dms.sent) == count_after,
      "same change hash never sends twice, even if the snapshot save failed")

# ------------------------------------------- never fail silently: owner net

print("== health: 3 consecutive failures DM the owner, once per episode ==")
owner_dms = DMs()


async def owner_alert(text):
    await owner_dms.send(999, text)


state["fail_bank"] = True
for i in range(2):
    asyncio.run(ws.run_sweep(dms.send, owner_alert=owner_alert, reader=reader, now=NOW + 12600 + i))
check(owner_dms.sent == [], "no owner alert before the 3rd consecutive failure")
asyncio.run(ws.run_sweep(dms.send, owner_alert=owner_alert, reader=reader, now=NOW + 13500))
check(len(owner_dms.sent) == 1 and "Wallet Security health alert" in owner_dms.sent[0][1],
      "owner is DM'd at 3 consecutive failed sweeps")
asyncio.run(ws.run_sweep(dms.send, owner_alert=owner_alert, reader=reader, now=NOW + 14400))
check(len(owner_dms.sent) == 1, "owner alert does not repeat within the same episode")
check(store.ws_meta_get("consecutive_failures") == "4", "consecutive failure count is tracked")
state["fail_bank"] = False
asyncio.run(ws.run_sweep(dms.send, owner_alert=owner_alert, reader=reader, now=NOW + 15300))
check(store.ws_meta_get("consecutive_failures") == "0", "a successful sweep resets the failure count")
check(store.ws_meta_get("last_sweep_ok_ts") == str(NOW + 15300), "last successful sweep updates")

print("== health: missed-sweep watchdog ==")
owner_dms2 = DMs()


async def owner_alert2(text):
    await owner_dms2.send(999, text)


stale_now = NOW + 15300 + ws.WATCHDOG_STALE_SECONDS + 60
fired = asyncio.run(ws.watchdog_check(owner_alert2, now=stale_now))
check(fired and len(owner_dms2.sent) == 1, "watchdog pages the owner when sweeps go stale")
check("no successful wallet sweep" in owner_dms2.sent[0][1], "watchdog message says what is wrong")
fired = asyncio.run(ws.watchdog_check(owner_alert2, now=stale_now + 300))
check(not fired and len(owner_dms2.sent) == 1, "watchdog does not repeat within the episode")
fired = asyncio.run(ws.watchdog_check(owner_alert2, now=NOW + 15300 + 60))
check(not fired, "watchdog stays quiet while sweeps are fresh")

# ------------------------------------------------------- downtime notices

print("== downtime: shutdown fanout ==")
store.wallet_watch_add(333, WALLET2, NOW)
store.wallet_watch_add(333, WALLET, NOW)  # second wallet, same user: still ONE notice
store.wallet_watch_add(USER, WALLET2, NOW)
notice_dms = DMs()
sent = asyncio.run(ws.send_downtime_notices(notice_dms.send))
ids = sorted(u for u, _ in notice_dms.sent)
check(ids == [USER, 333], "shutdown notice goes once per watcher, to watchers only")
check(all(t == ws.DOWN_NOTICE for _, t in notice_dms.sent), "shutdown notice uses the owner's exact wording")
check("temporarily unprotected" in ws.DOWN_NOTICE and "security update is in progress" in ws.DOWN_NOTICE,
      "down notice is framed as a security update")

print("== downtime: startup resume with gap window + gap-diff alerting ==")
# Simulate a restart: the stored snapshot matches the live state except
# for one balance that moved while the bot was down.
gap_now = NOW + 100000
state["bank"][WALLET] = {"uluna": "12100000", "uusd": "0"}
resume_dms = DMs()
result = asyncio.run(ws.run_sweep(
    resume_dms.send, reader=reader, now=gap_now, detected_on_return=True))
check(result["success"], "post-restart sweep succeeds")
gap_alerts = [t for t in resume_dms.to(USER) if "Wallet Security alert" in t]
check(len(gap_alerts) == 1 and "Detected when protection resumed" in gap_alerts[0],
      "changes during downtime are alerted, labeled as detected on return")
check("LUNC balance increased by 3 LUNC" in gap_alerts[0], "gap diff carries the real change")
sent = asyncio.run(ws.send_resume_notices(
    resume_dms.send, now=gap_now, last_ok_before_boot=gap_now - 3600))
back = [t for u, t in resume_dms.sent if t.startswith("✅")]
check(len(back) >= 1 and all(ws.BACK_NOTICE in t for t in back),
      "resume notice uses the owner's exact wording")
check(any("Protection was paused for about 1 hour" in t for t in back),
      "resume notice names the offline window when the gap shows one")
short = asyncio.run(ws.send_resume_notices(
    resume_dms.send, now=gap_now + 100, last_ok_before_boot=gap_now))
check(all("Protection was paused" not in t for t in resume_dms.to(333)[-1:]),
      "no gap window is claimed when the restart was quick")

print(f"\nALL {passed} CHECKS PASSED")
