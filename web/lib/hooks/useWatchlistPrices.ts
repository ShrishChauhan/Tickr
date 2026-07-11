"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { fetchPriceOnly, ApiError } from "@/lib/api";
import type { PriceOnlyData } from "@/lib/api";
import { priceDataConfig } from "@/lib/swrConfig";
import { watchlistPricesKey } from "@/lib/swrKeys";

export type WatchlistPriceEntry =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: PriceOnlyData };

type PriceMap = Record<string, WatchlistPriceEntry>;

async function fetchAll(tickers: string[]): Promise<PriceMap> {
  const settled = await Promise.allSettled(tickers.map((t) => fetchPriceOnly(t)));
  const out: PriceMap = {};
  tickers.forEach((ticker, i) => {
    const result = settled[i];
    out[ticker] = result.status === "fulfilled"
      ? { status: "success", data: result.value }
      : {
          status: "error",
          message: result.reason instanceof ApiError ? result.reason.message : "Failed to load price",
        };
  });
  return out;
}

// One shared SWR entry for the whole watchlist page. Fetches are still fired one-per-ticker
// (no batch endpoint exists), but Promise.allSettled means one failing ticker never blocks
// the rest — each ticker's result is isolated in the returned map.
export function useWatchlistPrices(tickers: string[]): PriceMap {
  const dedupedTickers = useMemo(() => Array.from(new Set(tickers)), [tickers]);
  // Original casing is preserved for the actual requests — tickers like "EURUSD=X" or
  // "BTC-USD" are case-sensitive against upstream providers. Only the SWR cache key is
  // normalized (trimmed/uppercased/sorted) for stability.
  const cacheKeyTickers = useMemo(
    () => dedupedTickers.map((t) => t.trim().toUpperCase()).sort(),
    [dedupedTickers],
  );
  const key = cacheKeyTickers.length > 0 ? watchlistPricesKey(cacheKeyTickers) : null;

  // fetchAll never throws — per-ticker failures live inside the resolved map — so
  // useSWR's `error` is intentionally unused here.
  const { data } = useSWR<PriceMap>(key, () => fetchAll(dedupedTickers), priceDataConfig);

  return useMemo(() => {
    const map: PriceMap = {};
    for (const ticker of dedupedTickers) {
      map[ticker] = data?.[ticker] ?? { status: "loading" };
    }
    return map;
  }, [data, dedupedTickers]);
}
