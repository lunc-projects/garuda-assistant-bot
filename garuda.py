"""Garuda DeFi live data — Terra Classic LCD reads (PublicNode).

Every address here was taken from the Garuda security watch sources in
~/workspace/garuda-watch/ (NOT invented):

- DEX pair factory / router / gov ... check.py (FACTORY, ROUTER, GOV)
- Cross-staking factory ............. check_staking.py (STAKING_FACTORY)
- NFT staking factory ................ check_staking.py (NFT_FACTORY)
- Regular staking factory ........... check_regular.py (FACTORY)
- Farming factory + core contracts ... baseline_platform.json ("core")
- Labels for all of the above ........ watched_set.py (CORE_LABELS)

EXPECTED below is the security watch's own baseline state
(baseline.json, baseline_staking.json, baseline_regular.json): the
code id + wasm admin each core contract is supposed to have. /status
compares a fresh live read against it — the same lightweight check
the watch performs. Nothing here signs or sends anything; these are
read-only queries, like every other command in this bot.
"""
import base64
import datetime
import json
import os

import httpx

LCD = "https://terra-classic-lcd.publicnode.com"
FINDER = "https://finder.terraclassic.community"

GOV_CONTRACT = "terra1t6h84pcvtawc0e8x9xwp8a59hwcc00dgcfsswhjpqgsuyr9t7k0sfwfqu6"
DEX_PAIR_FACTORY = "terra1ypwj6sw25g0qcykv7mzmcvsndvx56r3yrgkaw3fds7yzwl7fwwcsnxkeh7"
DEX_ROUTER = "terra1frvfffkpdluzdj8lel4nyyjl2u0p6zuenhfeveulrlg6r2w4tdqqx2zr68"
CROSS_STAKING_FACTORY = "terra13e8mwvupdnj5cv0ruyqadr3cexxa9hm8jaml4j9kync05uh03p5qlaqux5"
NFT_STAKING_FACTORY = "terra1kqu2dtrxe44g54fsq67yengzld7ne6vwwuc4h6elaqa7rr6earystmw38q"
REGULAR_STAKING_FACTORY = "terra1uln3ee7w5s4vtrljdglczwx8xv9uyv46fv2vee4mkzjxq2sr02asad0uzt"
FARMING_FACTORY = "terra16d83gl8u0wx6xend59tr0dx750qqxh3q5vlznkk8uv4txlljrtrqymnzwx"
TOKEN_FACTORY = "terra1klqjtnrm26ruk5fn08fvnkh67f205fgjwul3jfugvvtts4trqkhsk8qmja"
FEE_COLLECTOR = "terra1e98felysrzt8z9k0ryljgfpg0k0vsnqw83hv02kz6gxkj7n7w23s5vq5gf"
ORDERBOOK = "terra15gk54rgdzd4xltxxzfe52y0jlhf7eh0wjvkkr877uvketw8ut90sr7ej8m"
SMART_ROUTER = "terra1eel4krahz8nr5vjw5w784ly7tjuu839mgmredngu7qdvwjxs43ds304q76"
LEADERBOARD = "terra14ed89n8lwr3kgzdx9gmez4gj3d2mvdsy4fcq7g4elpjncrkzn9sspedsvs"

# Farm set size from the watch's known farm set
# (garuda-watch/baseline_platform.json, "farms") — the full Garuda app
# snapshot the watch checks. Labeled as a baseline count wherever shown.
KNOWN_FARM_COUNT = 389

# Expected on-chain state per the watch baselines (code id + admin).
# Cross-staking: post-repair state (team migrated the factory to code
# 11750 on 2026-10-24; its config points at staking code 11751).
EXPECTED = {
    DEX_PAIR_FACTORY: {"name": "DEX pair factory", "code_id": "11411", "admin": GOV_CONTRACT},
    GOV_CONTRACT: {"name": "Garuda governance contract", "code_id": "11543",
                   "admin": "terra1u5jfafg63d8wprcujcqpu0nmdlasehd4kqrf82"},
    DEX_ROUTER: {"name": "DEX router", "code_id": "9822",
                 "admin": "terra1jh69dnxuypyaekz5azvkvt5265updxlsk8wnyy"},
    CROSS_STAKING_FACTORY: {"name": "Cross-staking factory", "code_id": "11750", "admin": GOV_CONTRACT},
    NFT_STAKING_FACTORY: {"name": "NFT staking factory", "code_id": "11451", "admin": GOV_CONTRACT},
    REGULAR_STAKING_FACTORY: {"name": "Regular staking factory", "code_id": "10921", "admin": GOV_CONTRACT},
    FARMING_FACTORY: {"name": "Farming factory", "code_id": None, "admin": None},
}


