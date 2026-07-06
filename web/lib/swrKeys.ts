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
