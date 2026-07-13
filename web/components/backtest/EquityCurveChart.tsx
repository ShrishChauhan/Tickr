'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import type { BacktestResponse } from '@/lib/api';
import styles from './results.module.css';

function formatEquity(value: number | null): string {
  return value === null ? '—' : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export default function EquityCurveChart({ result }: { result: BacktestResponse }) {
  const data = result.dates.map((date, i) => ({
    date,
    equity: result.equity_curve[i],
    label: new Date(date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' }),
  }));

  return (
    <div className={styles.chartWrap}>
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
            formatter={(v: unknown) => [formatEquity(typeof v === 'number' ? v : null), 'Equity']}
          />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="#2BFF88"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3, fill: '#2BFF88' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
