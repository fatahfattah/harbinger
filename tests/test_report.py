import json
import csv
import os
from scoring.ranker import rank
from output.report import _write_csv, _write_metadata
from conftest import SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS, FakeConfig
from llm.patterns import ARCHEYTPE_PROFILES


EXPECTED_CSV_HEADERS = [
    "Ticker", "Score", "Val_Score", "Insider_Score", "13F_Score",
    "Social_Score", "Cat_Score", "Tech_Score", "Niche_Score", "Short_Score", "Earnings_Score", "FH_Score", "AN_Score", "Inst_Score", "Div_Score", "Sea_Score", "Mac_Score",
    "Active_Signals",
    "Pattern", "Pattern_Sim",
    "Name", "Price", "Sector", "Fwd_PE", "Rev_Growth",
    "Insider_Buys", "Insider_Sells", "Insider_Net",
    "Insider_Buy_Value", "Insider_Sell_Value", "Insider_Net_Value",
    "Insider_Transactions",
    "New_Funds", "Fund_Names",
    "Reddit_Mentions",
    "Niche_Mentions", "Niche_Keywords", "Niche_Communities",
    "Catalyst_Events",
    "Ret_1m", "Ret_3m", "RSI", "Vol_Ratio",
    "Above_50ma", "Above_200ma", "Pct_From_High",
    "Short_Pct", "Short_Ratio", "Short_Change",
    "Beat_Rate", "Avg_Surprise_Pct",
    "D/E", "Current_Ratio", "Profit_Margin", "ROE", "FH_Signals",
    "Price_Target", "PT_Upside", "AN_Consensus", "AN_Analysts",
    "Inst_Pct", "Holder_Count", "Inst_Change", "Inst_Signals",
    "Div_Yield", "Payout_Ratio", "Beta", "Gross_Margin", "Div_Signals",
    "Sea_Profile", "Sea_Best", "Sea_Best_Avg", "Sea_Hit_Rate",
    "Mac_FX", "Mac_Rate", "Mac_Comm", "Mac_Asia", "Mac_Signals",
    "Sector_Momentum_Boost", "Convergence_Amp",
    "Early_Stage_Score",
]


class TestWriteCsv:
    def setup_method(self):
        self.scored = rank(SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS)

    def test_headers_match_expected(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_csv(self.scored, config, "20260531_120000")
        with open(path) as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == EXPECTED_CSV_HEADERS

    def test_row_count(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_csv(self.scored, config, "20260531_120000")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(self.scored)

    def test_asts_row_values(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_csv(self.scored, config, "20260531_120000")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        asts = next(r for r in rows if r["Ticker"] == "ASTS")
        assert float(asts["Score"]) > 0
        assert float(asts["Val_Score"]) > 0
        assert asts["Name"] == "AST SpaceMobile"
        assert float(asts["Insider_Net_Value"]) > 0

    def test_insider_transactions_column(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_csv(self.scored, config, "20260531_120000")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        txs = json.loads(rows[0]["Insider_Transactions"])
        if txs:
            assert isinstance(txs, list)
            assert "name" in txs[0]
            assert "code" in txs[0]

    def test_empty_scored_list(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_csv([], config, "20260531_120000")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 0

    def test_dict_wrapped_in_list(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        singled = self.scored[0]
        path = _write_csv(singled, config, "20260531_120000")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1

    def test_archetype_columns(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_csv(self.scored, config, "20260531_120000")
        with open(path) as f:
            rows = list(csv.DictReader(f))
        asts = next(r for r in rows if r["Ticker"] == "ASTS")
        assert asts["Pattern"] in ("MU-like", "NBIS-like", "ASTS-like", "Novel")
        assert asts["Pattern_Sim"] != ""


class TestWriteMetadata:
    def setup_method(self):
        self.scored = rank(SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS)

    def test_top_picks_count(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_metadata(self.scored, "LLM analysis here", config, {"universe": "test"}, "20260531_120000", "scan.csv")
        with open(path) as f:
            data = json.load(f)
        assert len(data["top_picks"]) == min(config.TOP_N, len(self.scored))
        assert data["top_count"] == len(data["top_picks"])

    def test_metadata_structure(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_metadata(self.scored, "", config, {"universe": "sp600"}, "20260531_120000", "scan.csv")
        with open(path) as f:
            data = json.load(f)
        assert data["timestamp"] == "20260531_120000"
        assert data["csv_file"] == "scan.csv"
        assert data["top_n"] == config.TOP_N
        assert data["llm_enabled"] == config.LLM_ENABLED
        assert data["metadata"]["universe"] == "sp600"

    def test_llm_narratives(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        expected_narratives = "**ASTS** — ASTS-like (high conviction)"
        path = _write_metadata(self.scored, expected_narratives, config, {}, "20260531_120000", "scan.csv")
        with open(path) as f:
            data = json.load(f)
        assert data["llm_narratives"] == expected_narratives

    def test_top_pick_details(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_metadata(self.scored, "", config, {}, "20260531_120000", "scan.csv")
        with open(path) as f:
            data = json.load(f)
        top = data["top_picks"][0]
        assert "ticker" in top
        assert "total_score" in top
        assert "scores" in top
        assert "details" in top
        assert "name" in top["details"]
        assert "events" in top["details"]
        assert "niche_mentions" in top["details"]

    def test_total_scored_tracked(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_metadata(self.scored, "", config, {}, "20260531_120000", "scan.csv")
        with open(path) as f:
            data = json.load(f)
        assert data["total_scored"] == len(self.scored)

    def test_none_metadata_defaults_to_empty(self, tmp_path):
        config = FakeConfig()
        config.OUTPUT_DIR = str(tmp_path)
        path = _write_metadata(self.scored, "", config, None, "20260531_120000", "scan.csv")
        with open(path) as f:
            data = json.load(f)
        assert "metadata" in data
        assert data["metadata"] == {}
