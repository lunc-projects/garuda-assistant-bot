"""Cross-bot daily usage stats — publish side (Garuda Assistant).

Steve's ruling (2026-10-27): the four assistant bots' usage counts
come together as ONE daily report from the LUNC Assistant bot. This
bot only publishes its own counts to a shared Upstash DB under
``botstats:garuda``; the LUNC bot reads them back at report time.

Counts ONLY — no names, titles, usernames or message text ever leave
the bot; payloads are plain numbers plus a unix timestamp.

Config is env-only: UPSTASH_STATS_URL + UPSTASH_STATS_TOKEN. When
either is unset, publish() is a silent no-op so the bot runs exactly
as before until the shared DB is wired up. All failures are swallowed:
stats must never break the bot.
"""
import json
import os
import time
from urllib.parse import quote

import httpx

BOT_NAME = "garuda"
KEY = "botstats:" + BOT_NAME
TTL_SECONDS = 3 * 24 * 3600          # a report key lives 3 days


def configured():
    return bool(os.getenv("UPSTASH_STATS_URL") and os.getenv("UPSTASH_STATS_TOKEN"))


def current_counts():
    """This bot's counts, from the same source /botstats uses:
    store.usage_counts() plus the AI pot (budget)."""
    import budget
    import store
    u = store.usage_counts()
    return {
        "groups_logging": u["groups"],
        "people_in_groups": u["people_in_groups"],
        "dm_users": u["dm_users"],
        "messages_logged": u["messages"],
        "pot_spent": budget.spent(),
        "pot_budget": budget.DAILY_TOKEN_BUDGET,
    }


def build_payload(counts, ts=None):
    payload = {"bot": BOT_NAME, "ts": int(ts if ts is not None else time.time())}
    payload.update(counts)
    return payload


async def publish(counts=None, client_factory=None):
    """Write this bot's counts to the shared DB. Returns True on
    success; False (silently) when unconfigured or on any failure."""
    try:
        if not configured():
            return False
        if counts is None:
            counts = current_counts()
        base = (os.getenv("UPSTASH_STATS_URL") or "").rstrip("/")
        headers = {"Authorization": f"Bearer {os.getenv('UPSTASH_STATS_TOKEN') or ''}"}
        factory = client_factory or (lambda: httpx.AsyncClient(timeout=15))
        async with factory() as client:
            r = await client.post(
                f"{base}/set/{quote(KEY, safe='')}?EX={TTL_SECONDS}",
                headers=headers, content=json.dumps(build_payload(counts)))
            r.raise_for_status()
        return True
    except Exception:
        return False
