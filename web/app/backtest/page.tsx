'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { fetchSearch, fetchBacktest, ApiError } from '@/lib/api';
import type { SearchResult, IndicatorSchema, RuleSchema, StrategySchema, BacktestResponse } from '@/lib/api';
import { searchKey } from '@/lib/swrKeys';
import RuleBuilder from '@/components/backtest/RuleBuilder';
import EquityCurveChart from '@/components/backtest/EquityCurveChart';
import SummaryStatsCards from '@/components/backtest/SummaryStatsCards';
import MethodologyLine from '@/components/backtest/MethodologyLine';
import TradeTable from '@/components/backtest/TradeTable';
import resultStyles from '@/components/backtest/results.module.css';
import styles from './page.module.css';

const COST_PCT = 0.001;
const STARTING_CAPITAL = 100_000;

type RunState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; result: BacktestResponse };

function isIndicatorValid(indicator: IndicatorSchema): boolean {
  if (indicator.type === 'PRICE') return true;
  return indicator.window != null && indicator.window >= 1;
}

function isRuleValid(rule: RuleSchema): boolean {
  if (!isIndicatorValid(rule.left)) return false;
  if (typeof rule.right === 'number') return !Number.isNaN(rule.right);
  return isIndicatorValid(rule.right);
}

function isStrategyValid(ticker: string | null, strategy: StrategySchema): boolean {
  return ticker != null && isRuleValid(strategy.entry) && isRuleValid(strategy.exit);
}

// Native <input type="date"> maps click position to a specific day/month/year
// segment, and segment focus only auto-advances forward. On an empty field
// whose rendered width leaves the calendar-icon hit zone dominating the
// clickable area, a plain click lands on a later segment (e.g. year), so
// typing digits can never reach the earlier (day/month) segments — the field
// looks unresponsive. Force focus to the first segment on empty fields only,
// so editing an already-filled date by clicking a specific segment still works.
function handleEmptyDateMouseDown(e: React.MouseEvent<HTMLInputElement>) {
  const input = e.currentTarget;
  if (input.value) return;
  const rect = input.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const iconZoneStart = rect.width - 28; // approx. calendar-picker-indicator width
  if (clickX < iconZoneStart) {
    e.preventDefault();
    input.focus();
  }
}

const DEFAULT_STRATEGY: StrategySchema = {
  entry: {
    left: { type: 'SMA', window: null },
    comparator: 'CROSSES_ABOVE',
    right: { type: 'SMA', window: null },
  },
  exit: {
    left: { type: 'SMA', window: null },
    comparator: 'CROSSES_BELOW',
    right: { type: 'SMA', window: null },
  },
};

