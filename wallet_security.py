"""Wallet Security — personal wallet monitoring for the Garuda Assistant Bot.

Owner-directed feature (2026-10-29): a community member registers THEIR
OWN wallet with /watch in DM, and the bot checks it about every 15
minutes and DMs them — and only them — when something changes:

  * bank balances (LUNC / USTC),
  * CW20 token balances (approach + limits below),
  * Garuda staking positions: regular CW20 staking pools, cross-staking
    pools, and NFT staking records,
  * NFT holdings in the Garuda NFT collections (plus staked-NFT counts).

It is READ-ONLY by construction: addresses only, no keys ever, no
signing, no sending. It DETECTS and NOTIFIES — it cannot prevent or
reverse anything, and the intro copy says so plainly.

It uses ZERO AI tokens: the checker is deterministic chain reads on a
timer. The Groq pot (budget.py) is spent only when a member separately
asks the bot an AI question.

NO FALSE ALARMS (trust-critical):
  * Registration snapshots a silent baseline — the first check never
    alerts.
  * A failed or partial chain read skips that wallet's cycle silently
    (snapshot untouched, retried next cycle). Nothing is ever alerted
    on read errors or partial data.
  * Alerts fire only on a real diff against the stored snapshot, and
    the snapshot advances only after the alert DM is delivered; a
    per-watch last-alert hash stops a duplicate send if the snapshot
    save itself fails.

NEVER SILENT WHEN DOWN (owner requirement, 2026-10-29):
  * Consecutive failed/partial sweeps are counted in the DB; at >= 3
    the OWNER gets a DM (once per outage episode).
  * /botstats shows the last successful sweep time.
  * A watchdog job alerts the owner if no successful sweep completes
    within 2x the sweep interval (once per episode).
  * Downtime is announced to watchers as a SECURITY UPDATE: on graceful
    shutdown a best-effort DM says the wallet is temporarily
    unprotected; after the first successful sweep on startup, watchers
    are told protection is back (with the offline window when the last
    sweep timestamp shows a gap). The post-restart sweep still diffs
    against the stored baseline, so changes that happened during the
    downtime ARE alerted, labeled as detected on return.
  * User-facing messages are change/downtime notices only — no health
    noise. All Wallet Security DMs are plain text (no Markdown parse
    mode — the entity-parse lesson).

CW20 DISCOVERY — approach and limits:
  Terra Classic has no chain endpoint that enumerates every CW20
  balance for a wallet, so the checker reads balances for a Garuda
  token UNIVERSE rebuilt from live chain data each sweep:
    - every token registered in the Garuda regular staking factory,
    - every cross-staking pool's staking token + CW20 reward tokens,
    - every NFT-staking reward token in the verified census below,
    - every CW20 in a Garuda DEX pair (incl. LP tokens).
  Limits, stated honestly: a CW20 outside that universe (a brand-new
  token nobody has staked / paired on Garuda yet) is not seen until it
  joins the universe. Bank LUNC/USTC are always covered.

How positions are read (all verified live on columbus-5, 2026-10-29):
  * Regular staking: targeted RAW state read, namespace "STAKING",
    key = wallet string, value JSON {"amount": ...}. A missing key
    returns data:null — a clean zero, not an error.
  * Cross staking: same pattern, namespace "STAKED_ASSETS", value JSON
    {"amount": ..., "staker_address": ...} (the smart query
    {"assets": {"staker": addr}} -> {"staked_assets": ...} agrees).
  * NFT staking: smart queries are dead on the post-hack code, so the
    sweep scans RAW contract state of the 35 census contracts once per
    sweep (shared across wallets) and extracts STAKED_NFT /
    UNSTAKED_NFT records by staker. That mirrors garuda-watch's
    check_nft_contents.py.
  * NFT holdings: CW721 {"tokens": {"owner": addr}} enumeration per
    collection. A collection whose contract answers that query with a
    "not supported"-style error is marked non-enumerable for the
    process lifetime and skipped (documented limit); any other read
    error fails the wallet's cycle instead of guessing.
"""

import asyncio
import base64
import hashlib
import json
import time
from decimal import Decimal

import httpx

import garuda
import store

LCD = garuda.LCD if hasattr(garuda, "LCD") else "https://terra-classic-lcd.publicnode.com"
FINDER = "https://finder.terraclassic.community/mainnet"

MAX_WATCHES_PER_USER = 3
SWEEP_INTERVAL_SECONDS = 900            # ~15 minutes
FAILURE_ALERT_THRESHOLD = 3             # consecutive failed/partial sweeps
WATCHDOG_STALE_SECONDS = 2 * SWEEP_INTERVAL_SECONDS

FEATURE_NAME = "Wallet Security"

INTRO = (
    "🔐 Wallet Security\n"
    "\n"
    "Register your own wallet and I will check it about every 15 minutes and DM you here if something changes:\n"
    "• LUNC / USTC balances moving in or out\n"
    "• CW20 token balances (the Garuda token set — staking, cross-staking, NFT rewards and DEX tokens)\n"
    "• Garuda staking positions going up or down (regular pools, cross-staking, NFT staking)\n"
    "• NFTs arriving or leaving in the Garuda collections\n"
    "\n"
    "To start, send me:\n"
    "/watch terra1...\n"
    "\n"
    "Honest limits, in plain words:\n"
    "• This DETECTS and NOTIFIES. It cannot prevent or reverse anything.\n"
    "• Addresses only — I never ask for keys or seed phrases, ever. This is read-only.\n"
    "• Checks run about every 15 minutes, so an alert can arrive up to ~15 minutes after a change.\n"
    "• Up to 3 wallets per person.\n"
    "\n"
    "/watching — your wallets + when each was last checked\n"
    "/unwatch terra1... — stop watching a wallet\n"
    "/watch off — pause your alerts · /watch on — resume them"
)

GROUP_REDIRECT = ("DM me to set up Wallet Security — send me /watch in a private chat. "
                  "Wallet addresses are never set up in a group.")

DOWN_NOTICE = ("⚠️ Wallet Security: your wallet is temporarily unprotected — "
               "a security update is in progress. Protection will resume as soon as the update is done.")
