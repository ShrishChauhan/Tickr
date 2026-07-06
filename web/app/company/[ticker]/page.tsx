'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import { fetchCompany, fetchFundamentals, fetchFilings, ApiError } from '@/lib/api';
import type { CompanyIdentity, NormalizedFundamentals, FilingReference } from '@/lib/api';
import { companyKey, fundamentalsKey, filingsKey } from '@/lib/swrKeys';
import { dailyDataConfig } from '@/lib/swrConfig';
import EquityPage from './EquityPage';
import PriceOnlyPage from './PriceOnlyPage';
import styles from './page.module.css';

type RouterState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; httpStatus?: number }
  | { kind: 'equity'; data: CompanyIdentity; fundamentals: NormalizedFundamentals[]; filings: FilingReference[] }
  | { kind: 'price_only'; identity: CompanyIdentity };

export default function CompanyPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const normalizedTicker = decodeURIComponent(ticker ?? '').toUpperCase();

  const {
    data: identity,
    error: identityError,
    isLoading: identityLoading,
  } = useSWR<CompanyIdentity, ApiError>(
    normalizedTicker ? companyKey(normalizedTicker) : null,
    () => fetchCompany(normalizedTicker),
    dailyDataConfig,
  );

  const isEquity = identity?.asset_type === 'equity';

  const { data: fundamentals, isLoading: fundLoading } = useSWR<NormalizedFundamentals[]>(
    isEquity ? fundamentalsKey(normalizedTicker) : null,
    () => fetchFundamentals(normalizedTicker),
    dailyDataConfig,
  );

  const { data: filings, isLoading: filingsLoading } = useSWR<FilingReference[]>(
    isEquity ? filingsKey(normalizedTicker) : null,
    () => fetchFilings(normalizedTicker),
    dailyDataConfig,
  );

  let state: RouterState;
  if (identityLoading || (!identity && !identityError)) {
    state = { kind: 'loading' };
  } else if (identityError) {
    state = {
      kind: 'error',
      message: identityError instanceof ApiError ? identityError.message : 'An unexpected error occurred',
      httpStatus: identityError instanceof ApiError ? identityError.status : undefined,
    };
  } else if (isEquity) {
    // Mirrors the old Promise.allSettled behavior: gate on loading only, not on
    // fundamentals/filings errors, so a single failed fetch degrades to [] instead
    // of surfacing a page-level error.
    state = (fundLoading || filingsLoading)
      ? { kind: 'loading' }
      : { kind: 'equity', data: identity!, fundamentals: fundamentals ?? [], filings: filings ?? [] };
  } else {
    state = { kind: 'price_only', identity: identity! };
  }

  if (state.kind === 'loading') {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <div className={styles.skeleton} aria-label="Loading…" aria-busy="true" />
        </div>
      </main>
    );
  }

  if (state.kind === 'error') {
    return (
      <main className={styles.page}>
        <div className={styles.container}>
          <Link href="/" className={styles.back}>
            ← Back to search
          </Link>
          <div className={styles.errorCard}>
            <p className={styles.errorTicker}>{normalizedTicker}</p>
            <p className={styles.errorMessage}>
              {state.httpStatus === 404
                ? `"${normalizedTicker}" not found. Check the ticker and try again.`
                : state.message}
            </p>
          </div>
        </div>
      </main>
    );
  }

  if (state.kind === 'equity') {
    return <EquityPage data={state.data} fundamentals={state.fundamentals} filings={state.filings} />;
  }

  return <PriceOnlyPage identity={state.identity} />;
}
