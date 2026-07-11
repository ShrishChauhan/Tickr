"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { normalizeUsername } from "@/lib/validation/username";
import GoogleOAuthButton from "./GoogleOAuthButton";
import styles from "./AuthForm.module.css";

export default function LoginForm() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const supabase = createClient();
    const trimmedIdentifier = identifier.trim();
    let email = trimmedIdentifier;

    if (!trimmedIdentifier.includes("@")) {
      const { data: resolvedEmail, error: rpcError } = await supabase.rpc(
        "get_email_for_username",
        { p_username: normalizeUsername(trimmedIdentifier) }
      );

      if (rpcError || !resolvedEmail) {
        setError("Invalid username/email or password.");
        setLoading(false);
        return;
      }

      email = resolvedEmail;
    }

    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });

    setLoading(false);

    if (signInError) {
      setError("Invalid username/email or password.");
      return;
    }

    router.push("/");
    router.refresh();
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <label className={styles.field}>
        <span className={styles.label}>Username or email</span>
        <input
          className={styles.input}
          type="text"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          required
          autoComplete="username"
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
          autoComplete="current-password"
        />
      </label>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <button className={styles.submit} type="submit" disabled={loading}>
        {loading ? "Please wait…" : "Log in"}
      </button>

      <GoogleOAuthButton disabled={loading} onError={setError} />

      <p className={styles.footer}>
        Don&apos;t have an account?{" "}
        <Link href="/signup" className={styles.footerLink}>
          Sign up
        </Link>
      </p>
    </form>
  );
}
