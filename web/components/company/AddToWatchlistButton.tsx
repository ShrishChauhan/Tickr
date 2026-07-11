'use client';

import { useState } from 'react';
import { createClient } from '@/lib/supabase/client';
import { useSupabaseUser } from '@/lib/hooks/useSupabaseUser';
import { addToWatchlist } from '@/lib/watchlist';
import styles from './AddToWatchlistButton.module.css';

interface Props {
  ticker: string;
  name: string;
  assetType: string;
  market: string;
}

type ButtonState = 'idle' | 'loading' | 'watching' | 'error';

export default function AddToWatchlistButton({ ticker, name, assetType, market }: Props) {
  const { user, loading: userLoading } = useSupabaseUser();
  const [state, setState] = useState<ButtonState>('idle');
  const [message, setMessage] = useState<string | null>(null);

  if (userLoading) return null;

  if (!user) {
    return (
      <a href="/login" className={styles.signInPrompt}>
        Sign in to track
      </a>
    );
  }

  async function handleClick() {
    if (state === 'loading' || state === 'watching') return;
    setState('loading');
    setMessage(null);

    const supabase = createClient();
    const result = await addToWatchlist(supabase, user!.id, {
      ticker,
      assetType,
      displayName: name,
      market,
    });

    if (result.status === 'error') {
      setState('error');
      setMessage(result.message);
      return;
    }

    setState('watching');
  }

  if (state === 'watching') {
    return <span className={styles.watchingBadge}>✓ Watching</span>;
  }

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={styles.button}
        onClick={handleClick}
        disabled={state === 'loading'}
      >
        {state === 'loading' ? 'Adding…' : '+ Watchlist'}
      </button>
      {state === 'error' && message && <span className={styles.error}>{message}</span>}
    </div>
  );
}
