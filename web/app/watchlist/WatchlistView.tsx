'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { createClient } from '@/lib/supabase/client';
import { getOrCreateTag, ASSET_TYPE_GROUP_LABELS } from '@/lib/watchlist';
import type { WatchlistItem } from '@/lib/watchlist';
import styles from './WatchlistView.module.css';

interface Props {
  initialItems: WatchlistItem[];
  userId: string;
}

export default function WatchlistView({ initialItems, userId }: Props) {
  const router = useRouter();
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const [tagInputs, setTagInputs] = useState<Record<string, string>>({});

  const allTagNames = useMemo(() => {
    const names = new Set<string>();
    for (const item of initialItems) {
      for (const tag of item.tags) names.add(tag.name);
    }
    return Array.from(names).sort();
  }, [initialItems]);

  const filteredItems = useMemo(() => {
    if (selectedTags.size === 0) return initialItems;
    return initialItems.filter((item) => item.tags.some((tag) => selectedTags.has(tag.name)));
  }, [initialItems, selectedTags]);

  const grouped = useMemo(() => {
    const groups = new Map<string, WatchlistItem[]>();
    for (const item of filteredItems) {
      const list = groups.get(item.asset_type) ?? [];
      list.push(item);
      groups.set(item.asset_type, list);
    }
    return groups;
  }, [filteredItems]);

  function toggleTag(name: string) {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function setPending(id: string, isPending: boolean) {
    setPendingIds((prev) => {
      const next = new Set(prev);
      if (isPending) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function handleRemove(itemId: string) {
    setPending(itemId, true);
    const supabase = createClient();
    await supabase.from('watchlist_items').delete().eq('id', itemId);
    router.refresh();
  }

  async function handleAddTag(itemId: string) {
    const raw = tagInputs[itemId]?.trim();
    if (!raw) return;

    setPending(itemId, true);
    const supabase = createClient();
    const tagId = await getOrCreateTag(supabase, userId, raw, false);
    if (tagId) {
      await supabase.from('watchlist_item_tags').insert({ item_id: itemId, tag_id: tagId });
    }
    setTagInputs((prev) => ({ ...prev, [itemId]: '' }));
    router.refresh();
  }

  if (initialItems.length === 0) {
    return (
      <div className={styles.empty}>
        <p>No assets tracked yet — search for a ticker and add it to your watchlist.</p>
        <Link href="/" className={styles.emptyLink}>
          Go to search
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      {allTagNames.length > 0 && (
        <div className={styles.filterRow}>
          {allTagNames.map((name) => (
            <button
              key={name}
              type="button"
              className={`${styles.filterPill} ${selectedTags.has(name) ? styles.filterPillActive : ''}`}
              onClick={() => toggleTag(name)}
            >
              {name}
            </button>
          ))}
        </div>
      )}

      {Array.from(grouped.entries()).map(([assetType, items]) => (
        <section key={assetType} className={styles.section}>
          <h2 className={styles.sectionTitle}>
            {ASSET_TYPE_GROUP_LABELS[assetType] ?? assetType}
          </h2>
          <div className={styles.itemList}>
            {items.map((item) => (
              <div key={item.id} className={styles.itemRow}>
                <div className={styles.itemMain}>
                  <Link href={`/company/${item.ticker}`} className={styles.itemTicker}>
                    {item.ticker}
                  </Link>
                  <span className={styles.itemName}>{item.display_name}</span>
                </div>

                <div className={styles.itemTags}>
                  {item.tags.map((tag) => (
                    <span
                      key={tag.id}
                      className={`${styles.tagPill} ${tag.is_auto_derived ? styles.tagPillAuto : styles.tagPillCustom}`}
                    >
                      {tag.name}
                    </span>
                  ))}
                  <input
                    type="text"
                    className={styles.tagInput}
                    placeholder="+ add tag"
                    value={tagInputs[item.id] ?? ''}
                    onChange={(e) => setTagInputs((prev) => ({ ...prev, [item.id]: e.target.value }))}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        handleAddTag(item.id);
                      }
                    }}
                    disabled={pendingIds.has(item.id)}
                  />
                </div>

                <button
                  type="button"
                  className={styles.removeButton}
                  onClick={() => handleRemove(item.id)}
                  disabled={pendingIds.has(item.id)}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
