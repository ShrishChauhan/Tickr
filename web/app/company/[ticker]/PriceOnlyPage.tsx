'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { fetchPriceOnly, ApiError } from '@/lib/api';
import type { CompanyIdentity, PriceOnlyData, OHLCBar } from '@/lib/api';
import { relativeTime } from '@/lib/format';
import pageStyles from './page.module.css';
import styles from './PriceOnlyPage.module.css';

type Timeframe = '1W' | '1M' | '3M' | '1Y';

const TIMEFRAME_DAYS: Record<Timeframe, number> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
};

interface Props {
  identity: CompanyIdentity;
}

type InternalState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; data: PriceOnlyData };

function formatPrice(value: number | null, currency: string): string {
  if (value === null) return '—';
  const prefix = currency === 'USD' ? '$' : currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : '';
  const suffix = prefix ? '' : ` ${currency}`;
  if (Math.abs(value) >= 1_000_000_000_000) return `${prefix}${(value / 1_000_000_000_000).toFixed(2)}T${suffix}`;
  if (Math.abs(value) >= 1_000_000_000) return `${prefix}${(value / 1_000_000_000).toFixed(2)}B${suffix}`;
  if (Math.abs(value) >= 1_000_000) return `${prefix}${(value / 1_000_000).toFixed(2)}M${suffix}`;
  return `${prefix}${value.toLocaleString(undefined, { maximumFractionDigits: 4 })}${suffix}`;
}

function formatPct(value: number | null): string {
  if (value === null) return '—';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function filterBars(ohlc: OHLCBar[], tf: Timeframe): OHLCBar[] {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - TIMEFRAME_DAYS[tf]);
  return ohlc.filter(b => new Date(b.date) >= cutoff);
}

function assetTypeLabel(asset_type: string): string {
  const labels: Record<string, string> = {
    crypto: 'Crypto',
    forex: 'Forex',
    commodity: 'Commodity',
    index: 'Index',
  };
  return labels[asset_type] ?? asset_type;
}

// Candlestick rendered as a custom SVG bar with wick
function CandlestickBar(props: {
  x?: number; y?: number; width?: number; height?: number;
  open?: number; close?: number; high?: number; low?: number;
  yScale?: (v: number) => number;
}) {
  const { x = 0, width = 0, open = 0, close = 0, high = 0, low = 0, yScale } = props;
  if (!yScale || !width) return null;

  const isUp = close >= open;
  const color = isUp ? '#2BFF88' : '#FF4060';
  const bodyTop = yScale(Math.max(open, close));
  const bodyBottom = yScale(Math.min(open, close));
  const bodyHeight = Math.max(1, bodyBottom - bodyTop);
  const wickTop = yScale(high);
  const wickBottom = yScale(low);
  const cx = x + width / 2;

  return (
    <g>
      <line x1={cx} y1={wickTop} x2={cx} y2={wickBottom} stroke={color} strokeWidth={1} />
      <rect
        x={x + 1}
        y={bodyTop}
        width={Math.max(1, width - 2)}
        height={bodyHeight}
        fill={color}
        fillOpacity={0.85}
      />
    </g>
  );
}

