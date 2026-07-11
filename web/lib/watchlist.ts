import type { SupabaseClient } from "@supabase/supabase-js";
import { fetchSearch } from "@/lib/api";

export const MARKET_LABELS: Record<string, string> = {
  US: "US Stocks",
  UK: "UK Stocks",
  DE: "German Stocks",
  JP: "Japanese Stocks",
  IN: "Indian Stocks",
  BR: "Brazilian Stocks",
  MX: "Mexican Stocks",
};

export const ASSET_TYPE_GROUP_LABELS: Record<string, string> = {
  equity: "Equities",
  crypto: "Crypto",
  forex: "Forex",
  commodity: "Commodities",
  index: "Indices",
  etf: "ETFs",
  fund: "Funds",
};

export interface Tag {
  id: string;
  name: string;
  is_auto_derived: boolean;
}

export interface WatchlistItem {
  id: string;
  ticker: string;
  asset_type: string;
  display_name: string | null;
  notes: string | null;
  added_at: string;
  tags: Tag[];
}

const UNIQUE_VIOLATION = "23505";

export async function getOrCreateTag(
  supabase: SupabaseClient,
  userId: string,
  name: string,
  isAutoDerived: boolean,
): Promise<string | null> {
  const trimmed = name.trim();
  if (!trimmed) return null;

  const existing = await supabase
    .from("tags")
    .select("id")
    .eq("user_id", userId)
    .ilike("name", trimmed)
    .maybeSingle();

  if (existing.data) return existing.data.id;

  const inserted = await supabase
    .from("tags")
    .insert({ user_id: userId, name: trimmed, is_auto_derived: isAutoDerived })
    .select("id")
    .single();

  if (inserted.data) return inserted.data.id;

  if (inserted.error?.code === UNIQUE_VIOLATION) {
    const retry = await supabase
      .from("tags")
      .select("id")
      .eq("user_id", userId)
      .ilike("name", trimmed)
      .maybeSingle();
    return retry.data?.id ?? null;
  }

  return null;
}

async function attachTag(
  supabase: SupabaseClient,
  itemId: string,
  tagId: string,
): Promise<void> {
  await supabase.from("watchlist_item_tags").insert({ item_id: itemId, tag_id: tagId });
}

export type AddToWatchlistResult =
  | { status: "added" }
  | { status: "duplicate" }
  | { status: "error"; message: string };

interface AddToWatchlistInput {
  ticker: string;
  assetType: string;
  displayName: string;
  market: string;
}

export async function addToWatchlist(
  supabase: SupabaseClient,
  userId: string,
  input: AddToWatchlistInput,
): Promise<AddToWatchlistResult> {
  const { ticker, assetType, displayName, market } = input;

  const inserted = await supabase
    .from("watchlist_items")
    .insert({
      user_id: userId,
      ticker,
      asset_type: assetType,
      display_name: displayName,
    })
    .select("id")
    .single();

  if (inserted.error) {
    if (inserted.error.code === UNIQUE_VIOLATION) {
      return { status: "duplicate" };
    }
    return { status: "error", message: "Couldn't add to watchlist. Please try again." };
  }

  const itemId = inserted.data.id as string;

  if (assetType === "equity") {
    const marketLabel = MARKET_LABELS[market];
    if (marketLabel) {
      const marketTagId = await getOrCreateTag(supabase, userId, marketLabel, true);
      if (marketTagId) await attachTag(supabase, itemId, marketTagId);
    }

    const results = await fetchSearch(ticker);
    const match = results.find((r) => r.ticker.toUpperCase() === ticker.toUpperCase());
    if (match?.sector) {
      const sectorTagId = await getOrCreateTag(supabase, userId, match.sector, true);
      if (sectorTagId) await attachTag(supabase, itemId, sectorTagId);
    }
  }

  return { status: "added" };
}