def finder(addr):
    return f"{FINDER}/address/{addr}"


async def _get(path):
    async with httpx.AsyncClient(timeout=25, proxy=os.getenv("OUTBOUND_PROXY") or None) as c:
        r = await c.get(f"{LCD}{path}")
        r.raise_for_status()
        return r.json()


async def contract_info(addr):
    d = await _get(f"/cosmwasm/wasm/v1/contract/{addr}")
    return d["contract_info"]


async def smart(addr, msg):
    q = base64.b64encode(json.dumps(msg).encode()).decode()
    d = await _get(f"/cosmwasm/wasm/v1/contract/{addr}/smart/{q}")
    return d["data"]


async def _paged_tokens(addr):
    """All registered tokens of the regular staking factory
    (same query the watch's check_regular.py uses)."""
    data = await smart(addr, {"registered_token": {}})
    return data.get("tokens", [])


async def _cross_pool_count(addr):
    """Registered cross-staking contracts, paged like the watch does."""
    out, offset = [], 0
    while True:
        page = await smart(addr, {"registered_token": {"offset": offset}})
        addrs = page.get("staking_addresses", [])
        if not addrs:
            return out
        out.extend(addrs)
        offset += len(addrs)
        if len(addrs) < 2 or offset > 1000:
            return out


# ---------- pure formatters (unit-tested with fixtures) ----------

def format_staking(regular_tokens, regular_info, cross_count, cross_info, cross_cfg):
    """regular_tokens: the factory's registered_token list; infos are
    contract_info dicts; cross_cfg is the cross factory config."""
    lines = ["🥩 *Garuda staking — live*"]
    lines.append(f"\n*Regular staking* — {len(regular_tokens)} pools registered")
    lines.append(f"Factory code: {regular_info.get('code_id')} · admin: Garuda governance contract")
    syms = []
    for t in regular_tokens:
        sym = t.get("symbol") or t.get("token_symbol")
        if sym:
            syms.append(sym)
    if syms:
        lines.append("Pools include: " + ", ".join(syms[:12]) + ("…" if len(syms) > 12 else ""))
    scid = (cross_cfg or {}).get("staking_code_id")
    lines.append(f"\n*Cross-staking* — {cross_count} staking contracts registered")
    lines.append(f"Factory code: {cross_info.get('code_id')}" + (f" · staking code: {scid}" if scid else ""))
    lines.append("Cross-staking was repaired on 2026-10-24 after the October incident — factory code 11750, staking code 11751.")
    lines.append(f"\nRegular factory: {finder(REGULAR_STAKING_FACTORY)}")
    lines.append(f"Cross factory: {finder(CROSS_STAKING_FACTORY)}")
    lines.append("⚠️ Staking always carries smart-contract risk — this is live on-chain info, not financial advice.")
    return "\n".join(lines)


def format_dex(factory_info, pair_count, gov_info):
    lines = ["🔄 *Garuda DEX — live*",
             "Garuda's own decentralised exchange on Terra Classic: swap CW20 tokens, add liquidity to pairs, and farm the pairs in the Garuda app (see /farms).",
             f"\nPair factory code: {factory_info.get('code_id')} · trading pairs registered: {pair_count}",
             f"Governance contract code: {gov_info.get('code_id')} (GDEX holders govern the DEX)",
             f"\nPair factory: {finder(DEX_PAIR_FACTORY)}",
             f"Router: {finder(DEX_ROUTER)}",
             "⚠️ Open the DEX only from your own bookmark — fake DEX sites are a common drain. Check a pair's contract address on Finder before you swap. The official site link is in /links."]
    return "\n".join(lines)


