'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { fetchCompany, fetchFundamentals, fetchFilings, ApiError } from '@/lib/api';
import type { CompanyIdentity, NormalizedFundamentals, FilingReference } from '@/lib/api';
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

  const [state, setState] = useState<RouterState>({ kind: 'loading' });

  useEffect(() => {
    if (!normalizedTicker) return;

    let cancelled = false;
    setState({ kind: 'loading' });

    fetchCompany(normalizedTicker)
      .then(identity => {
        if (cancelled) return;

        if (identity.asset_type === 'equity') {
          Promise.allSettled([
            fetchFundamentals(normalizedTicker),
            fetchFilings(normalizedTicker),
          ]).then(([fundResult, filingsResult]) => {
            if (cancelled) return;
            setState({
              kind: 'equity',
              data: identity,
              fundamentals: fundResult.status === 'fulfilled' ? fundResult.value : [],
              filings: filingsResult.status === 'fulfilled' ? filingsResult.value : [],
            });
          });
        } else {
          setState({ kind: 'price_only', identity });
        }
      })
      .catch(err => {
        if (cancelled) return;
        setState({
          kind: 'error',
          message: err instanceof ApiError ? err.message : 'An unexpected error occurred',
          httpStatus: err instanceof ApiError ? err.status : undefined,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [normalizedTicker]);

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