function CandlestickChart({ bars, currency }: { bars: OHLCBar[]; currency: string }) {
  const data = bars.map(b => ({
    date: b.date,
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }));

  const allPrices = data.flatMap(d => [d.high, d.low]);
  const minPrice = Math.min(...allPrices);
  const maxPrice = Math.max(...allPrices);
  const padding = (maxPrice - minPrice) * 0.05 || 1;
  const yMin = minPrice - padding;
  const yMax = maxPrice + padding;

  const chartHeight = 220;
  const chartWidth = 800;
  const leftPad = 64;
  const rightPad = 12;
  const topPad = 8;
  const bottomPad = 32;
  const plotW = chartWidth - leftPad - rightPad;
  const plotH = chartHeight - topPad - bottomPad;

  const yScale = (v: number) => topPad + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

  const barW = Math.max(2, plotW / data.length - 2);

  const yTicks = 5;
  const yTickVals = Array.from({ length: yTicks }, (_, i) =>
    yMin + (i / (yTicks - 1)) * (yMax - yMin),
  );

  const xTickStep = Math.max(1, Math.floor(data.length / 6));

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%' }}
    >
      {/* Grid lines */}
      {yTickVals.map((v, i) => (
        <line
          key={i}
          x1={leftPad}
          y1={yScale(v)}
          x2={chartWidth - rightPad}
          y2={yScale(v)}
          stroke="rgba(255,255,255,0.04)"
          strokeWidth={1}
        />
      ))}
      {/* Y axis labels */}
      {yTickVals.map((v, i) => (
        <text
          key={i}
          x={leftPad - 6}
          y={yScale(v) + 4}
          textAnchor="end"
          fontSize={10}
          fill="#6b7280"
          fontFamily="var(--font-data)"
        >
          {v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(2)}
        </text>
      ))}
      {/* X axis labels */}
      {data.map((d, i) => {
        if (i % xTickStep !== 0) return null;
        const x = leftPad + (i / data.length) * plotW + barW / 2;
        const label = new Date(d.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        return (
          <text key={i} x={x} y={chartHeight - 4} textAnchor="middle" fontSize={10} fill="#6b7280" fontFamily="var(--font-data)">
            {label}
          </text>
        );
      })}
      {/* Candles */}
      {data.map((d, i) => {
        const x = leftPad + (i / data.length) * plotW;
        return (
          <CandlestickBar
            key={i}
            x={x}
            width={barW}
            open={d.open}
            close={d.close}
            high={d.high}
            low={d.low}
            yScale={yScale}
          />
        );
      })}
    </svg>
  );
}

function PriceLineChart({ bars, currency }: { bars: OHLCBar[]; currency: string }) {
  const data = bars.map(b => ({
    date: b.date,
    price: b.close,
    label: new Date(b.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'var(--font-data)' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'var(--font-data)' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(Number(v.toFixed(2)))}
          width={56}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--color-surface)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 6,
            fontFamily: 'var(--font-data)',
            fontSize: 12,
            color: 'var(--color-text-primary)',
          }}
          labelStyle={{ color: '#6b7280', fontSize: 11 }}
          formatter={(v: unknown) => [formatPrice(typeof v === 'number' ? v : null, currency), 'Price']}
        />
        <Line
          type="monotone"
          dataKey="price"
          stroke="#2BFF88"
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 3, fill: '#2BFF88' }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function MetadataGrid({ data }: { data: PriceOnlyData }) {
  const { asset_type, currency, market_cap, volume_24h, circulating_supply, high_52w, low_52w, contract_month } = data;

  const items: { label: string; value: string }[] = [];

  if (asset_type === 'crypto') {
    if (market_cap !== null) items.push({ label: 'Market Cap', value: formatPrice(market_cap, currency) });
    if (volume_24h !== null) items.push({ label: '24h Volume', value: formatPrice(volume_24h, currency) });
    if (circulating_supply !== null) items.push({ label: 'Circ. Supply', value: circulating_supply.toLocaleString(undefined, { maximumFractionDigits: 0 }) });
    items.push({ label: '52W High', value: formatPrice(high_52w, currency) });
    items.push({ label: '52W Low', value: formatPrice(low_52w, currency) });
  } else if (asset_type === 'forex') {
    items.push({ label: '52W High', value: formatPrice(high_52w, currency) });
    items.push({ label: '52W Low', value: formatPrice(low_52w, currency) });
  } else if (asset_type === 'commodity') {
    if (contract_month) items.push({ label: 'Contract', value: contract_month });
    items.push({ label: '52W High', value: formatPrice(high_52w, currency) });
    items.push({ label: '52W Low', value: formatPrice(low_52w, currency) });
    if (volume_24h !== null) items.push({ label: '24h Volume', value: formatPrice(volume_24h, currency) });
  } else {
    items.push({ label: '52W High', value: formatPrice(high_52w, currency) });
    items.push({ label: '52W Low', value: formatPrice(low_52w, currency) });
    if (volume_24h !== null) items.push({ label: 'Volume', value: formatPrice(volume_24h, currency) });
  }

  if (items.length === 0) return null;

  return (
    <div className={styles.metaGrid}>
      {items.map(({ label, value }) => (
        <div key={label} className={styles.statItem}>
          <span className={styles.statLabel}>{label}</span>
          <span className={styles.statValue}>{value}</span>
        </div>
      ))}
    </div>
  );
}

