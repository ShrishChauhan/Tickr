'use client';

import { useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { createClient } from '@/lib/supabase/client';
import { useSupabaseUser } from '@/lib/hooks/useSupabaseUser';
import { savedComparisonsKey } from '@/lib/swrKeys';
import { listSavedComparisons, saveComparison, deleteSavedComparison } from '@/lib/savedComparisons';
import type { SavedComparison } from '@/lib/savedComparisons';
import styles from './SavedComparisonsPanel.module.css';

interface Props {
  tickers: string[];
  onLoad: (tickers: string[]) => void;
}

export default function SavedComparisonsPanel({ tickers, onLoad }: Props) {
  const { user, loading: userLoading } = useSupabaseUser();

  if (userLoading) return null;

  if (!user) {
    return (
      <p className={styles.signInNotice}>
        <Link href="/login" className={styles.signInLink}>Sign in</Link> to save comparisons.
      </p>
    );
  }

  return <SignedInPanel userId={user.id} tickers={tickers} onLoad={onLoad} />;
}

function SignedInPanel({ userId, tickers, onLoad }: Props & { userId: string }) {
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const { data: comparisons = [], mutate } = useSWR<SavedComparison[]>(
    savedComparisonsKey(userId),
    () => listSavedComparisons(createClient(), userId),
  );

  const canSave = tickers.length >= 2;

  async function handleSave() {
    const trimmed = name.trim();
    if (!trimmed || !canSave) return;

    setSaving(true);
    setError(null);
    const result = await saveComparison(createClient(), userId, { name: trimmed, tickers });
    setSaving(false);

    if (result.status === 'duplicate') {
      setError(`You already have a comparison named "${trimmed}".`);
      return;
    }
    if (result.status === 'error') {
      setError(result.message);
      return;
    }

    setName('');
    mutate();
  }

  async function handleDelete(id: string) {
    setPendingIds((prev) => new Set(prev).add(id));
    await deleteSavedComparison(createClient(), id);
    mutate();
    setPendingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }

  return (
    <div className={styles.panel}>
      <div className={styles.saveRow}>
        <input
          type="text"
          className={styles.nameInput}
          placeholder={canSave ? 'Name this comparison' : 'Add 2+ tickers to save'}
          value={name}
          onChange={(e) => { setName(e.target.value); setError(null); }}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); }}
          disabled={saving || !canSave}
        />
        <button
          type="button"
          className={styles.saveButton}
          onClick={handleSave}
          disabled={saving || !canSave || !name.trim()}
        >
          Save current comparison
        </button>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {comparisons.length > 0 && (
        <div className={styles.list}>
          {comparisons.map((comparison) => (
            <div key={comparison.id} className={styles.row}>
              <span className={styles.comparisonName}>{comparison.name}</span>
              <span className={styles.tickersBadge}>{comparison.tickers.join(', ')}</span>
              <button
                type="button"
                className={styles.loadButton}
                onClick={() => onLoad(comparison.tickers)}
                disabled={pendingIds.has(comparison.id)}
              >
                Load
              </button>
              <button
                type="button"
                className={styles.deleteButton}
                onClick={() => handleDelete(comparison.id)}
                disabled={pendingIds.has(comparison.id)}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
