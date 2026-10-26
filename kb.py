"""Garuda DeFi knowledge base.

Facts only — written from the verified record (the Garuda security
watch's on-chain baselines and the October 2026 incident investigation).
No invented links, rates, or numbers: anything live points at the live
commands (/dex, /staking, /farms), and anything not verified
here is simply not claimed. Owner: keep this file current when the
team publishes new official info.
"""

_FINDER = "https://finder.terraclassic.community/address/"

KB = {
    "what is garuda": (
        "Garuda DeFi is a decentralised-finance platform built natively on Terra Classic. "
        "Its pieces: a DEX (swap CW20 tokens and provide liquidity), regular CW20 staking pools, "
        "cross-staking, NFT staking, and yield farms for DEX liquidity pairs — all governed by "
        "GDEX token holders through the Garuda governance contract. "
        "Live on-chain overviews: /dex · /staking · /farms"),
    "dex": (
        "The Garuda DEX is an automated-market-maker exchange on Terra Classic. You swap one CW20 "
        "token for another through liquidity pairs, or add both sides of a pair as liquidity and "
        "earn a share of swap fees. Prices come from the pool ratios, so big trades move the price "
        "(slippage) — check the pair's contract on Finder before a large swap. Live status: /dex"),
    "how to swap": (
        "Swapping on the Garuda DEX, in outline: (1) open the official Garuda site from your own "
        "bookmark — never from a DM link; (2) connect a Terra Classic wallet (Station / Keplr / "
        "Cosmostation); (3) pick the pair and amounts, read the estimated received amount and "
        "slippage; (4) approve and sign in your wallet; (5) verify the result on Finder. "
        "Start with a small test swap if it's your first time."),
    "staking": (
        "Garuda has two staking systems. Regular staking: single-token CW20 pools registered in "
        "the regular staking factory — stake one token, earn rewards; it was NOT affected by the "
        "October 2026 incident. Cross-staking: pools that pair tokens across contracts; it was "
        "drained in October 2026 and repaired by the team on 2026-10-24 (factory code 11750, "
        "staking code 11751). Live pool counts and codes: /staking · pools and farms: /farms"),
    "farms": (
        "Garuda farms pay rewards for staking LP (liquidity-provider) tokens from Garuda DEX "
        "pairs. The Garuda app tracks 389 farms. Farming adds impermanent-loss risk on top of "
        "normal price risk: if the pair's prices move apart, you can end up with less than "
        "simply holding the two tokens. Overview: /farms"),
    "gdex": (
        "GDEX is Garuda's governance token. GDEX holders govern the DEX through the Garuda "
        "governance contract "
        f"({_FINDER}terra1t6h84pcvtawc0e8x9xwp8a59hwcc00dgcfsswhjpqgsuyr9t7k0sfwfqu6). "
        "This bot doesn't quote prices or supply figures for GDEX — check a live source."),
    "incident": (
        "What happened in October 2026, from the verified on-chain record: "
        "On Oct 20, Garuda's NFT staking factory was exploited through an unrestricted "
        "migration entry point — 35 staking contracts were affected, 1,084 NFTs were moved, "
        "and most of those NFTs ended up frozen in place rather than stolen. "
        "On Oct 21, the cross-staking factory was drained the same way: 9 contracts, about "
        "59.1M LUNC plus about 4,284 USTC. "
        "The regular staking pools and the DEX itself were NOT drained. "
        "The Garuda team repaired the cross-staking factory on Oct 24 (codes 11750 / 11751). "
        "The Garuda team did not hack itself — the drain was an external attack, and no culprit "
        "has been publicly identified."),
    "is garuda safe": (
        "No DeFi platform is risk-free, and Garuda was exploited in October 2026 (ask me what "
        "happened in October for the verified summary). What you can verify yourself, any "
        "time: the contract addresses in /dex, /staking and /farms all link to Finder, where "
        "you can check code ids and admins yourself. Use your own judgment, start small, "
        "and never deposit more than you can afford to lose."),
    "links": (
        "Verified here: the Garuda community group on Telegram is @Garudaverse99, and every "
        "Garuda contract can be verified on Finder (finder.terraclassic.community) — /dex, "
        "/staking and /farms include the contract links. This bot does not publish a website "
        "or X link for Garuda until the official one is confirmed; beware of look-alike sites."),
}

# Keyword -> KB key. find_kb_answer returns the entry whose longest
# keyword phrase appears in the lowercased question.
_KEYWORDS = {
    "what is garuda": ("what is garuda", "about garuda", "garuda defi"),
    "incident": ("hack", "hacked", "drain", "drained", "exploit", "stolen", "attack", "october"),
    "is garuda safe": ("safe", "trust", "legit"),
    "how to swap": ("how to swap", "how do i swap"),
    "dex": ("dex", "swap", "exchange", "liquidity"),
    "staking": ("staking", "stake", "cross-staking", "cross staking"),
    "farms": ("farm", "farming", "yield"),
    "gdex": ("gdex", "governance token", "gov token"),
    "links": ("link", "website", "official site", "telegram group"),
}


def kb_as_text() -> str:
    """The whole KB as one block for the AI system prompt."""
    lines = ["Garuda DeFi knowledge base (verified facts — prefer these over general knowledge; "
             "if a question isn't covered here, say so rather than inventing details):"]
    for key, text in KB.items():
        lines.append(f"\n[{key}]\n{text}")
    return "\n".join(lines)


def find_kb_answer(q: str):
    """Instant no-AI answer when a question clearly matches a KB topic."""
    low = (q or "").lower()
    best, best_len = None, 0
    for key, words in _KEYWORDS.items():
        for w in words:
            if w in low and len(w) > best_len:
                best, best_len = key, len(w)
    return KB.get(best) if best else None