BACK_NOTICE = ("✅ Wallet Security: security update complete — "
               "your wallet is protected again.")

# The 35 Garuda NFT staking contracts and their collections / reward
# tokens — from the verified on-chain census in garuda-watch
# (check_nft_contents.py; garuda-nft-verification-2026-10-23).
NFT_STAKING_CONTRACTS = {'terra10aglafvfs4zs5zdn00c0srmpy2huupp59pqzrs2j26qar6dxmwpqey0egt': {'collection': 'terra1ma45lcarhtra77j2tqs6hjgvc3uz26yrwysfftygjlvwsztrzewqv2y0cp',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'BOYS',
                                                                      'reward_token': 'terra1a4x7t4w7a5hwqph0q0m5maqu45j99cpkgt82rllvrh4hc6g53k7spulsqj'},
 'terra10mtzcw25jgwer66zyl3xpugzzwkru6vfm64z7qa8fpwqawhhfjxq0pnhum': {'collection': 'terra1elgkxqspyqr5al3tlewqfwdcedr3mrn84nwd7h',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'BULL',
                                                                      'reward_token': 'terra1sl0cgtanapyy449h0hlmt77s8hak7caktvky8t4ct7a7kvjtyyvqzg8rv6'},
 'terra13ksrsjvd9znvx4e27hycncg86y65ugy4dwj48lmy5gh0eq4rwy8qsxe7ys': {'collection': 'terra19yfs2kjeeq85d8qpqdma4j2r0wcytd8zzsw9njm3dv7jkeu3sfsqtr3j84',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'QUID',
                                                                      'reward_token': 'terra1zmsv8khmsrz2xj8zuhu7r7yruf5dfsyhtqyqf5lf92f2uvz6lf9sx5sr79'},
 'terra16us90plgwtt44szqfussek556q3n0r6l5jetq62khpwg45gyauvqrt6wm5': {'collection': 'terra1h7695hzkhr950prrr8ptf957rcclf252unsn36lv5uhmnps307hq4g09wn',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'LTRN',
                                                                      'reward_token': 'terra1wwrg00jczxf4czy4jr4wc2nvgpl4un4g8fjvm2zy54neel7ygqgsmlhhvp'},
 'terra17gr9m652lzhl5yv70ss36an0rc9htkwnspeq63t3w5uvg2d72srqkyp8gv': {'collection': 'terra1406z74rnr0fmk8w8l07umrzm6e3xguygurgst4',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'BULL',
                                                                      'reward_token': 'terra1sl0cgtanapyy449h0hlmt77s8hak7caktvky8t4ct7a7kvjtyyvqzg8rv6'},
 'terra18rr5nuswj0sdtt5vty865eynqcdd86xqul9wr932ljea86fj7f3qshyqyz': {'collection': 'terra1lvsslpr4rdx3mpvwht3nc2wqsehc82f00hkgwat0k8uem4dz225qnqhzym',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'SPACEX',
                                                                      'reward_token': 'terra14mqjm7n23ky3479hmaarzqnwrlmapje08runh5m7a29rz6sunhpsn9pq27'},
 'terra199n9vpux4zaydy92jyhxfeyd9k695seea68nyq5c8j89yxf4xtgss3sg4d': {'collection': 'terra1x0yw2z00j295rtd8rfg3mrmvsqrcyw8syac7eqvu7vyze3mzcc0q66ql8p',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'GRDX',
                                                                      'reward_token': 'terra12f3f5fzfzxckc0qlv3rmwwkjfhzevpwmx77345n0zuu2678vxf0sm6vvcw'},
 'terra1adjd4pl6z4c7q82fte0zsg27pl39xmt3f76z208wgkgjpe03nsasxxgfc4': {'collection': 'terra13ck7exyuaqsxl5cqzqvg8l4997p3xst5yhn6tsdp904svfr7wqwsg2x80x',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'SMT',
                                                                      'reward_token': 'terra1rc4ef7s6pzuf9pkg8ymnw29pjz2yfm3tjg0kleu4348c2e6upkxqdfdj5u'},
 'terra1e8z8lqjq0zch5zzalwc8k2suzenzw8s6qdw5nqx4hvmfr6ax7qwsyredg8': {'collection': 'terra15skdn2jkn7347pgrz0sa9wsmesffud8zr3avwgkk85k7l3m9xj4q5ngf6n',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'GRDX',
                                                                      'reward_token': 'terra12f3f5fzfzxckc0qlv3rmwwkjfhzevpwmx77345n0zuu2678vxf0sm6vvcw'},
 'terra1hgwrmsva5c5rpxt4xsqcx0tdgfry8mpnskje0pa5fmz6glwmwrlsv45uzy': {'collection': 'terra1v823yz492lwd9009dthx9h0cr93l03mpmp3etse78stuahxqnqwslpjnzu',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'PoG',
                                                                      'reward_token': 'terra1rdxr2nhqlhw7jq0ved7srvwwuvk98g28e97s5c0seyrcel4364rsrdapge'},
 'terra1hukx5ze0xcmqjaf48xf5duajp4azx9v2s9pvapc4z7fun5asd3wqqnv2j6': {'collection': 'terra19wz8gw49hp0myv7fnzuwhfaml684pcn7falsk0',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'GRDX',
                                                                      'reward_token': 'terra12f3f5fzfzxckc0qlv3rmwwkjfhzevpwmx77345n0zuu2678vxf0sm6vvcw'},
 'terra1j26gc9g2n7uk8f0w9y83pa5p2h9cyptw0ap5nvuhrx2stsdpregqfa97v8': {'collection': 'terra1v823yz492lwd9009dthx9h0cr93l03mpmp3etse78stuahxqnqwslpjnzu',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'GRDX',
                                                                      'reward_token': 'terra12f3f5fzfzxckc0qlv3rmwwkjfhzevpwmx77345n0zuu2678vxf0sm6vvcw'},
 'terra1jsc8ngrvlwr2k643argepuc3xxrugf5zt5axp0zycaedjvpxv3tqzc5dcr': {'collection': 'terra1qwye5h4xhd6qt4k5vyn7ekml5wj8fmwgk7qjtll0klf07zhlwadspx23rr',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'TCR',
                                                                      'reward_token': 'terra1c3m0mfshydl4dc27xmwun2g938delmpcd6tm7qr3vln8kh7ahwxsz526jm'},
 'terra1kf7kxkp4564yjk5ejhxe2u88ml9vv5uatswdwflqfparnntwvygsdrn4ym': {'collection': 'terra17spx7su47l4m4ep22sfljt3plj5d74fcpzjmx5uzz9a6cdcj8ncqq62py9',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'DO',
                                                                      'reward_token': 'terra15p8su45k45axng8ue59rl6zph4at27s49u3agr6uqrx3dhcxpg3qt0ekdt'},
 'terra1khh2d0x9u9pntfhsex3js5kpz6ytrqr6mkq98gxgxrs4p9nnlreqwca3rl': {'collection': 'terra18avpa8d9h9jk4cqwu86j50xw4nlfa0zt28k44s5ttrkwm6mfgy5smz0nu6',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'DO',
                                                                      'reward_token': 'terra15p8su45k45axng8ue59rl6zph4at27s49u3agr6uqrx3dhcxpg3qt0ekdt'},
 'terra1l2lwqjqrkwz0cp4jngxhppmaws55jme37fmdesz29cmgqknekdnshts75z': {'collection': 'terra1k4jxlmdpru8k9fayhaag6jqwzgaa8jh0993neatmcn99vg0rcmnsny2xjr',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'CODE',
                                                                      'reward_token': 'terra1l435jetw69mxym6enacraelpsp85se4mhkpcea8342s3vanqv9yqp74p42'},
 'terra1mcywye6mepvghrpskp7mmd6mmalf0rsg64ujysqvzk85tlkx6pvs0dzjfj': {'collection': 'terra1n8626dsgtvgrqet6x0e43r4r60f30vpe074drdkd3329n6cnnsesjuuepp',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'HNT',
                                                                      'reward_token': 'terra1gm4fzalxdhjt0hl398dhe9ln9ecj50m9dmr4x5558w59js02v9psqncdgd'},
 'terra1mr89dnvp7hcmqfhk54cd3ylfygyfxagfulr0lq5gxcl8pgcywugq46jpl5': {'collection': 'terra12z2273hfx0y5682gfdkm6rmupf3wn5mkgfstla3zazjsgxetkzpql05fm9',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'COFFEE',
                                                                      'reward_token': 'terra19eytmx0yd3m5udlv7rh6u429g6ddjm2cndwv5cxndcymrztx4krqz9p4t6'},
 'terra1n3ycvd7deaaalaarye53lk99cug5ulawrze4zvz4cmjzkc0nm0hs4cv0gz': {'collection': 'terra10u9ukz6g99nf2855wkf0c6a2rzuhrggtyaf53et355dp4jgplx8smnm7xa',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'DO',
                                                                      'reward_token': 'terra15p8su45k45axng8ue59rl6zph4at27s49u3agr6uqrx3dhcxpg3qt0ekdt'},
 'terra1nn73kvzefpeptf6a5kgh9t6ska998hyaa920zwhqq607vepgsk8sfduldc': {'collection': 'terra1vwvugj454ykdqx3sc6cjeyevevpw7lk22pphjgcng4ku0w8ulunq8ghz7k',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'ELON',
                                                                      'reward_token': 'terra13d6xlk4d6cfa6c5c7n2ffua5d5fk5ggfq8vsxr34xnxr07nmke0qajzu8y'},
 'terra1nvpfqv2ecvtxularrave27sneymwd0c2cng2zzftl9sh0p93wf4qyuqvuu': {'collection': 'terra1wdlh784wgrel8pn5jdgujg9cvdch0p2ngvsuxzj8k54vefmng4csvmtp8w',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'GDEX',
                                                                      'reward_token': 'terra16hzl7lge3jjnlazvut2ypt7upk68z5dycc9rwy608fah8q0y3fuslkenzc'},
 'terra1nxz7cqa8zyzejwqqyjnewf709es37tykr6dp9rr2qms98unfsunsaxr7y8': {'collection': 'terra103skwsk84tu2m33erjxt64p54a08p6ckflfwvg',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'GRDX',
                                                                      'reward_token': 'terra12f3f5fzfzxckc0qlv3rmwwkjfhzevpwmx77345n0zuu2678vxf0sm6vvcw'},
 'terra1pw35wjmccnjpfn0a3f3hnf8cy4atc2h0vk8wtf26xtq4gkzvctys97dp5p': {'collection': 'terra13wdhr7nd9xlg96rhuzjmk6yxrjehhzad69n7qpzft97sgd5xupsq4fc85a',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'SMT',
                                                                      'reward_token': 'terra1rc4ef7s6pzuf9pkg8ymnw29pjz2yfm3tjg0kleu4348c2e6upkxqdfdj5u'},
 'terra1q808add8lfk7zsp0ac5yy3gt05x2uk872vm08x7g6g2vgp9yrpuqqlq6dh': {'collection': 'terra10k7j8lyr0kctymz9f49dps3mxa0ggfgu92u3dxddsw4dzxk2nv8q0t9ezd',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'GRDX',
                                                                      'reward_token': 'terra12f3f5fzfzxckc0qlv3rmwwkjfhzevpwmx77345n0zuu2678vxf0sm6vvcw'},
 'terra1qw8ayajd2596e3y3sz8uhtsctgl6ljchzye7jg43ae74mc0ranwqfa6p7c': {'collection': 'terra15hyljcx5c9u4ppyjqlffzrugz6za96lkt25czv2h9y6akga6gmxqnn8zpl',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'DO',
                                                                      'reward_token': 'terra15p8su45k45axng8ue59rl6zph4at27s49u3agr6uqrx3dhcxpg3qt0ekdt'},
 'terra1rrjf8tajqjf65z4r93tdtqaj3nkkcz0wg5ujntnlgpdtyt99jjlste04mg': {'collection': 'terra1ewjlmvlh9an4mj5t47x98vschmnzvxd6c76flg6j5zgdcm32w4mqsh9s4j',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'FRG',
                                                                      'reward_token': 'terra14rfnhc2aru7jp304lht3yf903necsnrt4cxd464cftsfcksw0rtsgundnt'},
 'terra1teqchay4a0s8ac2dq7rt83yfdecp0seruqaagj5c9hj8m395kypskqfjag': {'collection': 'terra19qshtw7fx3yg67prr7n2qdauq30yyftfwa3acy0k6j2sw0hy4dnsee4dpn',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'ORBIT',
                                                                      'reward_token': 'terra1a8rmymsc58p9jg45p8ghy2ueqhmmhsxgd2tvuxma0pxa3g40tw8s0tjg82'},
 'terra1thtsvva822swy4v7azy6m399fpsfq9pvml2hqthvxey3k0q3v7fqdttyyd': {'collection': 'terra14vup8e67z2wqdmmpn5hrmuxhe62v74h7tpfeduzwwkd7msn3wg8sv2368f',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'BOYS',
                                                                      'reward_token': 'terra1a4x7t4w7a5hwqph0q0m5maqu45j99cpkgt82rllvrh4hc6g53k7spulsqj'},
 'terra1tketka9qygj7f9da9cgteyvf4pdr4y5yat2vrtn8yqeha09mz9vstsx2dl': {'collection': 'terra1xhryrhswtaeq6q7dwga4d202clyym49ydqe0dg50lmvtdssgn5hsjzltr8',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'REX',
                                                                      'reward_token': 'terra1pyf0rp73neeyunvelqe2ps029pk3at5xg9sn8hnzvv3pehrjqf2qwx7grv'},
 'terra1tt56e43p8gjzq77hy59v396yk05kd2u05w33p5t3fwtmsngngdsq6m8tuh': {'collection': 'terra1e56ddhtsaggx9l46ag3kkv8tgn2c288gdm2f7xvdtzgph6k95l6qn04xh8',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'BULL',
                                                                      'reward_token': 'terra1sl0cgtanapyy449h0hlmt77s8hak7caktvky8t4ct7a7kvjtyyvqzg8rv6'},
 'terra1ustwrdzganwqpzyuz7sjjfdu3hdltc3yfs38nxkjmm937rmk75yqdee3z5': {'collection': 'terra1rx227e6lzvcd63r5sm244av3spnfega2d0dx8svrzfzg3lgsnq3smlkkdf',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'TeslaX',
                                                                      'reward_token': 'terra1t9gw5njcx009ud2ke7txq92hx5v75arsctzch9nyxv0096987c4q9fwvzy'},
 'terra1uy0sqk9tt9tnd0340jwx2ryrtxu2f8sr5naurk30qc5fcyyhhp2syn47a0': {'collection': 'terra1jhdpyfle4wpy39vyncwmn46jqqnz2stc02egh4ywzf4ss9eupjxq8mj4mv',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'HOTEL',
                                                                      'reward_token': 'terra1ag44q2zgxvpwrhy54t72actkpg6fl3yd65mkn9dzhdn3mya94anqsw6f77'},
 'terra1vrkak47fgzfjnrylj5lqsy7l9nzg3hs4c9uqy6vkwxe60s5cuufqacp4sj': {'collection': 'terra125ptrd44qwlcsd97rzjc0hsjwu5zkm3fypdt6cshgj87cl6rjnfq86mwhf',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'VIMA',
                                                                      'reward_token': 'terra1wsmy4llflw9mc9qfysge5nnmpk5vfcrvc3hevrmaxzlr0qsyvh4q5yuhwd'},
 'terra1vzq8cd60zjan6s4a7qr0gtd7jrxluw96xzhx5j99mwfpmg4tvjsqw4x2hy': {'collection': 'terra16pgk84hcagjqav0um6m3glt3fkwkj4g9270mdqsj4w6lt5k6uwsqylhtuq',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'ALPHA',
                                                                      'reward_token': 'terra1x6e64es6yhauhvs3prvpdg2gkqdtfru840wgnhs935x8axr7zxkqzysuxz'},
 'terra1wqllwd83dj4ldscl4e89uw2hc8hcxt777ezsnwafz2gujf8qveysdud29x': {'collection': 'terra1v823yz492lwd9009dthx9h0cr93l03mpmp3etse78stuahxqnqwslpjnzu',
                                                                      'reward_decimals': 6,
                                                                      'reward_symbol': 'GDEX',
                                                                      'reward_token': 'terra16hzl7lge3jjnlazvut2ypt7upk68z5dycc9rwy608fah8q0y3fuslkenzc'}}

