"""
yfinance coverage probe — run BEFORE writing any onboarding code.
Run from repo root:  engine/.venv/Scripts/python.exe engine/tests/probe_yfinance_coverage.py

Goal: find out empirically — not by guessing — where yfinance has fundamental
data, where it degrades, and where it's absent. This decides the onboarding tiers.

No assertions, no engine imports. Just fetches and reports.
"""
import yfinance as yf

# --- sample set across tiers/asset classes ---
SAMPLES = {
    "US equity (baseline)":        ["AAPL", "JPM"],
    "UK (.L)":                     ["SHEL.L", "HSBA.L"],
    "Germany (.DE)":               ["SAP.DE", "BMW.DE"],
    "Japan (.T)":                  ["7203.T", "6758.T"],     # Toyota, Sony
    "India (.NS)":                 ["RELIANCE.NS", "TCS.NS"],
    "Brazil (.SA)":                ["PETR4.SA", "VALE3.SA"],
    "Mexico (.MX)":                ["WALMEX.MX", "GFNORTEO.MX"],
    "Crypto":                      ["BTC-USD", "ETH-USD"],
    "Forex":                       ["EURUSD=X", "USDJPY=X"],
    "Commodity (futures)":         ["GC=F", "CL=F"],          # gold, crude
    "Index":                       ["^GSPC", "^NSEI"],
}

# fields we care about for the normalization engine
KEY_FUNDAMENTALS = [
    "totalRevenue", "grossProfits", "operatingMargins",
    "netIncomeToCommon", "trailingPE", "returnOnEquity",
    "totalDebt", "freeCashflow",
]

def probe(ticker):
    out = {"price": False, "info_fields": 0, "fundamentals": 0,
           "financials_df": False, "name": None, "err": None}
    try:
        t = yf.Ticker(ticker)
        # price history
        try:
            h = t.history(period="5d")
            out["price"] = not h.empty
        except Exception:
            out["price"] = False
        # .info
        try:
            info = t.info or {}
            out["name"] = info.get("shortName") or info.get("longName")
            out["info_fields"] = len([k for k, v in info.items() if v not in (None, "", 0)])
            out["fundamentals"] = sum(1 for f in KEY_FUNDAMENTALS if info.get(f) not in (None, "", 0))
        except Exception as e:
            out["err"] = f"info:{type(e).__name__}"
        # financial statements
        try:
            fin = t.financials
            out["financials_df"] = fin is not None and not fin.empty
        except Exception:
            out["financials_df"] = False
    except Exception as e:
        out["err"] = f"{type(e).__name__}:{e}"
    return out

print(f"{'TICKER':<14}{'PRICE':<7}{'INFO#':<7}{'FUND/8':<8}{'STMTS':<7}NAME")
print("-" * 78)
for tier, tickers in SAMPLES.items():
    print(f"\n## {tier}")
    for tk in tickers:
        r = probe(tk)
        price = "yes" if r["price"] else "NO"
        stmts = "yes" if r["financials_df"] else "NO"
        name = r["name"] or (r["err"] or "?")
        print(f"{tk:<14}{price:<7}{r['info_fields']:<7}{r['fundamentals']}/8     {stmts:<7}{name}")

print("\n\nREAD THE RESULTS THIS WAY:")
print("- PRICE=yes, FUND>=5, STMTS=yes  -> full equity model works (Tier 1)")
print("- PRICE=yes, FUND 1-4, STMTS=mix -> partial; show what exists, 'limited data'")
print("- PRICE=yes, FUND=0, STMTS=NO    -> price-only asset (crypto/fx/commodity) -> needs separate model")
print("- PRICE=NO                       -> ticker format wrong or unsupported")
