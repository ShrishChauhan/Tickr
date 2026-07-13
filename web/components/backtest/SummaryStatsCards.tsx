'use client';

import type { BacktestResponse } from '@/lib/api';
import styles from './results.module.css';

const STAT_DEFINITIONS = {
  totalReturn: 'Total percentage gain or loss on starting capital over the full backtest period.',
  maxDrawdown: 'The largest peak-to-trough decline in portfolio value at any point during the backtest.',
  numTrades: 'The number of completed round-trip trades (entries with a matching exit).',
  winRate: 'The share of closed trades that ended with a positive profit and loss.',
  finalStatus: 'Whether the strategy held an open position (marked-to-market, not force-closed) at the end of the period, or was flat in cash.',
};

function fmtSignedPct(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export default function SummaryStatsCards({ result }: { result: BacktestResponse }) {
  return (
    <div className={styles.statsGrid}>
      <div className={styles.statCard}>
        <div className={styles.statHeader}>
          <span className={styles.statLabel}>Total Return</span>
          <span className={`${styles.statValue} ${result.total_return_pct >= 0 ? styles.positive : styles.negative}`}>
            {fmtSignedPct(result.total_return_pct)}
          </span>
        </div>
        <p className={styles.statDefinition}>{STAT_DEFINITIONS.totalReturn}</p>
      </div>

      <div className={styles.statCard}>
        <div className={styles.statHeader}>
          <span className={styles.statLabel}>Max Drawdown</span>
          <span className={`${styles.statValue} ${styles.negative}`}>
            -{result.max_drawdown_pct.toFixed(2)}%
          </span>
        </div>
        <p className={styles.statDefinition}>{STAT_DEFINITIONS.maxDrawdown}</p>
      </div>

      <div className={styles.statCard}>
        <div className={styles.statHeader}>
          <span className={styles.statLabel}>Trades</span>
          <span className={styles.statValue}>{result.num_trades}</span>
        </div>
        <p className={styles.statDefinition}>{STAT_DEFINITIONS.numTrades}</p>
      </div>

      <div className={styles.statCard}>
        <div className={styles.statHeader}>
          <span className={styles.statLabel}>Win Rate</span>
          <span className={styles.statValue}>
            {result.win_rate_pct == null ? 'N/A — no closed trades' : `${result.win_rate_pct.toFixed(2)}%`}
          </span>
        </div>
        <p className={styles.statDefinition}>{STAT_DEFINITIONS.winRate}</p>
      </div>

      <div className={styles.statCard}>
        <div className={styles.statHeader}>
          <span className={styles.statLabel}>Final Status</span>
          <span className={styles.statValue}>{result.final_status === 'open' ? 'Open position' : 'Flat'}</span>
        </div>
        <p className={styles.statDefinition}>{STAT_DEFINITIONS.finalStatus}</p>
      </div>
    </div>
  );
}