NFT_COLLECTIONS = sorted({v["collection"] for v in NFT_STAKING_CONTRACTS.values()})
NFT_REWARD_TOKENS = sorted({v["reward_token"] for v in NFT_STAKING_CONTRACTS.values()})


# ---------------------------------------------------------------- bech32

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values):
    chk = 1
    gen = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= gen[i]
    return chk


def _bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _convertbits(data, frombits, tobits, pad=True):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or value >> frombits:
            return None
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def valid_terra_address(addr):
    """Strict bech32 validation for a Terra Classic address: 'terra'
    HRP, valid BIP-0173 checksum, and a 20- or 32-byte payload
    (accounts are 20 bytes; contracts 32)."""
    if not isinstance(addr, str):
        return False
    addr = addr.strip()
    if not addr or addr != addr.lower() or len(addr) > 90:
        return False
    pos = addr.rfind("1")
    if pos < 1:
        return False
    hrp, data_part = addr[:pos], addr[pos + 1:]
    if hrp != "terra" or len(data_part) < 6:
        return False
    try:
        data = [_BECH32_CHARSET.index(c) for c in data_part]
    except ValueError:
        return False
    if _bech32_polymod(_bech32_hrp_expand(hrp) + data) != 1:
        return False
    decoded = _convertbits(data[:-6], 5, 8, pad=False)
    if decoded is None or len(decoded) not in (20, 32):
        return False
    return True


