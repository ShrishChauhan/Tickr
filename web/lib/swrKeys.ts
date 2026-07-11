export const companyKey = (ticker: string) => `/api/v1/companies/${ticker.trim().toUpperCase()}`;

export const fundamentalsKey = (
  ticker: string,
  period: 'annual' | 'quarterly' = 'annual',
  limit = 5,
) => `/api/v1/companies/${ticker.trim().toUpperCase()}/fundamentals?period=${period}&limit=${limit}`;

export const filingsKey = (ticker: string, limit = 10) =>
  `/api/v1/companies/${ticker.trim().toUpperCase()}/filings?limit=${limit}`;

export const priceOnlyKey = (ticker: string) => `/api/v1/assets/${ticker.trim().toUpperCase()}/price`;

export const screenerKey = (universeKey: string) => `/api/v1/screener/${universeKey}/rows`;

export const searchKey = (query: string) => `/api/v1/search?q=${query.trim()}`;

// Internal cache key for the watchlist dashboard's batched price fetch. Not a real API path —
// namespaced with a `watchlist-prices:` prefix so it can never collide with priceOnlyKey's
// per-ticker `/api/v1/assets/.../price` keys in SWR's global cache.
export const watchlistPricesKey = (sortedUpperTickers: string[]) =>
  `watchlist-prices:${sortedUpperTickers.join(',')}`;
