from scoring.ranker import rank, _match_archetype, _extract_details
from conftest import (
    SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS, SAMPLE_TICKERS,
    make_signal,
)
from llm.patterns import ARCHEYTPE_PROFILES


class TestMatchArchetype:
    def test_mu_like_match(self):
        s = ARCHEYTPE_PROFILES["MU-like"]
        scores = {d: s[d] for d in ["valuation", "insider", "fund_13f", "social", "catalyst", "technicals", "niche"]}
        name, sim = _match_archetype(scores)
        assert name == "MU-like"
        assert sim >= 80
        assert sim <= 100

    def test_nbis_like_match(self):
        s = ARCHEYTPE_PROFILES["NBIS-like"]
        scores = {d: s[d] for d in ["valuation", "insider", "fund_13f", "social", "catalyst", "technicals", "niche"]}
        name, sim = _match_archetype(scores)
        assert name == "NBIS-like"
        assert sim >= 80

    def test_asts_like_match(self):
        s = ARCHEYTPE_PROFILES["ASTS-like"]
        scores = {d: s[d] for d in ["valuation", "insider", "fund_13f", "social", "catalyst", "technicals", "niche"]}
        name, sim = _match_archetype(scores)
        assert name == "ASTS-like"
        assert sim >= 80

    def test_novel_when_less_than_3_active_dims(self):
        scores = {"valuation": 7, "insider": 8}
        name, sim = _match_archetype(scores)
        assert name == "Novel"
        assert sim == 0

    def test_novel_when_all_scores_zero(self):
        scores = {"valuation": 0, "insider": 0, "fund_13f": 0, "social": 0, "catalyst": 0, "technicals": 0, "niche": 0}
        name, sim = _match_archetype(scores)
        assert name == "Novel"
        assert sim == 0

    def test_social_dominant_matches_nbis(self):
        scores = {"valuation": 0, "insider": 0, "fund_13f": 0, "social": 7, "catalyst": 7, "technicals": 0, "niche": 8}
        name, sim = _match_archetype(scores)
        assert name == "NBIS-like"
        assert sim >= 90

    def test_close_to_mu_matches_mu(self):
        scores = {"valuation": 6, "insider": 5, "fund_13f": 6, "social": 5, "catalyst": 5, "technicals": 4, "niche": 4}
        name, sim = _match_archetype(scores)
        assert name == "MU-like"
        assert sim >= 30

    def test_only_active_dims_used(self):
        scores = {"valuation": 7, "insider": 6, "fund_13f": 7, "social": 0, "catalyst": 0, "technicals": 0, "niche": 0}
        name, sim = _match_archetype(scores)
        assert name == "MU-like"
        assert sim >= 70


