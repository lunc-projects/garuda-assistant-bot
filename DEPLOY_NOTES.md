# Garuda Assistant Bot — deploy notes

Code is complete and tested; nothing is deployed yet. Deploying needs
Steve's BotFather token (his step — the token never goes through chat
or into the repo).

## 1. Steve's BotFather steps (create the bot ONLY — no games)

Games are out of this build by decision, so there is **no game
registration** step.

1. Open @BotFather → /newbot
2. Name: **Garuda Assistant** (display-name placeholder — change freely)
3. Username: Steve's pick (must end in `bot`)
4. Copy the token — it goes straight into the Railway env (step 2),
   never into chat, the repo, or any file here.
5. Optional, cosmetic: /setdescription / /setabouttext — the bot also
   sets its description + command list itself on boot (post_init).
6. Optional: a profile photo — if a file named `bot-profile-512.png`
   (512×512) is placed next to bot.py before deploy, the bot re-applies
   it on every boot. No photo ships with this build (the LUNC bot's
   logo was deliberately NOT copied).

## 2. Railway setup

- New service from this repo/dir (repo name per the spec:
  `garuda-assistant-bot`), start command: `python bot.py` (Procfile
  included), requirements.txt included.
- **Attach a volume mounted at /data** — the SQLite DB lives there so
  settings, language prefs, FAQs, ban lists and the message log survive
  redeploys.
- Environment variables:

| Var | Value | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | the BotFather token | Steve pastes it here himself |
| `AI_API_KEY` | Groq API key | Same Groq free account pattern as the other bots; the daily pot is 200,000 tokens/day (budget.py) |
| `AI_BASE_URL` | `https://api.groq.com/openai/v1` | Groq endpoint |
| `AI_MODEL` | `openai/gpt-oss-120b` | The model the pot is sized for |
| `OWNER_TELEGRAM_ID` | Steve's numeric Telegram id | Owner gates: /approve, /gban undo alerts, /botstats, rank overrides |
| `DB_PATH` | `/data/messages.db` | Optional — this is already the default when /data exists |
| `RETENTION_DAYS` | `7` | Optional — message log retention for summaries |
| `OUTBOUND_PROXY` | — | Only if the host needs the egress proxy (the other bots use it on this infra) |

## 3. /setcommands list (the bot also sets this itself on boot)

```
summary - Summarize group messages
catchup - What you missed
tldr - Shrink a message (reply to it)
ask - Ask me anything
dex - Garuda DEX overview (live)
staking - Garuda staking status (live)
farms - Garuda farms overview (live)
status - Garuda security status (live check)
proposals - Proposals voting now
proposal - Proposal + tally
price - LUNC + USTC price
stats - Chain stats
govalerts - Proposal alerts on/off
wallet - Public wallet lookup
token - CW20 token info
rank - Your rank in this chat
language - Choose your language
privacy - Privacy & security info
protect - Request scam protection (group admins)
aiban - AI-ban a user (moderators)
appeal - Appeal a ban (in DM)
rules - This group's rules
menu - Buttons menu — no typing
panel - Admin panel (group admins)
help - All commands
```

## 4. First-run checks after deploy

1. DM the bot /start → language picker + Garuda intro.
2. /dex /staking /farms /status in DM → live answers (status should
   read all-clear against the baseline; if a row shows CHANGED, the
   team may have legitimately updated a contract — verify on Finder
   and update garuda.py's EXPECTED + the watch baseline together).
3. /ask was garuda hacked → instant KB incident summary (no AI spend).
4. Add the bot to a test group as admin (Ban users + Delete messages),
   run /protect, approve from the owner DM, join with a second account
   → the 4-tap gate fires in DM.
5. /summary after some chatter → AI summary; check the pot line with
   /botstats (owner only).

## 5. TODO_LINKS — official Garuda links still to confirm

The bot publishes ONLY links verified from the garuda-watch sources or
Steve's verified facts. The following are **not** in the bot yet —
confirm each with the Garuda team / Steve, then add to bot.py
LINKS_TEXT (and kb.py "links") in one edit:

- [ ] **Garuda official website** — `garuda-defi.org` is the domain the
      LUNC bot's (user-verified) DEX list carried for the Garuda DEX,
      and it is already in this bot's first-message link allowlist on
      that basis — but it was NOT found in the garuda-watch code, so it
      is not published in /links until Steve confirms it is the
      official one to publish.
- [ ] **Garuda X (Twitter) account** — no handle verified; none published.
- [ ] **Garuda docs / gitbook** — none verified; none published.
- [ ] **Garuda DEX direct app URL** — follows from the website decision.
- [ ] Wallet download links for /links (Station / Keplr / Cosmostation)
      — intentionally left out of the Garuda /links until the website
      pass; the safety texts reference the wallets by name only.

Verified and already in the bot:
- Garuda community Telegram group: https://t.me/Garudaverse99
- Finder (chain explorer): https://finder.terraclassic.community —
  every Garuda contract in /dex, /staking, /farms, /status links here
  with its full address.

## 6. Known maintenance points

- `garuda.py` EXPECTED (code ids + admins) mirrors the garuda-watch
  baselines (baseline.json / baseline_staking.json /
  baseline_regular.json, re-checked Oct 25, 2026). If the Garuda team
  legitimately migrates a core contract, update EXPECTED and the watch
  baseline in the same pass, or /status will (correctly) flag CHANGED.
- Farm count (389) and DEX pair fallback count (10) come from the
  watch's known sets and are labeled as such in the bot's answers.
