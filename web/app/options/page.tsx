'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import {
  fetchSearch,
  fetchOptionExpirations,
  fetchOptionChain,
  fetchOptionCalculation,
} from '@/lib/api';
import type { SearchResult, OptionContract, GreeksResult } from '@/lib/api';
import {
  searchKey,
  optionExpirationsKey,
  optionChainKey,
  optionCalculationKey,
} from '@/lib/swrKeys';
import styles from './page.module.css';

type OptionType = 'call' | 'put';

const GREEK_ROWS: { key: keyof GreeksResult; label: string; explanationKey: keyof GreeksResult['explanations'] }[] = [
  { key: 'delta', label: 'Delta', explanationKey: 'delta' },
  { key: 'gamma', label: 'Gamma', explanationKey: 'gamma' },
  { key: 'theta_per_day', label: 'Theta (per day)', explanationKey: 'theta' },
  { key: 'vega', label: 'Vega', explanationKey: 'vega' },
  { key: 'rho_per_percent', label: 'Rho (per 1%)', explanationKey: 'rho' },
];

export default function OptionsPage() {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [selectedExpiration, setSelectedExpiration] = useState<string | null>(null);
  const [optionType, setOptionType] = useState<OptionType>('call');
  const [selectedStrike, setSelectedStrike] = useState<number | null>(null);
  const [ivInput, setIvInput] = useState('');

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
    setSelectedExpiration(null);
    setSelectedStrike(null);
    setIvInput('');
  }

  const { data: expirationsData, isLoading: expirationsLoading } = useSWR(
    selectedTicker ? optionExpirationsKey(selectedTicker) : null,
    () => fetchOptionExpirations(selectedTicker!),
  );

  function selectExpiration(expiration: string) {
    setSelectedExpiration(expiration);
    setSelectedStrike(null);
    setIvInput('');
  }

  const { data: chainData, isLoading: chainLoading } = useSWR(
    selectedTicker && selectedExpiration ? optionChainKey(selectedTicker, selectedExpiration) : null,
    () => fetchOptionChain(selectedTicker!, selectedExpiration!),
  );

  const contracts: OptionContract[] = optionType === 'call' ? chainData?.calls ?? [] : chainData?.puts ?? [];
  const sortedContracts = [...contracts].sort((a, b) => a.strike - b.strike);
  const selectedContract = sortedContracts.find(c => c.strike === selectedStrike) ?? null;

  function selectType(type: OptionType) {
    setOptionType(type);
    setSelectedStrike(null);
    setIvInput('');
  }

  function selectStrike(strike: number) {
    setSelectedStrike(strike);
    const contract = contracts.find(c => c.strike === strike);
    setIvInput(
      contract?.implied_volatility != null ? (contract.implied_volatility * 100).toFixed(2) : '',
    );
  }

  const ivDecimal = ivInput.trim() === '' ? NaN : Number(ivInput) / 100;
  const canCalculate =
    selectedTicker != null && selectedExpiration != null && selectedStrike != null && !Number.isNaN(ivDecimal);

  const { data: result, isLoading: calculating } = useSWR<GreeksResult>(
    canCalculate
      ? optionCalculationKey(selectedTicker!, selectedExpiration!, selectedStrike!, optionType, ivDecimal)
      : null,
    () => fetchOptionCalculation(selectedTicker!, selectedExpiration!, selectedStrike!, optionType, ivDecimal),
  );

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <Link href="/" className={styles.back}>← Back</Link>

        <div className={styles.header}>
          <h1 className={styles.title}>Options</h1>
          <p className={styles.subtitle}>Black-Scholes pricing and Greeks for US-listed equity/ETF options</p>
        </div>

        {/* ── Ticker typeahead ──────────────────────────────────────────────── */}
        {!selectedTicker ? (
          <div className={styles.inputWrapper} ref={containerRef}>
            <input
              className={styles.tickerInput}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onFocus={() => results.length > 0 && setDropdownOpen(true)}
              placeholder="Search ticker (equities/ETFs only)…"
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
            <button
              type="button"
              className={styles.changeButton}
              onClick={() => {
                setSelectedTicker(null);
                setSelectedExpiration(null);
                setSelectedStrike(null);
                setIvInput('');
              }}
            >
              Change
            </button>
          </div>
        )}

        {selectedTicker && expirationsLoading && (
          <p className={styles.notice}>Loading expirations for {selectedTicker}…</p>
        )}

        {selectedTicker && expirationsData && !expirationsData.available && (
          <div className={styles.emptyState}>
            <p className={styles.emptyText}>
              Options data not available for this ticker — currently supported for US-listed equities and ETFs only.
            </p>
          </div>
        )}

        {selectedTicker && expirationsData?.available && (
          <div className={styles.selectRow}>
            <div className={styles.selectGroup}>
              <label className={styles.selectLabel}>Expiration</label>
              <select
                className={styles.select}
                value={selectedExpiration ?? ''}
                onChange={e => selectExpiration(e.target.value)}
              >
                <option value="" disabled>Select expiration…</option>
                {expirationsData.expirations.map(exp => (
                  <option key={exp} value={exp}>{exp}</option>
                ))}
              </select>
            </div>

            <div className={styles.selectGroup}>
              <label className={styles.selectLabel}>Type</label>
              <div className={styles.toggle}>
                <button
                  type="button"
                  className={`${styles.toggleButton} ${optionType === 'call' ? styles.toggleButtonActive : ''}`}
                  onClick={() => selectType('call')}
                >
                  Call
                </button>
                <button
                  type="button"
                  className={`${styles.toggleButton} ${optionType === 'put' ? styles.toggleButtonActive : ''}`}
                  onClick={() => selectType('put')}
                >
                  Put
                </button>
              </div>
            </div>

            {selectedExpiration && (
              <div className={styles.selectGroup}>
                <label className={styles.selectLabel}>Strike</label>
                <select
                  className={styles.select}
                  value={selectedStrike ?? ''}
                  onChange={e => selectStrike(Number(e.target.value))}
                  disabled={chainLoading || sortedContracts.length === 0}
                >
                  <option value="" disabled>
                    {chainLoading ? 'Loading…' : 'Select strike…'}
                  </option>
                  {sortedContracts.map(c => (
                    <option key={c.strike} value={c.strike}>{c.strike}</option>
                  ))}
                </select>
              </div>
            )}

            {selectedContract && (
              <div className={styles.selectGroup}>
                <label className={styles.selectLabel}>Implied Volatility (%)</label>
                <input
                  className={styles.select}
                  type="number"
                  step="0.01"
                  value={ivInput}
                  onChange={e => setIvInput(e.target.value)}
                  placeholder="e.g. 25.00"
                />
              </div>
            )}
          </div>
        )}

        {/* ── Results ────────────────────────────────────────────────────────── */}
        {canCalculate && calculating && <p className={styles.notice}>Calculating…</p>}

        {result && (
          <div className={styles.resultCard}>
            <div className={styles.priceRow}>
              <span className={styles.priceLabel}>Theoretical price</span>
              <span className={styles.priceValue}>${result.price.toFixed(2)}</span>
            </div>

            <div className={styles.greeksGrid}>
              {GREEK_ROWS.map(row => (
                <div key={row.key} className={styles.greekRow}>
                  <div className={styles.greekHeader}>
                    <span className={styles.greekLabel}>{row.label}</span>
                    <span className={styles.greekValue}>{(result[row.key] as number).toFixed(4)}</span>
                  </div>
                  <p className={styles.greekExplanation}>{result.explanations[row.explanationKey]}</p>
                </div>
              ))}
            </div>

            <div className={styles.freshnessLine}>
              <p>
                S={result.inputs_used.S.toFixed(2)} · K={result.inputs_used.K.toFixed(2)} ·
                {' '}T={result.inputs_used.T.toFixed(4)} · r={(result.inputs_used.r * 100).toFixed(2)}% ·
                {' '}q={(result.inputs_used.q * 100).toFixed(2)}% · σ={(result.inputs_used.sigma * 100).toFixed(2)}%
              </p>
              <p>
                Price as of {result.inputs_used.price_as_of} · IV as of {result.inputs_used.iv_as_of} ·
                {' '}rate as of {result.inputs_used.r_as_of} ({result.inputs_used.r_source})
                {result.inputs_used.contract_last_trade_at &&
                  ` · contract last traded ${result.inputs_used.contract_last_trade_at}`}
              </p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
