'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import useSWR, { preload } from 'swr';
import styles from './SearchBar.module.css';
import { fetchSearch, fetchCompany, fetchFundamentals, fetchFilings, fetchPriceOnly, SearchResult } from '../../lib/api';
import { searchKey, companyKey, fundamentalsKey, filingsKey, priceOnlyKey } from '../../lib/swrKeys';

const TICKER_RE = /^[A-Z0-9.=^-]{1,16}$/;

const ASSET_TYPE_LABEL: Record<string, string> = {
  equity: 'Stock', crypto: 'Crypto', forex: 'Forex',
  commodity: 'Futures', index: 'Index', etf: 'ETF', fund: 'Fund',
};

export default function SearchBar() {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [highlighted, setHighlighted] = useState(-1);
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: results = [], isLoading: loading } = useSWR<SearchResult[]>(
    debouncedQuery.trim() ? searchKey(debouncedQuery) : null,
    () => fetchSearch(debouncedQuery),
    { keepPreviousData: true },
  );

  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, []);

  // Only re-open on a new committed query (debouncedQuery changing), not on every
  // background SWR revalidation of the same key (e.g. window refocus) — otherwise
  // a dismissed dropdown could silently reopen with stale results.
  useEffect(() => {
    if (debouncedQuery.trim() !== '') {
      setOpen(true);
      setHighlighted(-1);
    }
  }, [debouncedQuery]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const newValue = e.target.value;
    setValue(newValue);
    if (error) setError(null);

    if (!newValue.trim()) {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setDebouncedQuery('');
      setOpen(false);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(newValue.trim());
    }, 300);
  }

  function prefetchResult(r: SearchResult) {
    preload(companyKey(r.ticker), () => fetchCompany(r.ticker));
    if (r.asset_type === 'equity') {
      preload(fundamentalsKey(r.ticker), () => fetchFundamentals(r.ticker));
      preload(filingsKey(r.ticker), () => fetchFilings(r.ticker));
    } else {
      preload(priceOnlyKey(r.ticker), () => fetchPriceOnly(r.ticker));
    }
  }

  function selectResult(r: SearchResult) {
    setValue(r.ticker);
    setOpen(false);
    setDebouncedQuery('');
    setError(null);
    router.push(`/company/${r.ticker}`);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    e.stopPropagation();

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlighted(prev => Math.min(prev + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted(prev => Math.max(prev - 1, -1));
    } else if (e.key === 'Escape') {
      setOpen(false);
    } else if (e.key === 'Enter' && highlighted >= 0) {
      e.preventDefault();
      selectResult(results[highlighted]);
    }
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const ticker = value.trim().toUpperCase();

    if (!ticker) {
      setError('Enter a ticker symbol');
      return;
    }
    if (!TICKER_RE.test(ticker)) {
      setError('Invalid ticker format');
      return;
    }

    setError(null);
    setOpen(false);
    router.push(`/company/${ticker}`);
  }

  const showDropdown = (open || loading) && value.trim() !== '';

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <form
        className={styles.bar}
        onSubmit={handleSubmit}
        role="search"
        aria-label="Stock search"
      >
        <span className={styles.icon} aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" />
            <line
              x1="10.5" y1="10.5" x2="14" y2="14"
              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
            />
          </svg>
        </span>

        <input
          className={styles.input}
          type="text"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Search any stock…"
          aria-label="Ticker symbol"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={16}
        />

        {error && (
          <span className={styles.errorHint} role="alert">
            {error}
          </span>
        )}
      </form>

      {showDropdown && (
        <div className={styles.dropdown}>
          {loading && <div className={styles.dropdownLoading}>Searching…</div>}
          {!loading && results.map((r, i) => (
            <div
              key={r.ticker}
              className={
                i === highlighted
                  ? `${styles.dropdownRow} ${styles.dropdownRowHighlighted}`
                  : styles.dropdownRow
              }
              onMouseDown={() => selectResult(r)}
              onMouseEnter={() => prefetchResult(r)}
            >
              <span className={styles.dropdownTicker}>{r.ticker}</span>
              <span className={styles.dropdownName}>{r.name}</span>
              <span className={styles.dropdownTags}>
                {r.exchange && <span className={styles.dropdownTag}>{r.exchange}</span>}
                <span className={styles.dropdownTag}>{ASSET_TYPE_LABEL[r.asset_type] ?? r.asset_type}</span>
                {r.sector && <span className={styles.dropdownTag}>{r.sector}</span>}
              </span>
            </div>
          ))}
          {!loading && results.length === 0 && open && (
            <div className={styles.dropdownEmpty}>No results for &ldquo;{value}&rdquo;</div>
          )}
        </div>
      )}
    </div>
  );
}