export default function PriceOnlyPage({ identity }: Props) {
  const [state, setState] = useState<InternalState>({ kind: 'loading' });
  const [timeframe, setTimeframe] = useState<Timeframe>('3M');

  useEffect(() => {
    let cancelled = false;
    setState({ kind: 'loading' });
    fetchPriceOnly(identity.ticker).then(data => {
      if (!cancelled) setState({ kind: 'success', data });
    }).catch(err => {
      if (!cancelled) setState({
        kind: 'error',
        message: err instanceof ApiError ? err.message : 'Failed to load price data',
      });
    });
    return () => { cancelled = true; };
  }, [identity.ticker]);

  const filteredBars = useMemo(() => {
    if (state.kind !== 'success') return [];
    return filterBars(state.data.ohlc, timeframe);
  }, [state, timeframe]);

  const useCandlestick = state.kind === 'success'
    && state.data.ohlc.length > 0
    && !['forex', 'index'].includes(identity.asset_type);

  return (
    <main className={pageStyles.page}>
      <div className={pageStyles.container}>
        <Link href="/" className={pageStyles.back}>
          ← Back
        </Link>

        {/* Header card */}
        <div className={pageStyles.card}>
          <div className={pageStyles.cardHeader}>
            <span className={pageStyles.ticker}>{identity.ticker}</span>
            <span className={pageStyles.exchangeBadge}>
              {assetTypeLabel(identity.asset_type)}
            </span>
          </div>
          <h1 className={pageStyles.name}>{identity.name}</h1>

          {state.kind === 'success' && (
            <>
              <div className={styles.priceDisplay}>
                <span className={styles.currentPrice}>
                  {formatPrice(state.data.current_price, state.data.currency)}
                </span>
                {state.data.change_24h_pct !== null && (
                  <span className={`${styles.change} ${state.data.change_24h_pct >= 0 ? styles.changePositive : styles.changeNegative}`}>
                    {formatPct(state.data.change_24h_pct)}
                    {state.data.change_24h !== null && (
                      <> ({state.data.change_24h >= 0 ? '+' : ''}{state.data.change_24h.toFixed(2)})</>
                    )}
                  </span>
                )}
              </div>
              <p className={pageStyles.freshness}>Updated {relativeTime(state.data.fetched_at)}</p>
            </>
          )}
        </div>

        {/* Chart */}
        {state.kind === 'loading' && <div className={styles.skeletonChart} aria-busy="true" />}

        {state.kind === 'error' && (
          <div className={pageStyles.card} style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
            {state.message}
          </div>
        )}

        {state.kind === 'success' && (
          <>
            <div className={styles.chartCard}>
              <div className={styles.chartHeader}>
                <span className={styles.chartTitle}>
                  {useCandlestick ? 'Price — Candlestick' : 'Price — Line'}
                </span>
                <div className={styles.timeframeBar}>
                  {(['1W', '1M', '3M', '1Y'] as Timeframe[]).map(tf => (
                    <button
                      key={tf}
                      className={`${styles.tfBtn} ${tf === timeframe ? styles.tfBtnActive : ''}`}
                      onClick={() => setTimeframe(tf)}
                    >
                      {tf}
                    </button>
                  ))}
                </div>
              </div>
              <div className={styles.chartWrap}>
                {filteredBars.length > 0 ? (
                  useCandlestick
                    ? <CandlestickChart bars={filteredBars} currency={state.data.currency} />
                    : <PriceLineChart bars={filteredBars} currency={state.data.currency} />
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', height: '100%', color: 'var(--color-text-muted)', fontSize: '0.875rem', fontFamily: 'var(--font-ui)' }}>
                    No chart data available for this timeframe.
                  </div>
                )}
              </div>
            </div>

            <MetadataGrid data={state.data} />
          </>
        )}

        {/* No-fundamentals notice */}
        <div className={styles.noFundamentals}>
          <p className={styles.noFundamentalsText}>
            {(() => {
              const ASSET_TYPE_LABEL_PLURAL: Record<string, string> = {
                commodity: 'commodities',
                forex: 'forex pairs',
                index: 'indices',
                crypto: 'cryptocurrencies',
                etf: 'ETFs',
                fund: 'funds',
              };
              const assetLabel = ASSET_TYPE_LABEL_PLURAL[identity.asset_type] ?? `${identity.asset_type}s`;
              return `Fundamental analysis is not available for ${assetLabel}.`;
            })()}
            {' '}Tickr&apos;s research engine covers global equities.
          </p>
        </div>
      </div>
    </main>
  );
}
