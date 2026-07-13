'use client';

import type { ComparatorType, IndicatorSchema, RuleSchema } from '@/lib/api';
import IndicatorPicker from './IndicatorPicker';
import styles from './backtest.module.css';

interface Props {
  value: RuleSchema;
  onChange: (next: RuleSchema) => void;
  title: string;
}

const COMPARATORS: { value: ComparatorType; label: string }[] = [
  { value: 'CROSSES_ABOVE', label: 'Crosses Above' },
  { value: 'CROSSES_BELOW', label: 'Crosses Below' },
];

export default function RuleBuilder({ value, onChange, title }: Props) {
  const rightIsValue = typeof value.right === 'number';

  function setRightMode(mode: 'value' | 'indicator') {
    if (mode === 'value') {
      onChange({ ...value, right: NaN });
    } else {
      onChange({ ...value, right: { type: 'SMA', window: null } });
    }
  }

  return (
    <div className={styles.ruleCard}>
      <h2 className={styles.ruleTitle}>{title}</h2>

      <div className={styles.ruleRow}>
        <IndicatorPicker label="Left" value={value.left} onChange={left => onChange({ ...value, left })} />

        <div className={styles.selectGroup}>
          <label className={styles.selectLabel}>Comparator</label>
          <div className={styles.toggle}>
            {COMPARATORS.map(c => (
              <button
                key={c.value}
                type="button"
                className={`${styles.toggleButton} ${value.comparator === c.value ? styles.toggleButtonActive : ''}`}
                onClick={() => onChange({ ...value, comparator: c.value })}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.selectGroup}>
          <label className={styles.selectLabel}>Right side</label>
          <div className={styles.toggle}>
            <button
              type="button"
              className={`${styles.toggleButton} ${rightIsValue ? styles.toggleButtonActive : ''}`}
              onClick={() => setRightMode('value')}
            >
              Value
            </button>
            <button
              type="button"
              className={`${styles.toggleButton} ${!rightIsValue ? styles.toggleButtonActive : ''}`}
              onClick={() => setRightMode('indicator')}
            >
              Indicator
            </button>
          </div>
        </div>

        {rightIsValue ? (
          <div className={styles.selectGroup}>
            <label className={styles.selectLabel}>Right value</label>
            <input
              className={styles.select}
              type="number"
              value={Number.isNaN(value.right as number) ? '' : (value.right as number)}
              onChange={e =>
                onChange({ ...value, right: e.target.value.trim() === '' ? NaN : Number(e.target.value) })
              }
              placeholder="e.g. 30"
            />
          </div>
        ) : (
          <IndicatorPicker
            label="Right indicator"
            value={value.right as IndicatorSchema}
            onChange={right => onChange({ ...value, right })}
          />
        )}
      </div>
    </div>
  );
}
