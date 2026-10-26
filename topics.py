"""Hashtag topic answers, Garuda DeFi + Terra Classic basics.

In a group, typing a hashtag like #staking makes the bot reply with a
short, ready answer. Content is static and factual — live numbers
always point at the live commands (/dex, /staking, /farms, /status).
Only tags with verified content are included; #rules, #welcome and
#commands are dynamic and handled in bot.py.
"""

TOPICS = {
    "safety": (
        "🛡 Safety rules\n"
        "• No real admin will EVER DM you first, ask for your seed phrase, or ask you to 'verify' your wallet. Ever.\n"
        "• There are no doubling giveaways and no surprise prizes that need a wallet approval.\n"
        "• Only trust links from this group's admins. Full guide: /safety"),
    "scammed": (
        "🚨 If you were just scammed\n"
        "1. Send nothing more, and don't pay anyone who promises to 'recover' it — recovery fees are a second scam. On-chain transfers can't be reversed.\n"
        "2. If a site or person got your seed phrase, that wallet is burned forever: move anything left to a brand-new wallet with a new seed.\n"
        "3. Save tx hashes, addresses, and screenshots, and warn the group so others don't get hit."),
    "memo": (
        "🏷 About memos\n"
        "Sending LUNC to an exchange? Most exchanges use ONE shared deposit address plus a unique MEMO for your account. "
        "Forget the memo and your deposit may not arrive — recovery is slow and sometimes impossible.\n"
        "Sending between your own wallets usually needs no memo. Always send a small test first."),
    "revokeaccess": (
        "🔌 Revoking access\n"
        "Terra Classic has no EVM-style approval list to revoke. What you can do: disconnect dApps inside your wallet "
        "(Station / Keplr settings → connected sites), and if you ever typed your seed phrase anywhere, treat that wallet "
        "as compromised — move funds to a fresh wallet with a new seed."),
    "garuda": (
        "🦅 What is Garuda DeFi\n"
        "A DeFi platform built natively on Terra Classic: a DEX for swaps and liquidity, regular + cross staking pools, "
        "NFT staking, and yield farms — governed by GDEX holders. Live overviews: /dex · /staking · /farms · /status"),
    "dex": (
        "🔄 Garuda DEX\n"
        "Garuda's own decentralised exchange on Terra Classic: swap CW20 tokens through liquidity pairs, or provide "
        "liquidity and earn swap fees. Live status + contract links: /dex\n"
        "⚠️ Open the DEX only from your own bookmark — fake DEX sites are a common drain. Check a pair's contract on Finder before you swap."),
    "staking": (
        "🥩 Garuda staking\n"
        "Two systems: regular staking (single-token CW20 pools — untouched by the October 2026 incident) and "
        "cross-staking (drained in October 2026, repaired by the team on Oct 24 — factory code 11750, staking code 11751). "
        "Live pool counts and codes: /staking"),
    "farms": (
        "🌾 Garuda farms\n"
        "Farms pay rewards for staking LP tokens from Garuda DEX pairs; the Garuda app tracks 389 farms. "
        "Farming adds impermanent-loss risk (#il) on top of price risk. Overview: /farms"),
    "security": (
        "🛡️ Garuda security status\n"
        "Run /status — it re-reads Garuda's core contracts (code ids + admins) live from the chain and compares them "
        "with the post-repair baseline from the October 2026 incident. In short: NFT staking was exploited Oct 20 and "
        "cross-staking drained Oct 21; regular staking and the DEX were not drained, and the cross-staking factory "
        "was repaired Oct 24. Ask me 'what happened in October' for the full verified summary."),
    "il": (
        "⚖️ Impermanent loss (IL)\n"
        "When you provide liquidity to a pool, price moves can leave you with less value than if you'd simply held both "
        "tokens. The bigger the price swing, the bigger the gap; trading fees and rewards are what offset it. "
        "It's only locked in when you withdraw."),
    "wallets": (
        "👛 Wallets for Terra Classic\n"
        "Station · Keplr · Cosmostation — get them only from their official sites/app stores; look-alike domains are a "
        "top scam. Type the address yourself, never follow a DM link. (Official download links are being confirmed — "
        "ask in the group if you're unsure.)"),
    "endpoints": (
        "🌐 Public Terra Classic endpoints\n"
        "LCD: https://terra-classic-lcd.publicnode.com\n"
        "RPC: https://terra-classic-rpc.publicnode.com\n"
        "Explorer (Finder): https://finder.terraclassic.community"),
    "commonissues": (
        "🛠 Common issues\n"
        "• Tx failing? Usually gas — raise the fee/gas slightly and retry.\n"
        "• Exchange deposit missing? Check you included the MEMO (#memo).\n"
        "• 'Transport error' or wallet won't connect? It's a wallet↔chain connection issue — reconnect, or try the public endpoints (#endpoints).\n"
        "• Check any tx yourself on Finder by pasting its hash."),
    "props": (
        "🗳 Governance\n"
        "Terra Classic proposals voting right now: /proposals · Details and live tally: /proposal <id>\n"
        "Your vote counts through your staking wallet — the bot never votes for anyone."),
    "links": (
        "🔗 Links\n"
        "The verified list lives here: /links — the Garuda community group and the on-chain contract links. "
        "Website/X links are added only once confirmed official."),
}

ALIASES = {
    "safetytips": "safety", "scamwarning": "safety", "phishwarning": "safety", "nodm": "safety",
    "networks": "endpoints",
    "transporterror": "commonissues", "troubleshoot": "commonissues",
    "bridging": "endpoints",
    "terrastation": "wallets", "station": "wallets",
    "dexes": "dex", "swap": "dex", "trading": "dex", "exchanges": "dex", "garudadex": "dex",
    "stake": "staking", "crossstaking": "staking",
    "farming": "farms", "yieldfarming": "farms",
    "hack": "security", "hacked": "security", "incident": "security", "status": "security",
    "impermanentloss": "il",
    "whatisgaruda": "garuda",
}


def lookup(tag):
    """Answer text for a hashtag (without '#'), or None if unknown."""
    tag = (tag or "").lower().lstrip("#")
    if tag in TOPICS:
        return TOPICS[tag]
    canon = ALIASES.get(tag)
    return TOPICS.get(canon) if canon else None


def known(tag):
    tag = (tag or "").lower().lstrip("#")
    return tag in TOPICS or tag in ALIASES or tag in ("rules", "welcome", "commands")


def commands_text():
    tags = sorted(set(TOPICS) | set(ALIASES) | {"rules", "welcome", "commands"})
    return "🏷 Hashtags I answer in chat:\n" + " ".join("#" + t for t in tags) + "\nJust type one in the group — e.g. #staking or #security."
