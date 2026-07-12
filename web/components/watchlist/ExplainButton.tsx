'use client';

import { useState } from 'react';
import { fetchExplain } from '@/lib/api';
import type { ExplainResult } from '@/lib/api';
import styles from './ExplainButton.module.css';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'success'; result: ExplainResult };

interface Props {
  ticker: string;
  assetType: string;
  currentPrice: number;
  changePct: number | null;
}

export default function ExplainButton({ ticker, assetType, currentPrice, changePct }: Props) {
  const [state, setState] = useState<State>({ kind: 'idle' });
  const [open, setOpen] = useState(false);

  function handleClick() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (state.kind === 'success') return;
    setState({ kind: 'loading' });
    fetchExplain({
      ticker,
      asset_type: assetType,
      current_price: currentPrice,
      change_pct: changePct,
    }).then(
      (result) => setState({ kind: 'success', result }),
      () => setState({ kind: 'error' }),
    );
  }

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={styles.trigger}
        onClick={handleClick}
        aria-expanded={open}
        aria-label={`Explain ${ticker} price move`}
      >
        ?
      </button>
      {open && (
        <div className={styles.popover} role="tooltip">
          {state.kind === 'loading' && <p className={styles.loading}>Thinking…</p>}
          {state.kind === 'error' && (
            <p className={styles.error}>Explanation unavailable right now.</p>
          )}
          {state.kind === 'success' && <p className={styles.text}>{state.result.explanation}</p>}
        </div>
      )}
    </div>
  );
}