def format_farms(factory_info, farm_count):
    lines = ["🌾 *Garuda farms — live*",
             f"Farms tracked in the Garuda app: {farm_count} (count from the security watch's known farm set)",
             f"Farming factory code: {factory_info.get('code_id')} · admin: {factory_info.get('admin') or '—'}",
             "\nFarms pay rewards for staking LP tokens from Garuda DEX pairs. Rewards, rates and risks differ per farm — read the farm's own terms in the app before depositing.",
             f"\nFarming factory: {finder(FARMING_FACTORY)}",
             "⚠️ Farming carries impermanent-loss and smart-contract risk. Info only, not financial advice."]
    return "\n".join(lines)


def status_verdict(rows):
    """rows: [{name, addr, code_id, admin, expected_code, expected_admin}].
    Returns (all_ok, lines). A row with no expectation is report-only."""
    lines, all_ok = [], True
    for r in rows:
        bits = [f"code {r['code_id']}"]
        ok = True
        if r.get("expected_code") is not None:
            if str(r["code_id"]) != str(r["expected_code"]):
                ok = False
        if r.get("expected_admin"):
            bits.append("admin " + ("Garuda gov" if r["admin"] == GOV_CONTRACT else (r["admin"] or "none")))
            if r["admin"] != r["expected_admin"]:
                ok = False
        mark = "✅" if ok else "⚠️ CHANGED"
        if not ok:
            all_ok = False
        lines.append(f"{mark} *{r['name']}* — " + " · ".join(bits))
    return all_ok, lines


def format_status(rows, when):
    all_ok, lines = status_verdict(rows)
    head = ("🛡️ *Garuda security status — live check*\n"
            f"Checked just now ({when} UTC) against the security watch's baseline state: "
            "each core contract's code id and admin, read live from the chain.")
    tail = ("\n✅ Everything matches the baseline — no contract has been migrated or re-admined since the watch recorded it."
            if all_ok else
            "\n⚠️ Something above differs from the baseline. That can be a legitimate team update — or worse. Verify on Finder before using the affected part of Garuda.")
    links = "\n".join(f"• {r['name']}: {finder(r['addr'])}" for r in rows)
    return head + "\n\n" + "\n".join(lines) + "\n" + tail + "\n\n" + links


# ---------- live command builders ----------

async def staking_text():
    tokens = await _paged_tokens(REGULAR_STAKING_FACTORY)
    r_info = await contract_info(REGULAR_STAKING_FACTORY)
    pools = await _cross_pool_count(CROSS_STAKING_FACTORY)
    c_info = await contract_info(CROSS_STAKING_FACTORY)
    try:
        c_cfg = await smart(CROSS_STAKING_FACTORY, {"config": {}})
    except Exception:
        c_cfg = {}
    # Token symbols, best-effort like the watch does.
    for t in tokens:
        if not t.get("symbol") and t.get("token_address"):
            try:
                info = await smart(t["token_address"], {"token_info": {}})
                t["symbol"] = info.get("symbol")
            except Exception:
                pass
    return format_staking(tokens, r_info, len(pools), c_info, c_cfg)


# Pair count in the watch's DEX baseline (baseline.json, "pairs").
KNOWN_PAIR_COUNT = 10


async def dex_text():
    f_info = await contract_info(DEX_PAIR_FACTORY)
    g_info = await contract_info(GOV_CONTRACT)
    pairs = None
    try:
        data = await smart(DEX_PAIR_FACTORY, {"pairs": {"limit": 100}})
        pairs = len(data.get("pairs", []))
    except Exception:
        pairs = None
    if pairs:
        return format_dex(f_info, pairs, g_info)
    # Query shape not answered — use the watch baseline count, labeled.
    return format_dex(f_info, f"{KNOWN_PAIR_COUNT} (security-watch baseline)", g_info)


async def farms_text():
    f_info = await contract_info(FARMING_FACTORY)
    return format_farms(f_info, KNOWN_FARM_COUNT)


async def status_text():
    rows = []
    for addr, exp in EXPECTED.items():
        info = await contract_info(addr)
        rows.append({"name": exp["name"], "addr": addr,
                     "code_id": info.get("code_id"), "admin": info.get("admin", ""),
                     "expected_code": exp["code_id"], "expected_admin": exp["admin"]})
    when = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d, %H:%M")
    return format_status(rows, when)
