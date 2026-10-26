# Garuda Assistant Bot

A standalone Telegram assistant for **Garuda DeFi** (Terra Classic), forked
from the LUNC Assistant Bot's design — same structure, features and
mechanics, with all content and identity replaced for Garuda. Garuda only:
no other projects, no validator content, no games (games are deferred).

## What it does

- **Summaries** — /summary, /catchup, /tldr, DM long-text summaries
  (AI via Groq, with the daily token pot: 200,000 tokens/day on the Groq
  free allowance, rank caps 2/4/6 per user and 10/20/30 per chat per day,
  owner exempt; when the pot is empty the bot keeps working with basic
  non-AI summaries and "daily limit reached" notes).
- **/ask + mentions** — Garuda questions are answered instantly from the
  built-in knowledge base (kb.py, verified facts only); everything else
  goes to the AI with the same KB as its system context.
- **Live Garuda data** (read-only PublicNode LCD queries, garuda.py):
  /dex, /staking, /farms, /status (a live code-id + admin check of
  Garuda's core contracts against the security watch's baseline).
- **Chain data** for Garuda users (Garuda runs on Terra Classic):
  /price, /stats, /convert, /proposals, /proposal, /wallet, /token,
  plus /govalerts proposal notifications.
- **Group protection suite** (opt-in, owner-approved): join gate
  (4 randomized human-check taps, 3 strikes), global bans with owner
  one-tap undo + permanent mod log, AI bans, /mute, word blacklist,
  anti-raid, flood + cross-group repeat controls, fresh-account 24h
  text-only hold, first-message link rule with a Garuda allowlist,
  edit/caption checks, /report, /appeal, per-group /faq, hashtags,
  /menu and /panel, /aioff /aion.
- **/language** — 18 languages, per-user. **Persistence** — SQLite on
  the /data volume (DB_PATH), so redeploys don't wipe settings.
- **Read-only by construction** — no wallet, keys, signing or sending
  code anywhere in the bot.

## Run

See DEPLOY_NOTES.md for Railway setup, env vars, and the BotFather steps.

## Tests

Stdlib-only, no network: `python3 test_*.py` (each file runs standalone).
test_garuda.py covers the Garuda data commands with a mocked LCD, the
KB, address provenance against the garuda-watch sources, and the
Garuda-only / no-games guarantees.
