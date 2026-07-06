// company/fundamentals/filings — server TTL is 1 day, no need to revalidate on every focus
export const dailyDataConfig = { dedupingInterval: 10 * 60 * 1000, revalidateOnFocus: false };

// price-only assets — matches PRICE_DATA_TTL_SECONDS (15 min) exactly; revalidateOnFocus left
// at SWR's default (true) since dedupingInterval already throttles it to ~15 min effectively
export const priceDataConfig = { dedupingInterval: 15 * 60 * 1000 };

// batch screener rows — no dedicated server TTL; reasonable middle ground for a per-tab session
export const screenerConfig = { dedupingInterval: 5 * 60 * 1000 };
