"use client";

import { useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { isValidUsername, normalizeUsername } from "@/lib/validation/username";
import GoogleOAuthButton from "./GoogleOAuthButton";
import styles from "./AuthForm.module.css";

type UsernameStatus = "idle" | "checking" | "available" | "taken" | "invalid";

export default function SignupForm() {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [username, setUsername] = useState("");
  const [usernameStatus, setUsernameStatus] = useState<UsernameStatus>("idle");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [signupSent, setSignupSent] = useState(false);

  async function handleUsernameBlur() {
    const normalized = normalizeUsername(username);
    if (!normalized) {
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

    const { error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          username: normalized,
        },
      },
    });

    if (signUpError) {
      const { data: taken } = await supabase.rpc("username_exists", { p_username: normalized });
      setError(
        taken
          ? "That username was just taken — please choose another one."
          : "Something went wrong creating your account. Please try again."
      );
      setLoading(false);
      return;
    }

    setLoading(false);
    setSignupSent(true);
  }

  if (signupSent) {
    return (
      <div className={styles.form}>
        <p className={styles.notice}>
          Check your email to verify your account, then log in.
        </p>
        <Link href="/login" className={styles.footerLink}>
          Back to login
        </Link>
      </div>
    );
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
          required
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
          required
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

      <label className={styles.field}>
        <span className={styles.label}>Email</span>
        <input
          className={styles.input}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
        />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Password</span>
        <input
          className={styles.input}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={6}
          autoComplete="new-password"
        />
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
        {loading ? "Please wait…" : "Sign up"}
      </button>

      <GoogleOAuthButton disabled={loading} onError={setError} />

      <p className={styles.footer}>
        Already have an account?{" "}
        <Link href="/login" className={styles.footerLink}>
          Log in
        </Link>
      </p>
    </form>
  );
}