export default function BacktestPage() {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [strategy, setStrategy] = useState<StrategySchema>(DEFAULT_STRATEGY);
  const [runState, setRunState] = useState<RunState>({ kind: 'idle' });

  const containerRef = useRef<HTMLDivElement>(null);

  const { data: results = [] } = useSWR<SearchResult[]>(
    debouncedQuery ? searchKey(debouncedQuery) : null,
    () => fetchSearch(debouncedQuery),
    { keepPreviousData: true },
  );

  useEffect(() => {
    if (!query.trim()) { setDebouncedQuery(''); setDropdownOpen(false); return; }
    const tid = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => clearTimeout(tid);
  }, [query]);

  useEffect(() => {
    if (debouncedQuery) setDropdownOpen(true);
  }, [debouncedQuery]);

  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, []);

  function selectTicker(ticker: string) {
    setSelectedTicker(ticker.toUpperCase());
    setQuery('');
    setDropdownOpen(false);
  }

  const canSubmit = isStrategyValid(selectedTicker, strategy);

  function runBacktest() {
    if (!selectedTicker || !canSubmit) return;
    setRunState({ kind: 'loading' });
    fetchBacktest(selectedTicker, {
      strategy,
      cost_pct: COST_PCT,
      starting_capital: STARTING_CAPITAL,
      start: startDate || null,
      end: endDate || null,
    }).then(
      result => setRunState({ kind: 'success', result }),
      err => {
        if (err instanceof ApiError && err.status === 404) {
          setRunState({ kind: 'error', message: `No historical data for ${selectedTicker}.` });
        } else if (err instanceof ApiError && err.status === 400) {
          setRunState({ kind: 'error', message: err.message || 'Invalid strategy configuration.' });
        } else {
          setRunState({ kind: 'error', message: 'Failed to run backtest. Please try again.' });
        }
      },
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <Link href="/" className={styles.back}>← Back</Link>

        <div className={styles.header}>
          <h1 className={styles.title}>Backtest</h1>
          <p className={styles.subtitle}>Build an entry/exit rule and run it against local historical data</p>
        </div>

        {/* ── Ticker typeahead ──────────────────────────────────────────────── */}
        {!selectedTicker ? (
          <div className={styles.inputWrapper} ref={containerRef}>
            <input
              className={styles.tickerInput}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onFocus={() => results.length > 0 && setDropdownOpen(true)}
              placeholder="Search ticker…"
              maxLength={16}
              autoComplete="off"
              spellCheck={false}
            />
            {dropdownOpen && results.length > 0 && (
              <div className={styles.dropdown}>
                {results.map(r => (
                  <button
                    key={r.ticker}
                    className={styles.dropdownItem}
                    onMouseDown={() => selectTicker(r.ticker)}
                  >
                    <span className={styles.dropdownTicker}>{r.ticker}</span>
                    <span className={styles.dropdownName}>{r.name}</span>
                    {r.asset_type && <span className={styles.dropdownBadge}>{r.asset_type}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className={styles.tickerChip}>
            <span className={styles.chipLabel}>{selectedTicker}</span>
            <button type="button" className={styles.changeButton} onClick={() => setSelectedTicker(null)}>
              Change
            </button>
          </div>
        )}

        {/* ── Date range ────────────────────────────────────────────────────── */}
        <div className={styles.dateRow}>
          <div className={styles.selectGroup}>
            <label className={styles.selectLabel}>Start (optional)</label>
            <input
              className={styles.dateInput}
              type="date"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
              onMouseDown={handleEmptyDateMouseDown}
            />
          </div>
          <div className={styles.selectGroup}>
            <label className={styles.selectLabel}>End (optional)</label>
            <input
              className={styles.dateInput}
              type="date"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
              onMouseDown={handleEmptyDateMouseDown}
            />
          </div>
        </div>

        {/* ── Rule builders ─────────────────────────────────────────────────── */}
        <div className={styles.rules}>
          <RuleBuilder
            title="Entry Rule"
            value={strategy.entry}
            onChange={entry => setStrategy(s => ({ ...s, entry }))}
          />
          <RuleBuilder
            title="Exit Rule"
            value={strategy.exit}
            onChange={exit => setStrategy(s => ({ ...s, exit }))}
          />
        </div>

        {/* ── Submit ────────────────────────────────────────────────────────── */}
        <div className={styles.submitRow}>
          <button
            type="button"
            className={styles.runButton}
            disabled={!canSubmit || runState.kind === 'loading'}
            onClick={runBacktest}
          >
            {runState.kind === 'loading' ? 'Running…' : 'Run Backtest'}
          </button>
          {!canSubmit && (
            <p className={styles.submitHint}>
              Select a ticker and fill in both rules (window required for SMA/RSI) to enable.
            </p>
          )}
        </div>

        {/* ── Results ──────────────────────────────────────────────────────── */}
        {runState.kind === 'error' && (
          <p className={styles.submitHint}>{runState.message}</p>
        )}

        {runState.kind === 'success' && (
          <div className={resultStyles.resultsSection}>
            <h2 className={resultStyles.sectionTitle}>Results</h2>
            <SummaryStatsCards result={runState.result} />
            <EquityCurveChart result={runState.result} />
            <TradeTable trades={runState.result.trades} />
            <MethodologyLine
              result={runState.result}
              costPct={COST_PCT}
              startingCapital={STARTING_CAPITAL}
            />
          </div>
        )}
      </div>
    </main>
  );
}
