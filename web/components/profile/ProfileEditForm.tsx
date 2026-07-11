"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { isValidUsername, normalizeUsername } from "@/lib/validation/username";
import styles from "./ProfileEditForm.module.css";

type UsernameStatus = "idle" | "checking" | "available" | "taken" | "invalid";

interface ProfileEditFormProps {
  initialUsername: string;
  initialFirstName: string;
  initialLastName: string;
  initialDisplayName: string;
  initialBio: string;
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function ProfileEditForm({
  initialUsername,
  initialFirstName,
  initialLastName,
  initialDisplayName,
  initialBio,
}: ProfileEditFormProps) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [username, setUsername] = useState(initialUsername);
  const [usernameStatus, setUsernameStatus] = useState<UsernameStatus>("idle");
  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [displayName, setDisplayName] = useState(initialDisplayName);
  const [bio, setBio] = useState(initialBio);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const avatarLabel = initialDisplayName || initialUsername;

  function handleCancel() {
    setUsername(initialUsername);
    setUsernameStatus("idle");
    setFirstName(initialFirstName);
    setLastName(initialLastName);
    setDisplayName(initialDisplayName);
    setBio(initialBio);
    setError(null);
    setEditing(false);
  }

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

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
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

    const { error: updateError } = await supabase
      .from("profiles")
      .update({
        username: normalized,
        display_name: displayName.trim() || null,
        first_name: firstName.trim() || null,
        last_name: lastName.trim() || null,
        bio: bio.trim() || null,
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

    setEditing(false);
    router.refresh();
  }

  if (!editing) {
    return (
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.avatar}>{getInitials(avatarLabel)}</div>
          <div className={styles.headerText}>
            <span className={styles.displayName}>{initialDisplayName || initialUsername}</span>
            <span className={styles.username}>@{initialUsername}</span>
          </div>
        </div>

        <div className={styles.rows}>
          <div className={styles.row}>
            <span className={styles.rowLabel}>First name</span>
            <span className={styles.rowValue}>{initialFirstName || "—"}</span>
          </div>
          <div className={styles.row}>
            <span className={styles.rowLabel}>Last name</span>
            <span className={styles.rowValue}>{initialLastName || "—"}</span>
          </div>
          <div className={styles.row}>
            <span className={styles.rowLabel}>Bio</span>
            <span className={styles.rowValue}>{initialBio || "—"}</span>
          </div>
        </div>

        <div className={styles.actions}>
          <button className={styles.buttonPrimary} type="button" onClick={() => setEditing(true)}>
            Edit
          </button>
        </div>
      </div>
    );
  }

  return (
    <form className={styles.card} onSubmit={handleSave}>
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
          <span className={styles.error}>3-20 lowercase letters, numbers, underscores.</span>
        )}
        {usernameStatus === "checking" && <span className={styles.error}>Checking availability…</span>}
        {usernameStatus === "taken" && <span className={styles.error}>That username is taken.</span>}
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Display name</span>
        <input
          className={styles.input}
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </label>

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
        <span className={styles.label}>Bio</span>
        <textarea
          className={styles.textarea}
          value={bio}
          onChange={(e) => setBio(e.target.value)}
          maxLength={280}
        />
      </label>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <div className={styles.actions}>
        <button
          className={styles.buttonPrimary}
          type="submit"
          disabled={loading || usernameStatus === "checking" || usernameStatus === "taken"}
        >
          {loading ? "Saving…" : "Save"}
        </button>
        <button className={styles.buttonSecondary} type="button" onClick={handleCancel} disabled={loading}>
          Cancel
        </button>
      </div>
    </form>
  );
}
