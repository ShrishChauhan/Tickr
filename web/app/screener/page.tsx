'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { fetchScreenerRows } from '@/lib/api';
import { screenerKey } from '@/lib/swrKeys';
import { screenerConfig } from '@/lib/swrConfig';
import ScreenerTable from '@/components/screener/ScreenerTable';
import type { ScreenerRow, SortKey, SortDir } from '@/components/screener/ScreenerTable';
import SavedScreensPanel from '@/components/screener/SavedScreensPanel';
import styles from './page.module.css';

const UNIVERSES = [
  { key: 'dow30', label: 'DOW 30' },
  { key: 'nifty50', label: 'NIFTY 50' },
  { key: 'nasdaq100', label: 'NASDAQ-100' },
  { key: 'sp500', label: 'S&P 500' },
] as const;

type UniverseKey = (typeof UNIVERSES)[number]['key'];

// No FCF filter — the batch screener endpoint's lite fetch has no .info equivalent for free cash flow.
interface Filters {
  // Index signature so this structurally satisfies Record<string, string> (e.g. SavedScreensPanel's props) without a cast.
  [key: string]: string;
  marketCapMin: string;
  marketCapMax: string;
  peMin: string;
  peMax: string;
  netMarginMin: string;
  roeMin: string;
  debtToEquityMax: string;
  grossMarginMin: string;
  revenueMin: string;
}

const EMPTY_FILTERS: Filters = {
  marketCapMin: '',
  marketCapMax: '',
  peMin: '',
  peMax: '',
  netMarginMin: '',
  roeMin: '',
  debtToEquityMax: '',
  grossMarginMin: '',
  revenueMin: '',
};

function currencySymbolForUniverse(key: UniverseKey): string {
  return key === 'nifty50' ? '₹' : '$';
}

export default function ScreenerPage() {
  const [universeKey, setUniverseKey] = useState<UniverseKey>('dow30');
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sortKey, setSortKey] = useState<SortKey>('market_cap');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  function updateFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters(prev => ({ ...prev, [key]: value }));
  }

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir(prev => (prev === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  function handleLoadScreen(loadedUniverseKey: string, loadedFilters: Record<string, string>) {
    if (UNIVERSES.some(u => u.key === loadedUniverseKey)) {
      setUniverseKey(loadedUniverseKey as UniverseKey);
    }
    setFilters({ ...EMPTY_FILTERS, ...loadedFilters } as Filters);
    setSortKey('market_cap');
    setSortDir('desc');
  }

  const sym = currencySymbolForUniverse(universeKey);

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <Link href="/" className={styles.back}>← Back</Link>

        <div className={styles.header}>
          <h1 className={styles.title}>Screener</h1>
          <p className={styles.subtitle}>Filter index constituents by fundamentals</p>
        </div>

        <div className={styles.tabs}>
          {UNIVERSES.map(u => (
            <button
              key={u.key}
              className={`${styles.tab} ${universeKey === u.key ? styles.tabActive : ''}`}
              onClick={() => setUniverseKey(u.key)}
            >
              {u.label}
            </button>
          ))}
        </div>

        {universeKey === 'sp500' && (
          <p className={styles.notice}>
            Large universe — first load can take up to 2 minutes. Subsequent loads are fast (cached).
          </p>
        )}

        <div className={styles.filterPanel}>
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>Market Cap ({sym}B)</label>
            <div className={styles.filterRow}>
              <input className={styles.filterInput} type="number" placeholder="Min" value={filters.marketCapMin} onChange={e => updateFilter('marketCapMin', e.target.value)} />
              <input className={styles.filterInput} type="number" placeholder="Max" value={filters.marketCapMax} onChange={e => updateFilter('marketCapMax', e.target.value)} />
            </div>
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>P/E Ratio</label>
            <div className={styles.filterRow}>
              <input className={styles.filterInput} type="number" placeholder="Min" value={filters.peMin} onChange={e => updateFilter('peMin', e.target.value)} />
              <input className={styles.filterInput} type="number" placeholder="Max" value={filters.peMax} onChange={e => updateFilter('peMax', e.target.value)} />
            </div>
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>Net Margin % (min)</label>
            <input className={styles.filterInput} type="number" placeholder="e.g. 10" value={filters.netMarginMin} onChange={e => updateFilter('netMarginMin', e.target.value)} />
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>ROE % (min)</label>
            <input className={styles.filterInput} type="number" placeholder="e.g. 15" value={filters.roeMin} onChange={e => updateFilter('roeMin', e.target.value)} />
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>Debt / Equity (max)</label>
            <input className={styles.filterInput} type="number" placeholder="e.g. 1.5" value={filters.debtToEquityMax} onChange={e => updateFilter('debtToEquityMax', e.target.value)} />
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>Gross Margin % (min)</label>
            <input className={styles.filterInput} type="number" placeholder="e.g. 30" value={filters.grossMarginMin} onChange={e => updateFilter('grossMarginMin', e.target.value)} />
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>Revenue ({sym}M, min)</label>
            <input className={styles.filterInput} type="number" placeholder="Min" value={filters.revenueMin} onChange={e => updateFilter('revenueMin', e.target.value)} />
          </div>

          <button className={styles.clearButton} onClick={() => setFilters(EMPTY_FILTERS)}>
            Clear filters
          </button>
        </div>

        <SavedScreensPanel universeKey={universeKey} filters={filters} onLoad={handleLoadScreen} />

        {/* Keyed on universeKey so switching tabs remounts with fresh state
            instead of manually resetting fetched data inside an effect. */}
        <ScreenerResults
          key={universeKey}
          universeKey={universeKey}
          filters={filters}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={handleSort}
        />
      </div>
    </main>
  );
}

