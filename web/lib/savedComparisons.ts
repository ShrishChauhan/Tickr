import type { SupabaseClient } from "@supabase/supabase-js";

export interface SavedComparison {
  id: string;
  name: string;
  tickers: string[];
  created_at: string;
}

const UNIQUE_VIOLATION = "23505";

export async function listSavedComparisons(
  supabase: SupabaseClient,
  userId: string,
): Promise<SavedComparison[]> {
  const { data } = await supabase
    .from("saved_comparisons")
    .select("id, name, tickers, created_at")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .returns<SavedComparison[]>();

  return data ?? [];
}

export type SaveComparisonResult =
  | { status: "saved" }
  | { status: "duplicate" }
  | { status: "error"; message: string };

interface SaveComparisonInput {
  name: string;
  tickers: string[];
}

export async function saveComparison(
  supabase: SupabaseClient,
  userId: string,
  input: SaveComparisonInput,
): Promise<SaveComparisonResult> {
  const { name, tickers } = input;

  const { error } = await supabase.from("saved_comparisons").insert({
    user_id: userId,
    name,
    tickers,
  });

  if (error) {
    if (error.code === UNIQUE_VIOLATION) {
      return { status: "duplicate" };
    }
    return { status: "error", message: "Couldn't save this comparison. Please try again." };
  }

  return { status: "saved" };
}

export async function deleteSavedComparison(supabase: SupabaseClient, id: string): Promise<void> {
  await supabase.from("saved_comparisons").delete().eq("id", id);
}
