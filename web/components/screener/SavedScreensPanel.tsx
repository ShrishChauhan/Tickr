'use client';

import { useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { createClient } from '@/lib/supabase/client';
import { useSupabaseUser } from '@/lib/hooks/useSupabaseUser';
import { savedScreensKey } from '@/lib/swrKeys';
import { listSavedScreens, saveScreen, deleteSavedScreen } from '@/lib/savedScreens';
import type { SavedScreen } from '@/lib/savedScreens';
import styles from './SavedScreensPanel.module.css';

interface Props {
  universeKey: string;
  filters: Record<string, string>;
  onLoad: (universeKey: string, filters: Record<string, string>) => void;
}

export default function SavedScreensPanel({ universeKey, filters, onLoad }: Props) {
  const { user, loading: userLoading } = useSupabaseUser();

  if (userLoading) return null;

  if (!user) {
    return (
      <p className={styles.signInNotice}>
        <Link href="/login" className={styles.signInLink}>Sign in</Link> to save screens.
      </p>
    );
  }

  return <SignedInPanel userId={user.id} universeKey={universeKey} filters={filters} onLoad={onLoad} />;
}

function SignedInPanel({ userId, universeKey, filters, onLoad }: Props & { userId: string }) {
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const { data: screens = [], mutate } = useSWR<SavedScreen[]>(
    savedScreensKey(userId),
    () => listSavedScreens(createClient(), userId),
  );

  async function handleSave() {
    const trimmed = name.trim();
    if (!trimmed) return;

    setSaving(true);
    setError(null);
    const result = await saveScreen(createClient(), userId, { name: trimmed, universeKey, filters });
    setSaving(false);

    if (result.status === 'duplicate') {
      setError(`You already have a screen named "${trimmed}".`);
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
    await deleteSavedScreen(createClient(), id);
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
          placeholder="Name this screen"
          value={name}
          onChange={(e) => { setName(e.target.value); setError(null); }}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); }}
          disabled={saving}
        />
        <button
          type="button"
          className={styles.saveButton}
          onClick={handleSave}
          disabled={saving || !name.trim()}
        >
          Save current screen
        </button>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {screens.length > 0 && (
        <div className={styles.list}>
          {screens.map((screen) => (
            <div key={screen.id} className={styles.row}>
              <span className={styles.screenName}>{screen.name}</span>
              <span className={styles.universeBadge}>{screen.universe_key}</span>
              <button
                type="button"
                className={styles.loadButton}
                onClick={() => onLoad(screen.universe_key, screen.filters)}
                disabled={pendingIds.has(screen.id)}
              >
                Load
              </button>
              <button
                type="button"
                className={styles.deleteButton}
                onClick={() => handleDelete(screen.id)}
                disabled={pendingIds.has(screen.id)}
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
