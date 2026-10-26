"""Live Terra Classic data — PublicNode LCD + CoinGecko.
Generic public chain data for the Garuda Assistant Bot (Garuda lives
on Terra Classic). Garuda-specific contract data lives in garuda.py."""
import base64, json, os
import httpx
LCD = "https://terra-classic-lcd.publicnode.com"

async def _get(path):
    async with httpx.AsyncClient(timeout=25, proxy=os.getenv('OUTBOUND_PROXY') or None) as c:
        r = await c.get(f"{LCD}{path}"); r.raise_for_status(); return r.json()

async def prices():
    async with httpx.AsyncClient(timeout=25, proxy=os.getenv('OUTBOUND_PROXY') or None) as c:
        r = await c.get("https://api.coingecko.com/api/v3/simple/price?ids=terra-luna,terrausd&vs_currencies=usd&include_24hr_change=true&include_market_cap=true&include_24hr_vol=true")
        r.raise_for_status(); return r.json()

def fmt_price(d, name):
    return (f"{name}: ${d['usd']:.8g} ({d.get('usd_24h_change',0):+.2f}% 24h)\n"
            f"   Market cap: ${d.get('usd_market_cap',0):,.0f} | 24h volume: ${d.get('usd_24h_vol',0):,.0f}")

async def stats_text():
    block = await _get("/cosmos/base/tendermint/v1beta1/blocks/latest")
    height = block["block"]["header"]["height"]
    supply = await _get("/cosmos/bank/v1beta1/supply/by_denom?denom=uluna")
    total = int(supply["amount"]["amount"]) / 1e6
    pool = await _get("/cosmos/staking/v1beta1/pool")
    bonded = int(pool["pool"]["bonded_tokens"]) / 1e6
    pct = bonded / total * 100 if total else 0
    return (f"📊 *Chain — live (Terra Classic, the chain Garuda runs on)*\nBlock height: {height}\n"
            f"Total LUNC supply: {total:,.0f}\nBonded (staked): {bonded:,.0f} LUNC ({pct:.1f}% of supply)\n"
            f"Source: PublicNode LCD")

async def proposals_voting():
    d = await _get("/cosmos/gov/v1/proposals?proposal_status=2&pagination.limit=50")
    return d.get("proposals", [])

async def proposal_detail(pid):
    d = await _get(f"/cosmos/gov/v1/proposals/{pid}")
    return d["proposal"]

async def proposal_tally(pid):
    d = await _get(f"/cosmos/gov/v1/proposals/{pid}/tally")
    return d["tally"]

def tally_text(t):
    y, a, n, v = (int(t[k]) / 1e6 for k in ("yes_count", "abstain_count", "no_count", "no_with_veto_count"))
    total = y + a + n + v
    non_abstain = y + n + v
    if total == 0: return "No votes yet."
    def pc(x, base): return f"{x/base*100:.1f}%" if base else "—"
    return (f"YES {y:,.0f} ({pc(y, non_abstain)} of non-abstain)\nNO {n:,.0f}\n"
            f"NO WITH VETO {v:,.0f} ({pc(v, non_abstain)})\nABSTAIN {a:,.0f}\nTotal voted: {total:,.0f} LUNC")

async def wallet_text(addr):
    if not (addr.startswith("terra1") and len(addr) >= 39):
        return "That doesn't look like a Terra Classic address (terra1…)."
    bal = await _get(f"/cosmos/bank/v1beta1/balances/{addr}")
    lines = ["💼 *Wallet* (public on-chain data)"]
    if not bal.get("balances"): lines.append("Balances: 0 / no native balances found")
    for b in bal.get("balances", []):
        denom = {"uluna": "LUNC", "uusd": "USTC"}.get(b["denom"], b["denom"])
        amt = int(b["amount"]) / 1e6
        lines.append(f"{denom}: {amt:,.2f}")
    try:
        dels = await _get(f"/cosmos/staking/v1beta1/delegations/{addr}")
        tot = 0.0; rows = []
        for d in dels.get("delegation_responses", []):
            amt = int(d["balance"]["amount"]) / 1e6; tot += amt
            rows.append((d["delegation"]["validator_address"], amt))
        if rows:
            lines.append(f"\nStaked total: {tot:,.2f} LUNC across {len(rows)} validator(s)")
            for va, amt in rows[:10]: lines.append(f"• {va[:20]}… : {amt:,.2f}")
    except Exception: pass
    lines.append(f"\nFull history: https://finder.terraclassic.community/address/{addr}")
    lines.append("🔒 Public data only — never share a seed phrase with anyone, this bot will never ask.")
    return "\n".join(lines)

async def token_text(addr):
    q = base64.b64encode(json.dumps({"token_info": {}}).encode()).decode()
    try:
        d = await _get(f"/cosmwasm/wasm/v1/contract/{addr}/smart/{q}")
        info = d["data"]
    except Exception:
        return "Couldn't read that contract — check it's a CW20 contract address on Terra Classic."
    dec = int(info["decimals"]); supply = int(info["total_supply"]) / (10 ** dec)
    return (f"🪙 *{info['name']} ({info['symbol']})*\nDecimals: {dec}\nTotal supply: {supply:,.2f} {info['symbol']}\n"
            f"Contract: {addr}\nhttps://finder.terraclassic.community/address/{addr}\n"
            f"⚠️ Token info is on-chain data only — it does NOT verify a token is safe or legitimate. Always DYOR.")
