import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


SAMPLE_TICKERS = ["ASTS", "AMR", "SOFI"]


def make_signal(score, ticker, **kw):
    base = {"ticker": ticker, "score": score}
    base.update(kw)
    return base


SAMPLE_VAL_CANDIDATES = [
    make_signal(7.0, "ASTS", name="AST SpaceMobile", sector="Technology", price=113.41),
    make_signal(5.0, "AMR", name="Alpha Metallurgical Resources", sector="Materials", price=189.0),
    make_signal(3.0, "SOFI", name="SoFi Technologies", sector="Financial", price=8.50),
]

SAMPLE_INSIDER_CANDIDATES = [
    make_signal(6.0, "ASTS", buys=5, sells=2, net=3,
                buy_value=250000, sell_value=80000, net_value=170000,
                transactions=[{"name": "Abel Avellan", "role": "CEO", "code": "P", "value": 100000}]),
    make_signal(4.0, "AMR", buys=3, sells=0, net=3,
                buy_value=50000, sell_value=0, net_value=50000,
                transactions=[]),
    make_signal(8.0, "SOFI", buys=10, sells=1, net=9,
                buy_value=2000000, sell_value=50000, net_value=1950000,
                transactions=[{"name": "Anthony Noto", "role": "CEO", "code": "P", "value": 500000}]),
]

SAMPLE_13F_CANDIDATES = [
    make_signal(8.0, "ASTS", new_fund_count=4, funds=["Renaissance", "Citadel", "D.E. Shaw", "Coatue"]),
    make_signal(3.0, "AMR", new_fund_count=1, funds=["Millennium"]),
    make_signal(6.0, "SOFI", new_fund_count=2, funds=["ARK", "Point72"]),
]

SAMPLE_SOCIAL_CANDIDATES = [
    make_signal(9.0, "ASTS", mentions=45, subreddits={"ASTS": 40, "wallstreetbets": 5}),
    make_signal(4.0, "SOFI", mentions=12, subreddits={"wallstreetbets": 12}),
]

SAMPLE_CATALYST_CANDIDATES = [
    make_signal(7.0, "ASTS", catalysts=["8-K:Satellite Launch", "Earnings:Revenue Beat"]),
    make_signal(5.0, "SOFI", catalysts=["Earnings:Guidance Raise"]),
]

SAMPLE_TECH_CANDIDATES = [
    make_signal(8.0, "ASTS", ret_1m=53.5, ret_3m=30.5, rsi=69.8, vol_ratio=2.08,
                above_50ma=True, above_200ma=False, signals=["1m+", "High Vol"]),
    make_signal(5.0, "AMR", ret_1m=15.2, ret_3m=-5.1, rsi=45.0, vol_ratio=1.2,
                above_50ma=True, above_200ma=True, signals=[]),
    make_signal(3.0, "SOFI", ret_1m=-2.1, ret_3m=8.5, rsi=55.0, vol_ratio=0.9,
                above_50ma=False, above_200ma=True, signals=[]),
]

SAMPLE_NICHE_CANDIDATES = [
    make_signal(10.0, "ASTS", niche_mentions=12, general_mentions=3,
                keywords=["satellite", "D2C"], communities=["r/space", "r/ASTSpaceMobile"]),
    make_signal(2.0, "SOFI", niche_mentions=1, general_mentions=0,
                keywords=["fintech"], communities=["r/fintech"]),
]


SAMPLE_SIGNAL_DATA = {
    "valuation": SAMPLE_VAL_CANDIDATES,
    "insider": SAMPLE_INSIDER_CANDIDATES,
    "fund_13f": SAMPLE_13F_CANDIDATES,
    "social": SAMPLE_SOCIAL_CANDIDATES,
    "catalyst": SAMPLE_CATALYST_CANDIDATES,
    "technicals": SAMPLE_TECH_CANDIDATES,
    "niche": SAMPLE_NICHE_CANDIDATES,
}


SAMPLE_WEIGHTS = {
    "valuation": 0.18,
    "insider": 0.15,
    "fund_13f": 0.18,
    "social": 0.05,
    "catalyst": 0.09,
    "technicals": 0.20,
    "niche": 0.15,
}


class FakeConfig:
    TOP_N = 15
    OUTPUT_DIR = "/tmp/harbinger_test"
    LLM_ENABLED = True
