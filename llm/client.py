import json
import requests
from .patterns import LLM_SYSTEM_PROMPT, MU_ARCHETYPE, NBIS_ARCHETYPE, ASTS_ARCHETYPE


DEEP_DIVE_PROMPT = """You are a forensic stock analyst who defaults to skepticism. Your job is to stress-test the bullish case, not build one.

TICKER: {ticker}
PRICE: ${price}
SECTOR: {sector}

SIGNAL DATA:
{signal_data}

{sec_filings_section}

Analyze critically:

1. **Company Snapshot** (1-2 sentences — what do they actually do?)
2. **What Could Go Right** — be specific but measured
3. **What Could Go Wrong** — be exhaustive. List at least 3 risks.
4. **Signal Critique** — which signals are real vs noise? Social/niche mentions are the weakest signal. Technical momentum means it already moved. Earnings data (if available) is the hardest signal.
5. **Key Unknowns** — what information would change your view?
6. **Verdict** — choose one: Buy / Speculative / Hold / Pass with a one-sentence reason.

Rules:
- 3 Reddit posts are not a thesis. Social signals are near-worthless without hard data.
- If the company is unprofitable or pre-revenue, flag this as a major risk.
- If the score is driven by technicals (momentum), note that the easy money has been made.
- Be specific. "Strong management" is not analysis. Cite actual insider behavior.
- Do NOT recommend buying without identifying what specifically needs to go right and what the downside is."""


CROSS_VALIDATE_PROMPT = """You are a forensic stock analyst performing cross-validation on a set of top scan picks. Your job is to detect signal contradictions and risk patterns. Be skeptical.

TOP PICKS (scored by 11 signals: valuation, insider, 13F, social, catalyst, technicals, niche, short_interest, earnings, financial_health, analyst_targets):

{picks_text}

Analyze these picks as a PORTFOLIO:

1. **Signal Contradictions** — list any picks where signals strongly disagree (e.g., insider buying but weak earnings, high social buzz but weak FH, cheap valuation but declining revenue). Format as `TICKER: contradiction description`.

2. **Risk Patterns Detected** — flag any of these patterns:
   - Value Trap: low PE + declining revenue + insider selling
   - Momentum Trap: already up 50%+ in 3m with no new catalyst
   - Short Squeeze Setup: high SI + catalysts + insider buying (genuine squeeze potential)
   - Overbought: RSI > 70 near 52w high
   - Financially Weak: low FH score + unprofitable + high debt
   - Hype Without Substance: high social/niche score but weak fundamentals

3. **Convergence Picks** — tops picks where most signals agree. List up to 3.

4. **Portfolio Verdict** — one sentence: is this set of picks dominated by genuine fundamental signals or by momentum/noise? What's the biggest risk across the portfolio?"""


class HarbingerLLM:
    def __init__(self, api_url):
        self.api_url = api_url.rstrip("/")
        self.session_id = None

    def _ensure_session(self):
        if not self.session_id:
            resp = requests.post(
                f"{self.api_url}/session",
                json={"title": "harbinger scan"},
                timeout=10,
            )
            self.session_id = resp.json().get("id")

    def _send_prompt(self, prompt, timeout=180):
        self._ensure_session()
        resp = requests.post(
            f"{self.api_url}/session/{self.session_id}/message",
            json={"parts": [{"type": "text", "text": prompt}]},
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            texts = [p["text"] for p in data.get("parts", []) if p.get("type") == "text"]
            return "\n".join(texts)
        return f"[LLM error: {resp.status_code}]"

    def health(self):
        try:
            resp = requests.get(f"{self.api_url}/global/health", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def analyze(self, candidates_text):
        prompt = LLM_SYSTEM_PROMPT.format(
            MU=MU_ARCHETYPE,
            NBIS=NBIS_ARCHETYPE,
            ASTS=ASTS_ARCHETYPE,
        )
        prompt += "\n\nCANDIDATES:\n" + candidates_text
        try:
            return self._send_prompt(prompt)
        except requests.RequestException as e:
            return f"[LLM unavailable: {e}]"

    def deepdive(self, ticker, signal_row):
        price = signal_row.get("details", {}).get("valuation", {}).get("price", "?")
        sector = signal_row.get("details", {}).get("valuation", {}).get("sector", "?")
        sec_filings = signal_row.get("sec_filings", "")
        sec_filings_section = ""
        if sec_filings:
            sec_filings_section = f"RECENT SEC FILINGS: {sec_filings}\n\n"
        signal_data = json.dumps({
            "total_score": signal_row.get("total_score"),
            "early_stage_score": signal_row.get("early_stage_score"),
            "active_signals": signal_row.get("active_signals"),
            "archetype": signal_row.get("archetype"),
            "scores": signal_row.get("scores"),
            "details": signal_row.get("details"),
        }, indent=2, default=str)
        prompt = DEEP_DIVE_PROMPT.format(
            ticker=ticker,
            signal_data=signal_data,
            price=price,
            sector=sector,
            sec_filings_section=sec_filings_section,
        )
        try:
            return self._send_prompt(prompt, timeout=120)
        except requests.RequestException as e:
            return f"[LLM unavailable: {e}]"

    def cross_validate(self, scored_picks):
        if not scored_picks:
            return None
        lines = []
        for e in scored_picks[:15]:
            s = e["scores"]
            d = e["details"]
            v = d.get("valuation", {})
            ins = d.get("insider", {})
            tech = d.get("technicals", {})
            si = d.get("short_interest", {})
            earn = d.get("earnings", {})
            fh = d.get("financial_health", {})
            tags = []
            if v: tags.append(f"val(pe={v.get('fwd_pe','?')},gr={v.get('rev_growth','?')})")
            if ins and ins.get("net", 0) != 0: tags.append(f"ins(net=${ins.get('net_value',0):+,.0f})")
            if tech: tags.append(f"tech(1m={tech.get('ret_1m','?')}%,3m={tech.get('ret_3m','?')}%,rsi={tech.get('rsi','?')})")
            if si and si.get("short_pct", 0): tags.append(f"si={si.get('short_pct',0)}%")
            if earn and earn.get("total_quarters", 0): tags.append(f"earn(beat={earn.get('beat_rate',0)*100:.0f}%,surp={earn.get('avg_surprise_pct',0):.1f}%)")
            fh_sigs = fh.get("signals", []) if fh else []
            if fh_sigs: tags.append(f"fh({','.join(fh_sigs)})")
            lines.append(f"- {e['ticker']} (score={e['total_score']}, {e['active_signals']}sig): {' '.join(tags)}")
        picks_text = "\n".join(lines)
        prompt = CROSS_VALIDATE_PROMPT.format(picks_text=picks_text)
        try:
            return self._send_prompt(prompt, timeout=120)
        except requests.RequestException as e:
            return f"[LLM unavailable: {e}]"