class TestExtractDetails:
    def test_valuation_details(self):
        c = make_signal(7.0, "ASTS", name="AST SpaceMobile", sector="Technology", price=113.41, signals=["Low PE", "High Growth"])
        d = _extract_details("valuation", c)
        assert d["name"] == "AST SpaceMobile"
        assert d["price"] == 113.41
        assert d["sector"] == "Technology"
        assert d["rev_growth"] == 0

    def test_insider_details_with_transactions(self):
        txs = [{"name": "Abel Avellan", "role": "CEO", "code": "P", "value": 100000}]
        c = make_signal(6.0, "ASTS", buys=5, sells=2, net=3,
                        buy_value=250000, sell_value=80000, net_value=170000,
                        transactions=txs)
        d = _extract_details("insider", c)
        assert d["buys"] == 5
        assert d["sells"] == 2
        assert d["net_value"] == 170000
        assert d["transactions"] == txs

    def test_13f_details(self):
        c = make_signal(8.0, "ASTS", new_fund_count=3, funds=["RenTech", "Citadel", "Coatue"])
        d = _extract_details("fund_13f", c)
        assert d["new_funds"] == 3
        assert d["fund_names"] == ["RenTech", "Citadel", "Coatue"]

    def test_social_details(self):
        c = make_signal(9.0, "ASTS", mentions=45, subreddits={"ASTS": 40, "wsb": 5})
        d = _extract_details("social", c)
        assert d["mentions"] == 45
        assert d["subreddits"]["ASTS"] == 40

    def test_catalyst_details(self):
        c = make_signal(7.0, "ASTS", catalysts=["8-K:Launch", "Earnings:Beat"])
        d = _extract_details("catalyst", c)
        assert d["events"] == ["8-K:Launch", "Earnings:Beat"]

    def test_technicals_details(self):
        c = make_signal(8.0, "ASTS", ret_1m=53.5, ret_3m=30.5, rsi=69.8, vol_ratio=2.08,
                        above_50ma=True, above_200ma=False, signals=["1m+"])
        d = _extract_details("technicals", c)
        assert d["ret_1m"] == 53.5
        assert d["rsi"] == 69.8
        assert d["above_50ma"] is True
        assert d["above_200ma"] is False

    def test_niche_details(self):
        c = make_signal(10.0, "ASTS", niche_mentions=12, general_mentions=3,
                        keywords=["satellite"], communities=["r/space"])
        d = _extract_details("niche", c)
        assert d["niche_mentions"] == 12
        assert d["keywords"] == ["satellite"]
        assert d["communities"] == ["r/space"]

    def test_unknown_signal_name(self):
        c = make_signal(5.0, "TEST")
        d = _extract_details("unknown", c)
        assert d == {}


class TestRank:
    def test_empty_input(self):
        result = rank({}, SAMPLE_WEIGHTS)
        assert result == []

    def test_single_signal_single_ticker(self):
        data = {"valuation": [make_signal(5.0, "ASTS", name="AST SpaceMobile")]}
        result = rank(data, SAMPLE_WEIGHTS)
        assert len(result) == 1
        assert result[0]["ticker"] == "ASTS"
        assert result[0]["total_score"] > 0

    def test_multi_signal_multi_ticker(self):
        result = rank(SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS)
        assert len(result) == 3
        assert all(r["ticker"] in SAMPLE_TICKERS for r in result)

    def test_scores_sorted_descending(self):
        result = rank(SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS)
        scores = [r["total_score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_scores_within_bounds(self):
        result = rank(SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS)
        for r in result:
            assert 0 <= r["total_score"] <= 12

    def test_active_signals_counted(self):
        result = rank(SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS)
        for r in result:
            assert 0 <= r["active_signals"] <= 7

    def test_archetype_in_result(self):
        result = rank(SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS)
        for r in result:
            assert "archetype" in r
            assert "archetype_similarity" in r

    def test_details_in_result(self):
        result = rank(SAMPLE_SIGNAL_DATA, SAMPLE_WEIGHTS)
        asts = next(r for r in result if r["ticker"] == "ASTS")
        assert "valuation" in asts["details"]
        assert "insider" in asts["details"]
        assert "fund_13f" in asts["details"]
        assert "social" in asts["details"]
        assert "catalyst" in asts["details"]
        assert "technicals" in asts["details"]
        assert "niche" in asts["details"]

    def test_convergence_boost_applied(self):
        data = {"valuation": [make_signal(5.0, "T1")], "insider": [make_signal(5.0, "T1")],
                "fund_13f": [make_signal(5.0, "T1")], "social": [make_signal(5.0, "T1")]}
        result = rank(data, SAMPLE_WEIGHTS)
        weighted = (5 * 0.18 + 5 * 0.15 + 5 * 0.18 + 5 * 0.05)
        assert result[0]["total_score"] == round(weighted + 2.0, 2)

    def test_missing_signal_not_in_scores(self):
        result = rank({"valuation": [make_signal(5.0, "T1")], "insider": [make_signal(5.0, "T1")]}, SAMPLE_WEIGHTS)
        assert result[0]["scores"]["valuation"] == 5.0
        assert "fund_13f" not in result[0]["scores"]
