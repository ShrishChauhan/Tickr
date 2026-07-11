import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import WatchlistView from "./WatchlistView";
import type { WatchlistItem } from "@/lib/watchlist";
import styles from "./page.module.css";

interface RawTagLink {
  tags: { id: string; name: string; is_auto_derived: boolean } | null;
}

interface RawItem {
  id: string;
  ticker: string;
  asset_type: string;
  display_name: string | null;
  notes: string | null;
  added_at: string;
  watchlist_item_tags: RawTagLink[];
}

export default async function WatchlistPage() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();

  if (!data.user) {
    redirect("/login");
  }

  const { data: rows } = await supabase
    .from("watchlist_items")
    .select("id, ticker, asset_type, display_name, notes, added_at, watchlist_item_tags(tags(id, name, is_auto_derived))")
    .order("added_at", { ascending: false })
    .returns<RawItem[]>();

  const items: WatchlistItem[] = (rows ?? []).map((row) => ({
    id: row.id,
    ticker: row.ticker,
    asset_type: row.asset_type,
    display_name: row.display_name,
    notes: row.notes,
    added_at: row.added_at,
    tags: row.watchlist_item_tags
      .map((link) => link.tags)
      .filter((tag): tag is { id: string; name: string; is_auto_derived: boolean } => tag !== null),
  }));

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <h1 className={styles.title}>Watchlist</h1>
        <WatchlistView initialItems={items} userId={data.user.id} />
      </div>
    </main>
  );
}
