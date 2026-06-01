MU_ARCHETYPE = """MU (Micron Technology)
  Sector: Semiconductor / Memory (HBM)
  Setup: Cyclical value + AI demand thesis
  Key metrics: forward P/E ~5.7x, 20%+ revenue growth, ~$90B market cap
  Catalysts: Multi-year HBM3e contracts with NVIDIA, sold out through 2026
  Signals: Insider buying by officers, Reddit volume acceleration,
    hedge fund 13F accumulation (Renaissance, Citadel, Two Sigma),
    low forward P/E despite accelerating revenue
  Pattern: Market priced MU as cyclical peak, but HBM demand was structural.
    The forward P/E was pricing in a downturn that never materialized.
    This is one possible pattern — many similar setups fail."""

NBIS_ARCHETYPE = """NBIS (Nebius Group)
  Sector: AI Cloud Infrastructure
  Setup: Post-sanctions restructuring carve-out (ex-Yandex N.V.)
  Key metrics: Low institutional coverage, Dutch-domiciled entity
  Catalysts: Yandex carve-out completed, management-led restructuring,
    AI infrastructure capacity buildout, first institutional contracts
  Signals: Obscure entity structure meant low retail awareness,
    early institutional accumulation post-restructuring,
    independent analysts first to identify the story
  Pattern: The carve-out created an information vacuum. Low coverage
    means any new information can move the stock sharply in either direction.
    Information vacuums are as dangerous as they are opportunity-rich."""

ASTS_ARCHETYPE = """ASTS (AST SpaceMobile)
  Sector: Satellite-to-Cellular Telecommunications
  Setup: Pre-revenue binary catalyst
  Key metrics: Pre-revenue, SPAC heritage
  Catalysts: First commercial satellite deployment, direct-to-cell spectrum deals,
    regulatory approvals (FCC, international), carrier partnership agreements
  Signals: Insider buying by founder/CEO Abel Avellan,
    hedge fund 13F new positions,
    niche Reddit community (r/ASTSpaceMobile) with high-signal DD
  Pattern: A binary bet on satellite-to-cell technology.
    Pre-revenue companies either succeed massively or go to zero.
    The asymmetry works both ways — absence of revenue means no margin of safety."""

# Numerical signal profiles for archetype matching (0-10 per dimension)
# These represent each stock's signal fingerprint BEFORE their explosion
# Numerical signal profiles for archetype matching (0-10 per dimension)
# These represent the signal fingerprint these stocks would show
# when run through harbinger's actual signal pipeline
ARCHEYTPE_PROFILES = {
    "MU-like": {
        "valuation": 7, "insider": 6, "fund_13f": 7, "social": 4, "catalyst": 6, "technicals": 5, "niche": 5, "short_interest": 3,
        "earnings": 6, "financial_health": 6, "analyst_targets": 6,
        "sector": "Semiconductor",
        "description": "Value + Catalyst — low P/E with structural AI demand",
    },
    "NBIS-like": {
        "valuation": 1, "insider": 3, "fund_13f": 4, "social": 7, "catalyst": 7, "technicals": 8, "niche": 8, "short_interest": 4,
        "earnings": 1, "financial_health": 4, "analyst_targets": 2,
        "sector": "AI Infrastructure",
        "description": "Post-Restructuring — information vacuum before discovery",
    },
    "ASTS-like": {
        "valuation": 3, "insider": 4, "fund_13f": 6, "social": 8, "catalyst": 6, "technicals": 3, "niche": 9, "short_interest": 6,
        "earnings": 0, "financial_health": 3, "analyst_targets": 3,
        "sector": "Satellite Communications",
        "description": "Pre-Revenue Conviction — binary catalyst with insider conviction",
    },
}

LLM_SYSTEM_PROMPT = """You are a forensic stock signal analyst. Your job is to identify weaknesses in bullish narratives, not to hype stocks. You have seen thousands of signal scans that lead nowhere. Be skeptical.

ARCHETYPE REFERENCE — These are patterns that HAVE WORKED BEFORE. Most similar setups fail. Use them to spot what COULD go right, but default to skepticism.

--- MU Archetype: "Value + Catalyst" ---
{MU}
A stock that screens as "MU-like" when:
- Low forward P/E (<15x) combined with 15%+ revenue growth
- Insider buying is present
- Hedge funds are accumulating
- A tangible near-term catalyst exists (product cycle, supply deal)

--- NBIS Archetype: "Post-Restructuring" ---
{NBIS}
A stock that screens as "NBIS-like" when:
- Recent corporate restructuring, spinoff, or carve-out
- Operates in a high-demand sector (AI infra, cloud, HPC)
- Low analyst/institutional coverage
- Information vacuum
- Early revenue or contract wins post-restructuring

--- ASTS Archetype: "Pre-Revenue" ---
{ASTS}
A stock that screens as "ASTS-like" when:
- Pre-revenue or early-revenue with a clear binary catalyst
- High insider ownership and/or insider buying
- Notable hedge fund 13F new positions
- Niche but passionate investor community
- Next catalyst is identifiable (regulatory decision, product launch, trial readout)

Short Interest: High short interest is often a warning sign of fundamental problems,
  not a squeeze setup. Treat it as a red flag unless accompanied by improving fundamentals.

Sector Momentum: Tracks aggregate technical scores to detect sector rotation.
  Can create false positives — a rising tide lifts all boats temporarily.

--- Novel ---
Does not fit any known archetype. These are the hardest to evaluate — most are noise.

INSTRUCTIONS:
For each candidate, produce EXACTLY ONE LINE:
**TICKER** — **ARCHETYPE** (brief rationale). Concern: one specific risk. **CONFIDENCE**

If Novel, explain why it might be different in 1 sentence.

Confidence levels: HIGH / MEDIUM / LOW
  HIGH  = multiple confirming signals, clear archetype match, identifiable risk
  MEDIUM = partial match, insufficient data, or risks unclear
  LOW  = weak or conflicting signals, likely noise

CRITICAL RULES:
- Social media mentions (Reddit, niche) are the WEAKEST signal. Assume Reddit activity is noise unless corroborated by hard data (insider trades, SEC filings, financials).
- High short interest is a CONCERN, not a squeeze opportunity.
- High technical scores (momentum, RSI) mean the stock ALREADY MOVED — the easy money is gone.
- If the only positive signals are social/niche/technicals, flag it as weak.
- If the ticker has earnings data, penalize revenue declines, negative surprises, or low beat rates.
- Be direct. No fluff. No hedging. No hype."""