# ---------------------------------------------------------------- helpers

def finder_address(addr):
    return f"{FINDER}/address/{addr}"


def fmt_amount(raw, decimals=6):
    """Raw integer string -> human string, trailing zeros trimmed."""
    try:
        value = Decimal(str(raw)) / (Decimal(10) ** int(decimals))
    except Exception:
        return str(raw)
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _int(raw):
    try:
        return int(str(raw))
    except Exception:
        return 0


# ---------------------------------------------------------------- chain IO

class ChainReadError(Exception):
    """Any failed/partial chain read. The sweep treats this as 'skip
    silently, retry next cycle' — never as data."""


class ChainReader:
    """Thin async LCD reader. Every method raises ChainReadError on any
    failure or malformed reply, so a snapshot is only ever built from a
    COMPLETE read. Tests substitute the primitive methods."""

    def __init__(self, client_factory=None):
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=25))
        self._token_info_cache = {}
        self._collection_info_cache = {}
        self._non_enumerable = set()
        self._sem = asyncio.Semaphore(10)

    async def _get_json(self, client, url, params=None):
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except ChainReadError:
            raise
        except Exception as e:
            raise ChainReadError(f"GET {url}: {e}") from e

    async def smart(self, client, contract, msg):
        q = base64.b64encode(
            json.dumps(msg, separators=(",", ":")).encode()).decode()
        data = await self._get_json(
            client, f"{LCD}/cosmwasm/wasm/v1/contract/{contract}/smart/{q}")
        if not isinstance(data, dict) or "data" not in data:
            raise ChainReadError(f"smart query malformed for {contract}")
        return data["data"]

    async def raw_state_value(self, client, contract, namespace, key_suffix):
        """Targeted raw-state read: length-prefixed namespace + raw key
        bytes. Returns the decoded JSON value, or None when the key is
        absent (LCD answers data:null — a clean zero)."""
        ns = namespace.encode()
        raw_key = len(ns).to_bytes(2, "big") + ns + key_suffix.encode()
        encoded = base64.urlsafe_b64encode(raw_key).decode()
        data = await self._get_json(
            client, f"{LCD}/cosmwasm/wasm/v1/contract/{contract}/raw/{encoded}")
        if not isinstance(data, dict) or "data" not in data:
            raise ChainReadError(f"raw read malformed for {contract}")
        blob = data["data"]
        if blob is None or blob == "":
            return None
        try:
            return json.loads(base64.b64decode(blob))
        except Exception as e:
            raise ChainReadError(f"raw value undecodable for {contract}") from e

    async def all_state_models(self, client, contract):
        """Full raw-state scan (paged) — used for the NFT staking
        contracts, whose smart queries are dead on the current code.
        NOTE: the LCD caps this endpoint at 100 models per page no
        matter what limit is requested (verified live 2026-10-29), so
        a big contract legitimately needs 100+ pages; the caps below
        are sized for that, and a runaway scan is a failed read."""
        models = []
        key = None
        for _ in range(2000):
            params = {"pagination.limit": "2000"}
            if key:
                params["pagination.key"] = key
            data = await self._get_json(
                client, f"{LCD}/cosmwasm/wasm/v1/contract/{contract}/state",
                params=params)
            if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                raise ChainReadError(f"state scan malformed for {contract}")
            models.extend(data["models"])
            if len(models) > 200_000:
                raise ChainReadError(f"state scan exceeded model cap for {contract}")
            key = (data.get("pagination") or {}).get("next_key")
            if not key:
                return models
        raise ChainReadError(f"state scan exceeded page cap for {contract}")

    async def bank_balances(self, client, address):
        out = {}
        key = None
        for _ in range(10):
            params = {"pagination.limit": "200"}
            if key:
                params["pagination.key"] = key
            data = await self._get_json(
                client, f"{LCD}/cosmos/bank/v1beta1/balances/{address}",
                params=params)
            if not isinstance(data, dict) or not isinstance(data.get("balances"), list):
                raise ChainReadError("bank balances malformed")
            for coin in data["balances"]:
                if coin.get("denom") in ("uluna", "uusd"):
                    out[coin["denom"]] = str(coin.get("amount", "0"))
            key = (data.get("pagination") or {}).get("next_key")
            if not key:
                return {"uluna": out.get("uluna", "0"), "uusd": out.get("uusd", "0")}
        raise ChainReadError("bank balances exceeded page cap")

    async def token_info(self, client, token):
        if token in self._token_info_cache:
            return self._token_info_cache[token]
        info = await self.smart(client, token, {"token_info": {}})
        if not isinstance(info, dict) or "symbol" not in info:
            raise ChainReadError(f"token_info malformed for {token}")
        info = {"symbol": str(info["symbol"]),
                "decimals": int(info.get("decimals", 6)),
                "name": str(info.get("name", info["symbol"]))}
        self._token_info_cache[token] = info
        return info

    async def cw20_balance(self, client, token, address):
        data = await self.smart(client, token, {"balance": {"address": address}})
        if not isinstance(data, dict) or "balance" not in data:
            raise ChainReadError(f"cw20 balance malformed for {token}")
        return str(data["balance"])

    async def collection_name(self, client, collection):
        if collection in self._collection_info_cache:
            return self._collection_info_cache[collection]
        try:
            info = await self.smart(client, collection, {"contract_info": {}})
            name = str(info.get("name") or collection) if isinstance(info, dict) else collection
        except ChainReadError:
            name = collection  # a label lookup must never fail a sweep
        self._collection_info_cache[collection] = name
        return name

    async def cw721_tokens_of(self, client, collection, owner):
        """All token ids of `owner` in one CW721 collection (paged).
        Returns None when the collection permanently cannot enumerate
        (recorded in _non_enumerable); raises ChainReadError on any
        transient/unknown failure."""
        if collection in self._non_enumerable:
            return None
        ids = []
        start_after = None
        for _ in range(100):
            msg = {"tokens": {"owner": owner, "limit": 100}}
            if start_after is not None:
                msg["tokens"]["start_after"] = start_after
            try:
                data = await self.smart(client, collection, msg)
            except ChainReadError as e:
                text = str(e).lower()
                if "not supported" in text or "unknown variant" in text \
                        or "error parsing" in text:
                    self._non_enumerable.add(collection)
                    return None
                raise
            if not isinstance(data, dict) or not isinstance(data.get("tokens"), list):
                raise ChainReadError(f"cw721 tokens malformed for {collection}")
            page = [str(t) for t in data["tokens"]]
            ids.extend(page)
            if len(page) < 100:
                return ids
            start_after = page[-1]
        raise ChainReadError(f"cw721 enumeration exceeded page cap for {collection}")


