"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { isValidUsername, normalizeUsername } from "@/lib/validation/username";
import styles from "@/components/auth/AuthForm.module.css";

type UsernameStatus = "idle" | "checking" | "available" | "taken" | "invalid";

interface CompleteProfileFormProps {
  initialUsername: string;
  initialFirstName: string;
  initialLastName: string;
  redirectTo: string;
}

export default function CompleteProfileForm({
  initialUsername,
  initialFirstName,
  initialLastName,
  redirectTo,
}: CompleteProfileFormProps) {
  const router = useRouter();
  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [username, setUsername] = useState(initialUsername);
  const [usernameStatus, setUsernameStatus] = useState<UsernameStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleUsernameBlur() {
    const normalized = normalizeUsername(username);
    if (normalized === normalizeUsername(initialUsername)) {
      setUsernameStatus("idle");
      return;
    }
    if (!isValidUsername(normalized)) {
      setUsernameStatus("invalid");
      return;
    }

    setUsernameStatus("checking");
    const supabase = createClient();
    const { data, error: rpcError } = await supabase.rpc("username_exists", {
      p_username: normalized,
    });
    setUsernameStatus(rpcError ? "idle" : data ? "taken" : "available");
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    const normalized = normalizeUsername(username);
    if (!isValidUsername(normalized)) {
      setUsernameStatus("invalid");
      return;
    }
    if (usernameStatus === "taken") {
      return;
    }

    setLoading(true);
    const supabase = createClient();

    const { data: userData } = await supabase.auth.getUser();
    if (!userData.user) {
      setError("Session expired, please log in again.");
      setLoading(false);
      return;
    }

    const trimmedFirst = firstName.trim();
    const trimmedLast = lastName.trim();

    const { error: updateError } = await supabase
      .from("profiles")
      .update({
        username: normalized,
        first_name: trimmedFirst || null,
        last_name: trimmedLast || null,
        display_name:
          [trimmedFirst, trimmedLast].filter(Boolean).join(" ") || normalized,
        profile_completed: true,
      })
      .eq("id", userData.user.id);

    setLoading(false);

    if (updateError) {
      setError(
        updateError.code === "23505"
          ? "That username is already taken."
          : "Something went wrong saving your profile. Please try again."
      );
      return;
    }

    router.push(redirectTo);
    router.refresh();
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <label className={styles.field}>
        <span className={styles.label}>First name</span>
        <input
          className={styles.input}
          type="text"
          value={firstName}
          onChange={(e) => setFirstName(e.target.value)}
          autoComplete="given-name"
        />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Last name</span>
        <input
          className={styles.input}
          type="text"
          value={lastName}
          onChange={(e) => setLastName(e.target.value)}
          autoComplete="family-name"
        />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Username</span>
        <input
          className={styles.input}
          type="text"
          value={username}
          onChange={(e) => {
            setUsername(e.target.value);
            setUsernameStatus("idle");
          }}
          onBlur={handleUsernameBlur}
          required
          autoComplete="username"
        />
        {usernameStatus === "invalid" && (
          <span className={styles.error}>
            3-20 lowercase letters, numbers, underscores.
          </span>
        )}
        {usernameStatus === "checking" && (
          <span className={styles.error}>Checking availability…</span>
        )}
        {usernameStatus === "taken" && (
          <span className={styles.error}>That username is taken.</span>
        )}
      </label>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <button
        className={styles.submit}
        type="submit"
        disabled={loading || usernameStatus === "checking" || usernameStatus === "taken"}
      >
        {loading ? "Please wait…" : "Save and continue"}
      </button>
    </form>
  );
}
