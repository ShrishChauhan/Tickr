'use client';

import type { IndicatorSchema, IndicatorType } from '@/lib/api';
import styles from './backtest.module.css';

interface Props {
  value: IndicatorSchema;
  onChange: (next: IndicatorSchema) => void;
  label: string;
}

const INDICATOR_OPTIONS: { value: IndicatorType; label: string }[] = [
  { value: 'PRICE', label: 'Price' },
  { value: 'SMA', label: 'SMA' },
  { value: 'RSI', label: 'RSI' },
];

export default function IndicatorPicker({ value, onChange, label }: Props) {
  function selectType(type: IndicatorType) {
    onChange({ type, window: type === 'PRICE' ? null : value.window });
  }

  return (
    <div className={styles.selectGroup}>
      <label className={styles.selectLabel}>{label}</label>
      <select
        className={styles.select}
        value={value.type}
        onChange={e => selectType(e.target.value as IndicatorType)}
      >
        {INDICATOR_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      {value.type !== 'PRICE' && (
        <input
          className={styles.select}
          type="number"
          min={1}
          step={1}
          value={value.window ?? ''}
          onChange={e =>
            onChange({ ...value, window: e.target.value.trim() === '' ? null : Number(e.target.value) })
          }
          placeholder="Window (e.g. 14)"
        />
      )}
    </div>
  );
}