# ------------------------------------------------------- universe building

async def build_token_universe(reader, client):
    """The Garuda CW20 universe for this sweep (see module docstring).
    Returns (tokens:set, regular_pools, cross_pools); pools are lists of
    {"token", "staking"} dicts. Raises ChainReadError if the staking
    factories themselves cannot be read completely."""
    tokens = set(NFT_REWARD_TOKENS)

    regular = await reader.smart(client, garuda.REGULAR_STAKING_FACTORY,
                                 {"registered_token": {}})
    if not isinstance(regular, dict) or not isinstance(regular.get("tokens"), list):
        raise ChainReadError("regular factory registered_token malformed")
    regular_pools = []
    for entry in regular["tokens"]:
        token, staking = entry.get("token_address"), entry.get("staking_address")
        if not token or not staking:
            raise ChainReadError("regular factory entry malformed")
        tokens.add(token)
        regular_pools.append({"token": token, "staking": staking})

    cross_addrs = []
    offset = 0
    for _ in range(20):
        data = await reader.smart(client, garuda.CROSS_STAKING_FACTORY,
                                  {"registered_token": {"offset": offset}})
        if not isinstance(data, dict) or not isinstance(data.get("staking_addresses"), list):
            raise ChainReadError("cross factory registered_token malformed")
        page = data["staking_addresses"]
        cross_addrs.extend(page)
        if len(page) < 10:
            break
        offset += len(page)
    else:
        raise ChainReadError("cross factory listing exceeded page cap")
    cross_pools = []
    for staking in sorted(set(cross_addrs)):
        cfg = await reader.smart(client, staking, {"config": {}})
        token = cfg.get("token_address") if isinstance(cfg, dict) else None
        if not token:
            raise ChainReadError(f"cross config malformed for {staking}")
        tokens.add(token)
        cross_pools.append({"token": token, "staking": staking})
        rewards = await reader.smart(client, staking, {"rewards": {}})
        reward_list = rewards.get("rewards", []) if isinstance(rewards, dict) else []
        for reward in reward_list:
            denom = (reward or {}).get("denom") or {}
            if denom.get("cw20"):
                tokens.add(denom["cw20"])

    try:
        pairs = await reader.smart(client, garuda.DEX_PAIR_FACTORY,
                                   {"pairs": {"limit": 100}})
        pair_list = pairs.get("pairs", []) if isinstance(pairs, dict) else []
        for pair in pair_list:
            for info in pair.get("asset_infos", []) or []:
                token = (info.get("token") or {}).get("contract_addr")
                if token:
                    tokens.add(token)
            if pair.get("liquidity_token"):
                tokens.add(pair["liquidity_token"])
    except ChainReadError:
        pass  # DEX pairs only widen the universe; the staking-derived
        # set above is complete on its own, so a pairs failure narrows
        # coverage for one cycle rather than failing every wallet.

    return tokens, regular_pools, cross_pools


