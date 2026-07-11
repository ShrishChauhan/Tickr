"use client";

import { createClient } from "@/lib/supabase/client";
import styles from "./AuthForm.module.css";

interface GoogleOAuthButtonProps {
  disabled: boolean;
  onError: (message: string) => void;
}

export default function GoogleOAuthButton({ disabled, onError }: GoogleOAuthButtonProps) {
  async function handleGoogleSignIn() {
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) onError(error.message);
  }

  return (
    <>
      <div className={styles.divider}>
        <span>or</span>
      </div>

      <button
        className={styles.google}
        type="button"
        onClick={handleGoogleSignIn}
        disabled={disabled}
      >
        Continue with Google
      </button>
    </>
  );
}
