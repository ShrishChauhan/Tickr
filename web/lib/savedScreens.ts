import type { SupabaseClient } from "@supabase/supabase-js";

export interface SavedScreen {
  id: string;
  name: string;
  universe_key: string;
  filters: Record<string, string>;
  created_at: string;
}

const UNIQUE_VIOLATION = "23505";

export async function listSavedScreens(
  supabase: SupabaseClient,
  userId: string,
): Promise<SavedScreen[]> {
  const { data } = await supabase
    .from("saved_screens")
    .select("id, name, universe_key, filters, created_at")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .returns<SavedScreen[]>();

  return data ?? [];
}

export type SaveScreenResult =
  | { status: "saved" }
  | { status: "duplicate" }
  | { status: "error"; message: string };

interface SaveScreenInput {
  name: string;
  universeKey: string;
  filters: Record<string, string>;
}

export async function saveScreen(
  supabase: SupabaseClient,
  userId: string,
  input: SaveScreenInput,
): Promise<SaveScreenResult> {
  const { name, universeKey, filters } = input;

  const { error } = await supabase.from("saved_screens").insert({
    user_id: userId,
    name,
    universe_key: universeKey,
    filters,
  });

  if (error) {
    if (error.code === UNIQUE_VIOLATION) {
      return { status: "duplicate" };
    }
    return { status: "error", message: "Couldn't save this screen. Please try again." };
  }

  return { status: "saved" };
}

export async function deleteSavedScreen(supabase: SupabaseClient, id: string): Promise<void> {
  await supabase.from("saved_screens").delete().eq("id", id);
}