async def scan_nft_staking(reader, client):
    """One shared raw-state scan of all 35 NFT staking contracts.
    Returns {wallet: {"staked": [entry], "releasing": [entry]}} where
    entry = {"collection":..., "token_id":...}. Raises ChainReadError
    if any contract cannot be scanned completely."""
    by_wallet = {}
    sem = asyncio.Semaphore(6)

    async def one_contract(staking):
        async with sem:
            return staking, await reader.all_state_models(client, staking)

    scanned = await asyncio.gather(
        *(one_contract(s) for s in NFT_STAKING_CONTRACTS), return_exceptions=True)
    for entry in scanned:
        if isinstance(entry, Exception):
            raise ChainReadError(f"NFT staking scan failed: {entry}")
        staking, models = entry
        meta = NFT_STAKING_CONTRACTS[staking]
        for model in models:
            try:
                key = bytes.fromhex(model["key"])
            except Exception:
                continue
            if len(key) < 2:
                continue
            ns_len = int.from_bytes(key[:2], "big")
            namespace = key[2:2 + ns_len].decode("utf-8", "ignore")
            if namespace not in ("STAKED_NFT", "UNSTAKED_NFT"):
                continue
            try:
                value = json.loads(base64.b64decode(model["value"]))
            except Exception:
                continue
            staker = value.get("staker")
            token_id = value.get("token_id")
            if not staker or token_id is None:
                continue
            bucket = "staked" if namespace == "STAKED_NFT" else "releasing"
            by_wallet.setdefault(staker, {"staked": [], "releasing": []})[bucket].append(
                {"collection": meta["collection"], "token_id": str(token_id)})
    return by_wallet


# ---------------------------------------------------------------- snapshot

async def build_snapshot(reader, client, address, universe=None, nft_staking=None):
    """A COMPLETE snapshot of one wallet, or ChainReadError. Nothing
    partial is ever returned."""
    tokens, regular_pools, cross_pools = universe

    bank = await reader.bank_balances(client, address)

    async def one_balance(token):
        async with reader._sem:
            return token, await reader.cw20_balance(client, token, address)

    results = await asyncio.gather(
        *(one_balance(t) for t in sorted(tokens)), return_exceptions=True)
    cw20 = {}
    for result in results:
        if isinstance(result, Exception):
            raise ChainReadError(f"cw20 balance read failed: {result}")
        token, amount = result
        if _int(amount):
            cw20[token] = amount

    async def one_stake(kind, namespace, pool):
        async with reader._sem:
            value = await reader.raw_state_value(client, pool["staking"], namespace, address)
        amount = "0" if value is None else str(value.get("amount", "0"))
        return f"{kind}:{pool['staking']}", amount

    stake_results = await asyncio.gather(
        *(one_stake("regular", "STAKING", p) for p in regular_pools),
        *(one_stake("cross", "STAKED_ASSETS", p) for p in cross_pools),
        return_exceptions=True)
    stakes = {}
    for result in stake_results:
        if isinstance(result, Exception):
            raise ChainReadError(f"stake read failed: {result}")
        key, amount = result
        if _int(amount):
            stakes[key] = amount

    async def one_collection(collection):
        async with reader._sem:
            return collection, await reader.cw721_tokens_of(client, collection, address)

    held = []
    held_results = await asyncio.gather(
        *(one_collection(c) for c in NFT_COLLECTIONS), return_exceptions=True)
    for result in held_results:
        if isinstance(result, Exception):
            raise ChainReadError(f"NFT holdings read failed: {result}")
        collection, ids = result
        if ids is None:
            continue  # permanently non-enumerable collection (documented)
        held.extend(f"{collection}|{tid}" for tid in ids)
    mine = (nft_staking or {}).get(address, {"staked": [], "releasing": []})
    staked = sorted({f"{e['collection']}|{e['token_id']}" for e in mine["staked"]})
    releasing = sorted({f"{e['collection']}|{e['token_id']}" for e in mine["releasing"]})

    return {
        "bank": bank,
        "cw20": cw20,
        "stakes": stakes,
        "nfts": {"held": sorted(set(held)), "staked": staked, "releasing": releasing},
    }


