'use client';

import { useState, useEffect } from 'react';
import { fetchAnalysis } from '@/lib/api';
import type { AnalysisResult } from '@/lib/api';
import styles from './AnalysisPanel.module.css';

type State =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'success'; result: AnalysisResult };

interface Props {
  ticker: string;
}

export default function AnalysisPanel({ ticker }: Props) {
  const [state, setState] = useState<State>({ kind: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: 'loading' });

    fetchAnalysis(ticker).then(
      (result) => { if (!cancelled) setState({ kind: 'success', result }); },
      () => { if (!cancelled) setState({ kind: 'error' }); },
    );

    return () => { cancelled = true; };
  }, [ticker]);

  if (state.kind === 'loading') {
    return (
      <div className={styles.card}>
        <p className={styles.sectionLabel}>AI Analysis</p>
        <p className={styles.loadingLabel}>Generating analysis…</p>
        <div className={styles.skeletonWrap}>
          <div className={`${styles.skeletonLine} ${styles.w90}`} />
          <div className={`${styles.skeletonLine} ${styles.w75}`} />
          <div className={`${styles.skeletonLine} ${styles.w85}`} />
          <div className={`${styles.skeletonLine} ${styles.w60}`} />
          <div className={`${styles.skeletonLine} ${styles.w80}`} />
        </div>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className={styles.card}>
        <p className={styles.sectionLabel}>AI Analysis</p>
        <p className={styles.errorMsg}>
          Analysis unavailable. The AI service may be temporarily down.
        </p>
      </div>
    );
  }

  const { result } = state;
  const paragraphs = result.analysis.split(/\n\n+/).filter(Boolean);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <p className={styles.sectionLabel}>AI Analysis</p>
        <div className={styles.chips}>
          {result.cached && <span className={styles.badge}>CACHED</span>}
          <span className={styles.meta}>
            Based on {result.periods_analyzed} annual period{result.periods_analyzed !== 1 ? 's' : ''}
          </span>
        </div>
      </div>
      <div className={styles.body}>
        {paragraphs.map((para, i) => (
          <p key={i} className={styles.para}>{para}</p>
        ))}
      </div>
      <p className={styles.disclaimer}>{result.disclaimer}</p>
    </div>
  );
}