interface ScreenerResultsProps {
  universeKey: UniverseKey;
  filters: Filters;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}

function ScreenerResults({ universeKey, filters, sortKey, sortDir, onSort }: ScreenerResultsProps) {
  const { data: rows = [], isLoading: rowsLoading } = useSWR<ScreenerRow[]>(
    screenerKey(universeKey),
    () => fetchScreenerRows(universeKey),
    screenerConfig,
  );

  const anyFilterActive = useMemo(
    () => Object.values(filters).some(v => v !== ''),
    [filters],
  );

  const filteredRows = useMemo(() => {
    if (!anyFilterActive) return rows;
    return rows.filter(row => {
      if (filters.marketCapMin && (row.market_cap ?? -Infinity) < Number(filters.marketCapMin) * 1e9) return false;
      if (filters.marketCapMax && (row.market_cap ?? Infinity) > Number(filters.marketCapMax) * 1e9) return false;
      if (filters.peMin && (row.pe_ratio ?? -Infinity) < Number(filters.peMin)) return false;
      if (filters.peMax && (row.pe_ratio ?? Infinity) > Number(filters.peMax)) return false;
      if (filters.netMarginMin && (row.net_margin ?? -Infinity) < Number(filters.netMarginMin) / 100) return false;
      if (filters.roeMin && (row.roe ?? -Infinity) < Number(filters.roeMin) / 100) return false;
      if (filters.debtToEquityMax && (row.debt_to_equity ?? Infinity) > Number(filters.debtToEquityMax)) return false;
      if (filters.grossMarginMin && (row.gross_margin ?? -Infinity) < Number(filters.grossMarginMin) / 100) return false;
      if (filters.revenueMin && (row.revenue ?? -Infinity) < Number(filters.revenueMin) * 1e6) return false;

      return true;
    });
  }, [rows, filters, anyFilterActive]);

  const sortedRows = useMemo(() => {
    function metric(row: ScreenerRow): number | string | null {
      switch (sortKey) {
        case 'name': return row.name;
        case 'market_cap': return row.market_cap;
        case 'pe_ratio': return row.pe_ratio;
        case 'net_margin': return row.net_margin;
        case 'roe': return row.roe;
        case 'revenue': return row.revenue;
        case 'gross_margin': return row.gross_margin;
      }
    }

    const withValue = filteredRows.filter(r => metric(r) != null);
    const withoutValue = filteredRows.filter(r => metric(r) == null);

    withValue.sort((a, b) => {
      const av = metric(a)!;
      const bv = metric(b)!;
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortDir === 'desc' ? -cmp : cmp;
    });

    return [...withValue, ...withoutValue];
  }, [filteredRows, sortKey, sortDir]);

  return (
    <>
      <p className={styles.countLabel}>
        {rowsLoading
          ? 'Loading…'
          : `${sortedRows.length} of ${rows.length} stocks match`}
      </p>

      {rowsLoading ? (
        <p className={styles.notice}>Fetching {universeKey.toUpperCase()} constituents…</p>
      ) : (
        <ScreenerTable rows={sortedRows} sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
      )}
    </>
  );
}