def diff_snapshots(old, new):
    """Structured changes between two snapshots. Pure function."""
    changes = {"bank": [], "cw20": [], "stakes": [], "nfts": []}
    for denom in ("uluna", "uusd"):
        before = _int(old["bank"].get(denom, "0"))
        after = _int(new["bank"].get(denom, "0"))
        if before != after:
            changes["bank"].append(
                {"denom": denom, "before": before, "after": after, "delta": after - before})
    for token in sorted(set(old["cw20"]) | set(new["cw20"])):
        before = _int(old["cw20"].get(token, "0"))
        after = _int(new["cw20"].get(token, "0"))
        if before != after:
            changes["cw20"].append(
                {"token": token, "before": before, "after": after, "delta": after - before})
    for pool in sorted(set(old["stakes"]) | set(new["stakes"])):
        before = _int(old["stakes"].get(pool, "0"))
        after = _int(new["stakes"].get(pool, "0"))
        if before != after:
            changes["stakes"].append(
                {"pool": pool, "before": before, "after": after, "delta": after - before})
    for bucket in ("held", "staked", "releasing"):
        before = set(old["nfts"].get(bucket, []))
        after = set(new["nfts"].get(bucket, []))
        for item in sorted(after - before):
            changes["nfts"].append({"bucket": bucket, "direction": "in", "item": item})
        for item in sorted(before - after):
            changes["nfts"].append({"bucket": bucket, "direction": "out", "item": item})
    return changes


def has_changes(changes):
    return any(changes[k] for k in changes)


