'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { fetchUniverse, fetchFundamentals } from '@/lib/api';
import type { UniverseConstituent, NormalizedFundamentals } from '@/lib/api';
import ScreenerTable from '@/components/screener/ScreenerTable';
import type { ScreenerRow, SortKey, SortDir } from '@/components/screener/ScreenerTable';
import styles from './page.module.css';

const UNIVERSES = [
  { key: 'dow30', label: 'DOW 30' },
  { key: 'nifty50', label: 'NIFTY 50' },
  { key: 'nasdaq100', label: 'NASDAQ-100' },
  { key: 'sp500', label: 'S&P 500' },
] as const;

type UniverseKey = (typeof UNIVERSES)[number]['key'];

const CONCURRENCY = 8;

type RowResult = NormalizedFundamentals | 'error';

interface Filters {
  marketCapMin: string;
  marketCapMax: string;
  peMin: string;
  peMax: string;
  netMarginMin: string;
  roeMin: string;
  debtToEquityMax: string;
  grossMarginMin: string;
  revenueMin: string;
  fcfPositive: boolean;
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
  fcfPositive: false,
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
            Large universe — may take 1-2 minutes to fully load. Rows fill in as data arrives.
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

          <div className={styles.filterGroup}>
            <label className={styles.filterCheckboxLabel}>
              <input type="checkbox" checked={filters.fcfPositive} onChange={e => updateFilter('fcfPositive', e.target.checked)} />
              Free Cash Flow &gt; 0
            </label>
          </div>

          <button className={styles.clearButton} onClick={() => setFilters(EMPTY_FILTERS)}>
            Clear filters
          </button>
        </div>

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
  const [constituents, setConstituents] = useState<UniverseConstituent[]>([]);
  const [universeLoading, setUniverseLoading] = useState(true);
  const [results, setResults] = useState<Record<string, RowResult>>({});

  useEffect(() => {
    let cancelled = false;

    fetchUniverse(universeKey)
      .then(list => {
        if (cancelled) return;
        setConstituents(list);
        setUniverseLoading(false);
        runPool(list.map(c => c.ticker));
      })
      .catch(() => {
        if (cancelled) return;
        setConstituents([]);
        setUniverseLoading(false);
      });

    function runPool(tickers: string[]) {
      let cursor = 0;
      let active = 0;

      function pump() {
        if (cancelled) return;
        while (active < CONCURRENCY && cursor < tickers.length) {
          const ticker = tickers[cursor++];
          active++;
          fetchFundamentals(ticker, 'annual', 1)
            .then(data => {
              if (cancelled) return;
              setResults(prev => ({ ...prev, [ticker]: data[0] ?? 'error' }));
            })
            .catch(() => {
              if (cancelled) return;
              setResults(prev => ({ ...prev, [ticker]: 'error' }));
            })
            .finally(() => {
              active--;
              pump();
            });
        }
      }
      pump();
    }

    return () => {
      cancelled = true;
    };
  }, [universeKey]);

  const anyFilterActive = useMemo(
    () => Object.entries(filters).some(([k, v]) => (k === 'fcfPositive' ? v === true : v !== '')),
    [filters],
  );

  const rows: ScreenerRow[] = useMemo(() => {
    return constituents.map(c => {
      const r = results[c.ticker];
      const status: ScreenerRow['status'] = r === undefined ? 'loading' : r === 'error' ? 'error' : 'loaded';
      return {
        ticker: c.ticker,
        name: c.name,
        status,
        data: status === 'loaded' ? (r as NormalizedFundamentals) : undefined,
      };
    });
  }, [constituents, results]);

  const filteredRows = useMemo(() => {
    if (!anyFilterActive) return rows;
    return rows.filter(row => {
      if (row.status !== 'loaded' || !row.data) return false;
      const ratios = row.data.ratios;
      const revenue = row.data.income_statement.revenue;
      const fcf = row.data.cash_flow.free_cash_flow;

      if (filters.marketCapMin && (ratios.market_cap ?? -Infinity) < Number(filters.marketCapMin) * 1e9) return false;
      if (filters.marketCapMax && (ratios.market_cap ?? Infinity) > Number(filters.marketCapMax) * 1e9) return false;
      if (filters.peMin && (ratios.pe_ratio ?? -Infinity) < Number(filters.peMin)) return false;
      if (filters.peMax && (ratios.pe_ratio ?? Infinity) > Number(filters.peMax)) return false;
      if (filters.netMarginMin && (ratios.net_margin ?? -Infinity) < Number(filters.netMarginMin) / 100) return false;
      if (filters.roeMin && (ratios.roe ?? -Infinity) < Number(filters.roeMin) / 100) return false;
      if (filters.debtToEquityMax && (ratios.debt_to_equity ?? Infinity) > Number(filters.debtToEquityMax)) return false;
      if (filters.grossMarginMin && (ratios.gross_margin ?? -Infinity) < Number(filters.grossMarginMin) / 100) return false;
      if (filters.revenueMin && (revenue ?? -Infinity) < Number(filters.revenueMin) * 1e6) return false;
      if (filters.fcfPositive && !(fcf != null && fcf > 0)) return false;

      return true;
    });
  }, [rows, filters, anyFilterActive]);

  const sortedRows = useMemo(() => {
    function metric(row: ScreenerRow): number | string | null {
      if (!row.data) return null;
      switch (sortKey) {
        case 'name': return row.name;
        case 'market_cap': return row.data.ratios.market_cap;
        case 'pe_ratio': return row.data.ratios.pe_ratio;
        case 'net_margin': return row.data.ratios.net_margin;
        case 'roe': return row.data.ratios.roe;
        case 'revenue': return row.data.income_statement.revenue;
        case 'gross_margin': return row.data.ratios.gross_margin;
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
        {universeLoading
          ? 'Loading universe…'
          : `${sortedRows.length} of ${constituents.length} stocks match`}
      </p>

      <ScreenerTable rows={sortedRows} sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
    </>
  );
}
