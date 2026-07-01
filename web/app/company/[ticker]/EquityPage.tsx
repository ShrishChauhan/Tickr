'use client';

import Link from 'next/link';
import type { CompanyIdentity, NormalizedFundamentals, FilingReference } from '@/lib/api';
import { relativeTime } from '@/lib/format';
import FundamentalsTable from '@/components/company/FundamentalsTable';
import FilingsList from '@/components/company/FilingsList';
import AnalysisPanel from '@/components/company/AnalysisPanel';
import styles from './page.module.css';

interface Props {
  data: CompanyIdentity;
  fundamentals: NormalizedFundamentals[];
  filings: FilingReference[];
}

export default function EquityPage({ data, fundamentals, filings }: Props) {
  const latest = fundamentals[0];
  const periodLabel = latest
    ? (latest.fiscal_year ? `FY${latest.fiscal_year}` : latest.period_end_date.slice(0, 4))
    : null;

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <Link href="/" className={styles.back}>
          ← Back
        </Link>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <span className={styles.ticker}>{data.ticker}</span>
            <span className={styles.exchangeBadge}>{data.exchange}</span>
          </div>
          <h1 className={styles.name}>{data.name}</h1>
          <dl className={styles.meta}>
            <div className={styles.metaItem}>
              <dt className={styles.metaLabel}>Market</dt>
              <dd className={styles.metaValue}>{data.market}</dd>
            </div>
            <div className={styles.metaItem}>
              <dt className={styles.metaLabel}>Currency</dt>
              <dd className={styles.metaValue}>{data.currency}</dd>
            </div>
            {data.cik && (
              <div className={styles.metaItem}>
                <dt className={styles.metaLabel}>CIK</dt>
                <dd className={styles.metaValue}>{data.cik}</dd>
              </div>
            )}
          </dl>
          {periodLabel && latest && (
            <p className={styles.freshness}>
              Fundamentals as of {periodLabel} · Updated {relativeTime(latest.fetched_at)}
            </p>
          )}
        </div>
        {fundamentals.length > 0 && (
          <FundamentalsTable periods={fundamentals} />
        )}
        {filings.length > 0 && (
          <FilingsList filings={filings} />
        )}
        <AnalysisPanel ticker={data.ticker} />
      </div>
    </main>
  );
}