def changes_hash(address, changes):
    return hashlib.sha256(
        json.dumps({"a": address, "c": changes}, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------- alert text

_BANK_LABELS = {"uluna": "LUNC", "uusd": "USTC"}


async def format_alert(reader, client, address, changes, pool_tokens,
                       detected_on_return=False):
    """Plain-text alert (no Markdown). Full clickable Finder links."""
    lines = ["🔐 Wallet Security alert"]
    if detected_on_return:
        lines.append("Detected when protection resumed — this changed while Wallet Security was offline.")
    lines.append(f"Wallet: {address}")
    lines.append(f"View on Finder: {finder_address(address)}")
    lines.append("What changed:")

    body = []
    for change in changes["bank"]:
        label = _BANK_LABELS[change["denom"]]
        verb = "increased" if change["delta"] > 0 else "decreased"
        body.append(
            f"• {label} balance {verb} by {fmt_amount(abs(change['delta']))} {label} "
            f"(was {fmt_amount(change['before'])}, now {fmt_amount(change['after'])}).")
    for change in changes["cw20"]:
        info = await reader.token_info(client, change["token"])
        verb = "increased" if change["delta"] > 0 else "decreased"
        body.append(
            f"• {info['symbol']} balance {verb} by {fmt_amount(abs(change['delta']), info['decimals'])} "
            f"{info['symbol']} (was {fmt_amount(change['before'], info['decimals'])}, "
            f"now {fmt_amount(change['after'], info['decimals'])}). Token: {finder_address(change['token'])}")
    for change in changes["stakes"]:
        kind, staking = change["pool"].split(":", 1)
        token = pool_tokens.get(staking)
        symbol, decimals = "tokens", 6
        if token:
            info = await reader.token_info(client, token)
            symbol, decimals = info["symbol"], info["decimals"]
        kind_label = "regular staking" if kind == "regular" else "cross-staking"
        verb = "increased" if change["delta"] > 0 else "decreased"
        body.append(
            f"• Stake {verb} in the {symbol} {kind_label} pool by "
            f"{fmt_amount(abs(change['delta']), decimals)} {symbol} "
            f"(was {fmt_amount(change['before'], decimals)}, now {fmt_amount(change['after'], decimals)}). "
            f"Pool: {finder_address(staking)}")
    for change in changes["nfts"]:
        collection, token_id = change["item"].rsplit("|", 1)
        name = await reader.collection_name(client, collection)
        if change["bucket"] == "held":
            verb = "arrived in your wallet" if change["direction"] == "in" else "left your wallet"
        elif change["bucket"] == "staked":
            verb = "was staked (NFT staking)" if change["direction"] == "in" else "left NFT staking"
        else:
            verb = "entered the unstaking release period" if change["direction"] == "in" \
                else "finished the unstaking release period"
        body.append(
            f"• NFT #{token_id} ({name}) {verb}. Collection: {finder_address(collection)}")

    cap = 25
    lines.extend(body[:cap])
    if len(body) > cap:
        lines.append(f"• …and {len(body) - cap} more changes — check the wallet on Finder.")
    lines.append("If you did not make these changes, treat this wallet as at risk: move funds to a fresh wallet from a clean device, and never share your seed phrase with anyone.")
    return "\n".join(lines)


# ------------------------------------------------------------ sweep engine

async def run_sweep(send_dm, owner_alert=None, reader=None, now=None,
                    detected_on_return=False):
    """One full checker sweep over every registered watch.

    send_dm(user_id, text) — async callable; Wallet Security change
    alerts only ever go to the registering user's own DM.
    owner_alert(text) — async callable for OWNER health alerts (or None).

    A wallet whose read fails keeps its old snapshot and alerts
    nothing; the sweep then counts as failed/partial. Health state
    (consecutive failures, last success) is persisted via
    store.ws_meta_* so it survives restarts."""
    now = int(now if now is not None else time.time())
    reader = reader or ChainReader()
    watches = store.wallet_watches_all()
    result = {"watches": len(watches), "checked": 0, "alerts": 0,
              "failed_wallets": 0, "success": False}

    try:
        async with reader._client_factory() as client:
            universe = await build_token_universe(reader, client)
            nft_staking = await scan_nft_staking(reader, client)
            pool_tokens = {p["staking"]: p["token"] for p in universe[1] + universe[2]}
            for watch in watches:
                try:
                    snapshot = await build_snapshot(
                        reader, client, watch["address"], universe, nft_staking)
                except ChainReadError:
                    result["failed_wallets"] += 1
                    continue
                result["checked"] += 1
                store.wallet_watch_touch(watch["user_id"], watch["address"], now)
                old = watch.get("snapshot")
                if old is None:
                    store.wallet_watch_set_snapshot(
                        watch["user_id"], watch["address"], snapshot)
                    continue
                changes = diff_snapshots(old, snapshot)
                if not has_changes(changes):
                    store.wallet_watch_set_snapshot(
                        watch["user_id"], watch["address"], snapshot)
                    continue
                digest = changes_hash(watch["address"], changes)
                if watch.get("alerts_on", 1) and digest != watch.get("last_alert_hash"):
                    text = await format_alert(
                        reader, client, watch["address"], changes, pool_tokens,
                        detected_on_return=detected_on_return)
                    await send_dm(watch["user_id"], text)
                    store.wallet_watch_set_alert_hash(
                        watch["user_id"], watch["address"], digest)
                    result["alerts"] += 1
                store.wallet_watch_set_snapshot(
                    watch["user_id"], watch["address"], snapshot)
    except ChainReadError:
        result["failed_wallets"] += 1
    except Exception:
        result["failed_wallets"] += 1

    if result["failed_wallets"] == 0 and result["checked"] == result["watches"]:
        result["success"] = True
        store.ws_meta_set("last_sweep_ok_ts", str(now))
        store.ws_meta_set("consecutive_failures", "0")
        store.ws_meta_set("failure_alert_sent", "0")
        store.ws_meta_set("watchdog_alert_sent", "0")
    else:
        failures = int(store.ws_meta_get("consecutive_failures", "0") or 0) + 1
        store.ws_meta_set("consecutive_failures", str(failures))
        if failures >= FAILURE_ALERT_THRESHOLD \
                and store.ws_meta_get("failure_alert_sent", "0") != "1":
            store.ws_meta_set("failure_alert_sent", "1")
            if owner_alert is not None:
                await owner_alert(
                    "⚠️ Wallet Security health alert: the last "
                    f"{failures} wallet sweeps failed or were partial, so member wallets may "
                    "not be getting change alerts right now. The checker keeps retrying every "
                    "~15 minutes. (Members are not sent health noise — change alerts only.)")
    return result


async def watchdog_check(owner_alert, now=None):
    """Missed-sweep watchdog: returns True (and sends one owner DM per
    episode) when no successful sweep has completed within 2x the sweep
    interval. A fresh install gets one stale-window of grace from the
    first watchdog run (armed timestamp), so a brand-new deploy does
    not page the owner before its first sweep can run."""
    now = int(now if now is not None else time.time())
    last_ok = store.ws_meta_get("last_sweep_ok_ts")
    if last_ok is None:
        if store.ws_meta_get("watchdog_armed_ts") is None:
            store.ws_meta_set("watchdog_armed_ts", str(now))
            return False
        last_ok = store.ws_meta_get("watchdog_armed_ts")
    if now - int(last_ok) <= WATCHDOG_STALE_SECONDS:
        return False
    if store.ws_meta_get("watchdog_alert_sent", "0") == "1":
        return False
    store.ws_meta_set("watchdog_alert_sent", "1")
    if owner_alert is not None:
        minutes = (now - int(last_ok)) // 60
        await owner_alert(
            "⚠️ Wallet Security health alert: no successful wallet sweep has completed for "
            f"about {minutes} minutes (the limit is {WATCHDOG_STALE_SECONDS // 60}). "
            "Member wallets are not being checked right now. The bot keeps retrying; "
            "if this repeats, check the Railway service and the chain LCD.")
    return True


# ------------------------------------------------------- downtime notices

def watcher_user_ids():
    """Distinct Telegram user ids with at least one registered watch —
    the only people downtime notices go to."""
    return sorted({w["user_id"] for w in store.wallet_watches_all()})


async def send_downtime_notices(send_dm):
    """Graceful-shutdown fanout (best effort): every watcher is told
    their wallet is temporarily unprotected during a security update."""
    sent = 0
    for user_id in watcher_user_ids():
        try:
            await send_dm(user_id, DOWN_NOTICE)
            sent += 1
        except Exception:
            pass  # best effort by design — shutdown must not hang
    return sent


async def send_resume_notices(send_dm, now=None, last_ok_before_boot=None):
    """Startup fanout after the first successful sweep: protection is
    back. When the pre-boot last-success timestamp shows a real gap,
    the offline window is named."""
    now = int(now if now is not None else time.time())
    text = BACK_NOTICE
    if last_ok_before_boot:
        gap = now - int(last_ok_before_boot)
        if gap > SWEEP_INTERVAL_SECONDS:
            if gap >= 3600:
                window = f"about {gap // 3600} hour{'s' if gap >= 7200 else ''}"
            else:
                window = f"about {max(1, gap // 60)} minutes"
            text += (f" Protection was paused for {window}. "
                     "Anything that changed in that window has been checked against your last known state.")
    sent = 0
    for user_id in watcher_user_ids():
        try:
            await send_dm(user_id, text)
            sent += 1
        except Exception:
            pass
    return sent
