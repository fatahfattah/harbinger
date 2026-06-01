import os
from signals.interface import SignalDef, ARCH_DIMS_ORDERED

# -- Config values (defined before signal imports to avoid circular deps) --

# Ticker universe
SEED_TICKERS = [
    "ASTS", "NBIS", "MU",
    "RKLB", "LUNR", "PLTR", "SOFI", "IONQ", "RXRX",
    "ARM", "CRSP", "BE", "UPST", "AFRM",
    "TEAM", "DDOG", "MDB", "NET", "ZS", "SNOW", "PATH",
    "ALGM", "SITM", "ACLS",
    "RNA", "NTRA", "ALKS",
    "RDW", "GSAT",
    "AMD", "MRVL", "WOLF", "ON", "STM",
    "AMAT", "LRCX", "KLAC", "ENTG",
]

MCAP_MIN = 100_000_000
MCAP_MAX = 50_000_000_000
PRICE_MIN = 2.0

# — Valuation thresholds —
FWD_PE_MAX = 15
REV_GROWTH_MIN = 10
MAX_DEEP_DIVE = 100
VAL_WORKERS = 8
INFO_TIMEOUT = 20

# — Insider —
INSIDER_DAYS_BACK = 90
INSIDER_WORKERS = 6
MAX_FILINGS_PER_TICKER = 3

# — Social —
SOCIAL_DAYS_BACK = 7
SOCIAL_MIN_MENTIONS = 1.5
SOCIAL_WORKERS = 6

# — Niche / Early Signal —
NICHE_DAYS_BACK = 14
NICHE_MIN_MENTIONS = 0.5

# — Technicals —
MOMENTUM_WORKERS = 12
TECH_52WK_HIGH_WEIGHT = 2.0

# — Short Interest —
SHORT_INTEREST_WORKERS = 8
SHORT_PCT_MAX = 1.0
SHORT_PCT_SCALE = 8.0

# — 13F —
NOTABLE_FUNDS = {
    "0001037389": "Renaissance Technologies",
    "0001061761": "Citadel Advisors",
    "0001273878": "D. E. Shaw",
    "0001649339": "Susquehanna International",
    "0001103808": "Jane Street Capital",
    "0001089112": "Millennium Management",
    "0001166558": "Coatue Management",
    "0001423054": "Tiger Global Management",
    "0001007560": "Point72 Asset Management",
    "0001533618": "Two Sigma Investments",
    "0001855477": "Scion Asset Management",
    "0001707329": "ARK Investment Management",
    "0001214813": "Viking Global Investors",
    "0001002362": "Lone Pine Capital",
    "0001047645": "Third Point",
    "0001336528": "Pershing Square Capital",
    "0001232119": "Baupost Group",
    "0001000166": "Greenlight Capital",
    "0001297296": "ValueAct Capital",
    "0001371303": "Starboard Value",
    "0001002616": "Elliott Management",
    "0001171263": "Soros Fund Management",
    "0001076930": "Alkeon Capital Management",
    "0001736018": "Whale Rock Capital Management",
    "0001821174": "D1 Capital Partners",
    "0001104149": "Sachem Head Capital",
    "0001087867": "Glenview Capital",
    "0001179771": "Canyon Capital Advisors",
    "0001162774": "Senvest Management",
    "0001175103": "Abrams Capital Management",
    "0001431615": "Adage Capital Management",
    "0001489128": "Orbis Investment Management",
    "0001413505": "Maverick Capital",

    # Additional verified 13F filers (covers small/mid-cap overlap)
    "0000102909": "Vanguard Group",
    "0000315066": "FMR LLC (Fidelity)",

    # Small-cap specialists (verified via SEC EDGAR)
    "0000906304": "Royce & Associates",
    "0000814133": "Wasatch Advisors",
    "0000937394": "Heartland Advisors",
    "0000807249": "GAMCO Investors (Gabelli)",
    "0000354204": "Dimensional Fund Advisors",
    "0000080255": "T. Rowe Price Associates",
    "0001364742": "BlackRock Inc.",
}

# — Earnings —
EARNINGS_DAYS_BACK = 365
EARNINGS_WORKERS = 8

# — Pipeline —
MAX_SEC_TICKERS = 120

# — Scoring —
CONVERGENCE_BOOST_MAX = 2.0
CONVERGENCE_BOOST_PER_SIGNAL = 0.5
SECTOR_MOMENTUM_BOOST_MAX = 2.0
REGIME_SWITCH_WINDOW_DAYS = 7

# — LLM —
LLM_API = os.environ.get("HARBINGER_LLM_API", "http://127.0.0.1:4096")
LLM_ENABLED = os.environ.get("HARBINGER_LLM_ENABLED", "1") == "1"

# — Output —
TOP_N = 15
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "runs")

# — Dead ticker cache —
DEAD_TICKER_TTL_DAYS = 7

# -- Signal module imports (after config values, so they can import config) --

import signals.technicals as _tech
import signals.niche_topics as _nic
import signals.valuation as _val
import signals.social as _soc
import signals.catalysts as _cat
import signals.insider as _ins
import signals.fund_13f as _f13f
import signals.short_interest as _si
import signals.earnings as _earn
import signals.financial_health as _fh
import signals.analyst_targets as _an
import signals.institutional as _inst
import signals.dividend_quality as _div
import signals.seasonality as _sea
import signals.macro_exposure as _mac

SIGNALS: list[SignalDef] = [
    SignalDef("valuation", 1, _val.screen, 0.12),
    SignalDef("social", 1, _soc.fetch, 0.04),
    SignalDef("catalyst", 1, _cat.fetch, 0.04),
    SignalDef("technicals", 1, _tech.fetch, 0.10),
    SignalDef("earnings", 1, _earn.fetch, 0.06),
    SignalDef("insider", 2, _ins.fetch, 0.14),
    SignalDef("fund_13f", 2, _f13f.fetch, 0.05),
    SignalDef("niche", 2, _nic.fetch, 0.05),
    SignalDef("short_interest", 2, _si.fetch, 0.04),
    SignalDef("financial_health", 2, _fh.fetch, 0.05),
    SignalDef("analyst_targets", 2, _an.fetch, 0.06),
    SignalDef("institutional", 2, _inst.fetch, 0.06),
    SignalDef("dividend_quality", 2, _div.fetch, 0.05),
    SignalDef("seasonality", 2, _sea.fetch, 0.06),
    SignalDef("macro_exposure", 2, _mac.fetch, 0.08),
]

WEIGHTS = {s.name: s.weight for s in SIGNALS}
assert abs(sum(WEIGHTS.values()) - 1.0) < 0.01, f"weights sum to {sum(WEIGHTS.values())}"
