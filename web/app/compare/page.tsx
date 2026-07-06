'use client';

import { useState, useEffect, useRef, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Legend,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { fetchSearch, fetchCompany, fetchFundamentals } from '@/lib/api';
import type { NormalizedFundamentals, SearchResult } from '@/lib/api';
import { searchKey } from '@/lib/swrKeys';
import { getCurrencySymbol, fmtDollar, fmtPct, fmtMultiple } from '@/lib/format';
import styles from './page.module.css';

// ─── Constants ────────────────────────────────────────────────────────────────

const SERIES_COLORS = ['#2BFF88', '#6366F1', '#F59E0B', '#22D3EE', '#A78BFA'];

const RADAR_METRICS = [
  { key: 'gross_margin',     label: 'Gross Margin' },
  { key: 'operating_margin', label: 'Op. Margin' },
  { key: 'net_margin',       label: 'Net Margin' },
  { key: 'roe',              label: 'ROE' },
  { key: 'roa',              label: 'ROA' },
];

// ─── Table definition ─────────────────────────────────────────────────────────

type TableMetric = {
  label: string;
  getValue: (f: NormalizedFundamentals) => number | null | undefined;
  format: (v: number | null | undefined, sym: string) => string;
  higherIsBetter?: boolean;
};

type TableSection = {
  title: string;
  metrics: TableMetric[];
};

const TABLE_SECTIONS: TableSection[] = [
  {
    title: 'Income Statement',
    metrics: [
      { label: 'Revenue',          getValue: f => f.income_statement.revenue,          format: (v, s) => fmtDollar(v, s) },
      { label: 'Gross Profit',     getValue: f => f.income_statement.gross_profit,     format: (v, s) => fmtDollar(v, s), higherIsBetter: true },
      { label: 'Operating Income', getValue: f => f.income_statement.operating_income, format: (v, s) => fmtDollar(v, s), higherIsBetter: true },
      { label: 'Net Income',       getValue: f => f.income_statement.net_income,       format: (v, s) => fmtDollar(v, s), higherIsBetter: true },
    ],
  },
  {
    title: 'Margins',
    metrics: [
      { label: 'Gross Margin',     getValue: f => f.ratios.gross_margin,     format: (v) => fmtPct(v), higherIsBetter: true },
      { label: 'Operating Margin', getValue: f => f.ratios.operating_margin, format: (v) => fmtPct(v), higherIsBetter: true },
      { label: 'Net Margin',       getValue: f => f.ratios.net_margin,       format: (v) => fmtPct(v), higherIsBetter: true },
    ],
  },
  {
    title: 'Cash Flow',
    metrics: [
      { label: 'Free Cash Flow', getValue: f => f.cash_flow.free_cash_flow,       format: (v, s) => fmtDollar(v, s), higherIsBetter: true },
      { label: 'Operating CF',   getValue: f => f.cash_flow.operating_cash_flow,  format: (v, s) => fmtDollar(v, s), higherIsBetter: true },
      { label: 'CapEx',          getValue: f => f.cash_flow.capital_expenditures, format: (v, s) => fmtDollar(v, s) },
    ],
  },
  {
    title: 'Balance Sheet',
    metrics: [
      { label: 'Total Assets', getValue: f => f.balance_sheet.total_assets,  format: (v, s) => fmtDollar(v, s) },
      { label: 'Total Debt',   getValue: f => f.balance_sheet.total_debt,    format: (v, s) => fmtDollar(v, s) },
      { label: 'Total Equity', getValue: f => f.balance_sheet.total_equity,  format: (v, s) => fmtDollar(v, s), higherIsBetter: true },
    ],
  },
  {
    title: 'Returns & Leverage',
    metrics: [
      { label: 'ROE',          getValue: f => f.ratios.roe,            format: (v) => fmtPct(v),      higherIsBetter: true },
      { label: 'ROA',          getValue: f => f.ratios.roa,            format: (v) => fmtPct(v),      higherIsBetter: true },
      { label: 'P/E Ratio',    getValue: f => f.ratios.pe_ratio,       format: (v) => fmtMultiple(v) },
      { label: 'Debt / Equity', getValue: f => f.ratios.debt_to_equity, format: (v) => fmtMultiple(v) },
    ],
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function ComparePage() {
  return (
    <Suspense fallback={null}>
      <CompareContent />
    </Suspense>
  );
}

function CompareContent() {
  const searchParams = useSearchParams();
  const [tickers, setTickers]     = useState<string[]>([]);
  const [dataMap, setDataMap]     = useState<Record<string, NormalizedFundamentals[]>>({});
  const [loadingSet, setLoadingSet] = useState<Set<string>>(new Set());
  const [query, setQuery]         = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [note, setNote]           = useState<{ text: string; kind: 'error' | 'warn' } | null>(null);

  const containerRef  = useRef<HTMLDivElement>(null);
  const noteTimerRef  = useRef<ReturnType<typeof setTimeout>>(undefined);

  const { data: results = [] } = useSWR<SearchResult[]>(
    debouncedQuery ? searchKey(debouncedQuery) : null,
    () => fetchSearch(debouncedQuery),
    { keepPreviousData: true },
  );

  // Typeahead debounce
  useEffect(() => {
    if (!query.trim()) { setDebouncedQuery(''); setDropdownOpen(false); return; }
    const tid = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => clearTimeout(tid);
  }, [query]);

  // Only re-open on a new committed query, not on every background SWR
  // revalidation of the same key — otherwise a dismissed dropdown could
  // silently reopen with stale results (JSX below still gates on results.length).
  useEffect(() => {
    if (debouncedQuery) setDropdownOpen(true);
  }, [debouncedQuery]);

  // Close dropdown on outside click
  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, []);

  // Pre-populate from ?tickers= (e.g. deep-linked from the screener's Compare action)
  useEffect(() => {
    const param = searchParams.get('tickers');
    if (!param) return;
    for (const t of param.split(',').map(s => s.trim()).filter(Boolean)) {
      addTicker(t);
    }
    // Only run once on mount — addTicker manages its own state after that.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function showNote(text: string, kind: 'error' | 'warn') {
    setNote({ text, kind });
    clearTimeout(noteTimerRef.current);
    noteTimerRef.current = setTimeout(() => setNote(null), 4000);
  }

  async function addTicker(raw: string) {
    const ticker = raw.toUpperCase().trim();
    if (!ticker) return;
    if (tickers.length + loadingSet.size >= 5) { showNote('Maximum 5 tickers', 'error'); return; }
    if (tickers.includes(ticker) || loadingSet.has(ticker)) return;

    setQuery('');
    setDropdownOpen(false);
    setLoadingSet(prev => new Set([...prev, ticker]));

    try {
      const company = await fetchCompany(ticker);
      if (company.asset_type !== 'equity') {
        showNote(`${ticker} is not a stock — comparison supports equities only`, 'warn');
        return;
      }
      const data = await fetchFundamentals(ticker, 'annual', 3);
      setDataMap(prev => ({ ...prev, [ticker]: data }));
      setTickers(prev => [...prev, ticker]);
    } catch {
      showNote(`Could not load data for ${ticker}`, 'error');
    } finally {
      setLoadingSet(prev => { const s = new Set(prev); s.delete(ticker); return s; });
    }
  }

  function removeTicker(ticker: string) {
    setTickers(prev => prev.filter(t => t !== ticker));
    setDataMap(prev => { const next = { ...prev }; delete next[ticker]; return next; });
  }

  const atCap = tickers.length + loadingSet.size >= 5;

  // ── Radar data (only tickers that have loaded data) ──────────────────────

  const rawValues: Record<string, Record<string, number | null>> = {};
  for (const ticker of tickers) {
    const ratios = dataMap[ticker]?.[0]?.ratios as unknown as Record<string, number | null> | undefined;
    if (!ratios) continue;
    rawValues[ticker] = {};
    for (const m of RADAR_METRICS) {
      rawValues[ticker][m.key] = ratios[m.key] ?? null;
    }
  }

  const radarData = RADAR_METRICS.map(m => {
    const vals = tickers.map(t => rawValues[t]?.[m.key] ?? 0);
    const max = Math.max(...vals);
    return {
      metric: m.label,
      ...Object.fromEntries(
        tickers.map(t => [t, max > 0 ? ((rawValues[t]?.[m.key] ?? 0) / max) * 100 : 0])
      ),
    };
  });

  // ── Table currency ────────────────────────────────────────────────────────

  const currencies = tickers.map(t => dataMap[t]?.[0]?.currency ?? 'USD');
  const mixedCurrencies = new Set(currencies).size > 1;
  const symMap = Object.fromEntries(tickers.map((t, i) => [t, getCurrencySymbol(currencies[i])]));

  const canShowCharts = tickers.length >= 2;

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <Link href="/" className={styles.back}>← Back</Link>

        <div className={styles.header}>
          <h1 className={styles.title}>Compare</h1>
          <p className={styles.subtitle}>Add 2–5 stocks to compare side by side</p>
        </div>

        {/* ── Ticker input + chips ───────────────────────────────────────── */}
        <div className={styles.addRow}>
          <div className={styles.inputWrapper} ref={containerRef}>
            <input
              className={styles.tickerInput}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && query.trim()) addTicker(query);
                if (e.key === 'Escape') setDropdownOpen(false);
              }}
              onFocus={() => results.length > 0 && setDropdownOpen(true)}
              placeholder={atCap ? 'Maximum reached' : 'Add ticker…'}
              disabled={atCap}
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
                    onMouseDown={() => addTicker(r.ticker)}
                  >
                    <span className={styles.dropdownTicker}>{r.ticker}</span>
                    <span className={styles.dropdownName}>{r.name}</span>
                    {r.asset_type && (
                      <span className={styles.dropdownBadge}>{r.asset_type}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className={styles.chips}>
            {tickers.map((ticker, i) => (
              <div
                key={ticker}
                className={styles.chip}
                style={{ borderColor: `${SERIES_COLORS[i]}60` }}
              >
                <span className={styles.chipColor} style={{ background: SERIES_COLORS[i] }} />
                <span className={styles.chipLabel}>{ticker}</span>
                <button
                  className={styles.chipRemove}
                  onClick={() => removeTicker(ticker)}
                  aria-label={`Remove ${ticker}`}
                >
                  ×
                </button>
              </div>
            ))}
            {[...loadingSet].filter(t => !tickers.includes(t)).map(ticker => (
              <div key={ticker} className={`${styles.chip} ${styles.chipPending}`}>
                <span className={styles.chipLabel}>{ticker}</span>
                <span className={styles.chipLoading}>…</span>
              </div>
            ))}
          </div>
        </div>

        {note && (
          <p className={`${styles.note} ${note.kind === 'error' ? styles.noteError : styles.noteWarn}`}>
            {note.text}
          </p>
        )}

        {/* ── Main content ───────────────────────────────────────────────── */}
        {!canShowCharts ? (
          <div className={styles.emptyState}>
            <p className={styles.emptyText}>
              {tickers.length === 0 && loadingSet.size === 0
                ? 'Add at least 2 tickers to compare'
                : `Add ${Math.max(0, 2 - tickers.length)} more ticker${2 - tickers.length !== 1 ? 's' : ''} to compare`}
            </p>
          </div>
        ) : (
          <>
            {/* Radar chart */}
            <div className={styles.radarCard}>
              <p className={styles.sectionLabel}>Profitability &amp; Returns — normalized across set</p>
              <ResponsiveContainer width="100%" height={360}>
                <RadarChart data={radarData} margin={{ top: 16, right: 40, bottom: 16, left: 40 }}>
                  <PolarGrid stroke="rgba(255,255,255,0.07)" />
                  <PolarAngleAxis
                    dataKey="metric"
                    tick={{ fill: '#6b7280', fontSize: 11, fontFamily: 'var(--font-data)' }}
                  />
                  <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                  {tickers.map((ticker, i) => (
                    <Radar
                      key={ticker}
                      name={ticker}
                      dataKey={ticker}
                      stroke={SERIES_COLORS[i]}
                      fill={SERIES_COLORS[i]}
                      fillOpacity={0.15}
                    />
                  ))}
                  <Legend
                    wrapperStyle={{
                      fontFamily: 'var(--font-data)',
                      fontSize: 12,
                      paddingTop: 8,
                    }}
                  />
                  <Tooltip
                    content={((props: unknown) => {
                      const { active, payload, label } = props as {
                        active?: boolean;
                        payload?: ReadonlyArray<{ name?: string; color?: string }>;
                        label?: string;
                      };
                      if (!active || !payload?.length) return null;
                      const metricKey = RADAR_METRICS.find(m => m.label === label)?.key ?? '';
                      return (
                        <div className={styles.tooltip}>
                          <p className={styles.tooltipLabel}>{label}</p>
                          {payload.map(entry => {
                            const name = String(entry.name ?? '');
                            const raw = rawValues[name]?.[metricKey] ?? null;
                            const display = raw != null ? `${(raw * 100).toFixed(1)}%` : '—';
                            return (
                              <p key={name} className={styles.tooltipRow} style={{ color: entry.color }}>
                                {name}: {display}
                              </p>
                            );
                          })}
                        </div>
                      );
                    }) as never}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* Comparison table */}
            <div className={styles.tableCard}>
              {mixedCurrencies && (
                <p className={styles.caveatNote}>
                  Values shown in each company&apos;s reporting currency.
                </p>
              )}
              <div className={styles.tableWrapper}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th className={styles.metricHeader}>Metric</th>
                      {tickers.map((ticker, i) => (
                        <th key={ticker} className={styles.tickerHeader} style={{ color: SERIES_COLORS[i] }}>
                          {ticker}
                          <span className={styles.tickerCurrency}> {dataMap[ticker]?.[0]?.currency}</span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {TABLE_SECTIONS.flatMap(section => [
                      <tr key={`s-${section.title}`} className={styles.sectionRow}>
                        <td className={styles.sectionCell} colSpan={tickers.length + 1}>
                          {section.title}
                        </td>
                      </tr>,
                      ...section.metrics.map(metric => {
                        const rawVals = tickers.map(t => {
                          const d = dataMap[t]?.[0];
                          return d ? metric.getValue(d) : null;
                        });
                        const bestIdx = metric.higherIsBetter
                          ? rawVals.reduce<number>((best, v, i) => {
                              if (v == null) return best;
                              if (best === -1) return i;
                              const bv = rawVals[best];
                              return bv == null || v > bv ? i : best;
                            }, -1)
                          : -1;

                        return (
                          <tr key={`m-${metric.label}`} className={styles.dataRow}>
                            <td className={styles.metricCell}>{metric.label}</td>
                            {tickers.map((ticker, i) => {
                              const d = dataMap[ticker]?.[0];
                              const v = d ? metric.getValue(d) : null;
                              const text = d ? metric.format(v, symMap[ticker]) : '—';
                              const isBest = metric.higherIsBetter && i === bestIdx && v != null && tickers.length > 1;
                              return (
                                <td
                                  key={ticker}
                                  className={`${styles.valueCell} ${text === '—' ? styles.missingCell : ''}`}
                                  style={isBest ? { backgroundColor: 'rgba(43, 255, 136, 0.08)' } : undefined}
                                >
                                  {text}
                                </td>
                              );
                            })}
                          </tr>
                        );
                      }),
                    ])}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
