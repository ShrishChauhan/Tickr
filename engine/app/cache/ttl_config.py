# TTL constants by data type — AI analysis is the most expensive, cache hardest
PRICE_TTL_SECONDS = 30              # live prices: very short or skip caching entirely
PRICE_DATA_TTL_SECONDS = 900        # price+OHLC for non-equity assets: 15 minutes
FUNDAMENTALS_TTL_SECONDS = 86_400   # quarterly/annual financials: 1 day
FILING_REF_TTL_SECONDS = 86_400     # filing list/metadata: 1 day
AI_ANALYSIS_TTL_SECONDS = 604_800   # AI summaries: 7 days (until next filing invalidates)
COMPANY_INFO_TTL_SECONDS = 86_400   # company name/exchange/etc: 1 day
