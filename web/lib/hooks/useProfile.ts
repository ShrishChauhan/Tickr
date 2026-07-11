"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

interface Profile {
  username: string;
  display_name: string | null;
}

export function useProfile(userId: string | undefined) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      if (!userId) {
        if (!cancelled) {
          setProfile(null);
          setLoading(false);
        }
        return;
      }

      setLoading(true);
      const supabase = createClient();
      const { data } = await supabase
        .from("profiles")
        .select("username, display_name")
        .eq("id", userId)
        .single();

      if (!cancelled) {
        setProfile(data ?? null);
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [userId]);

  return { profile, loading };
}
