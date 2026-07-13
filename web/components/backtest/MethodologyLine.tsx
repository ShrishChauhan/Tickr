'use client';

import type { BacktestResponse } from '@/lib/api';
import styles from './results.module.css';

export default function MethodologyLine({
  result,
  costPct,
  startingCapital,
}: {
  result: BacktestResponse;
  costPct: number;
  startingCapital: number;
}) {
  const effectiveStart = result.dates[0];
  const effectiveEnd = result.dates[result.dates.length - 1];

  return (
    <div className={styles.methodologyLine}>
      <p>
        {effectiveStart} to {effectiveEnd} · ${startingCapital.toLocaleString()} starting capital ·
        {' '}{(costPct * 100).toFixed(2)}% transaction cost per side
      </p>
      <p>
        Signals are evaluated on a bar&apos;s close; trades fill at the next bar&apos;s close (no
        same-bar execution).
      </p>
    </div>
  );
}
