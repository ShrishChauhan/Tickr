'use client';

import Link from 'next/link';
import type { ScreenerRow } from '@/lib/api';
import { getCurrencySymbol, fmtDollar, fmtPct, fmtMultiple } from '@/lib/format';
import styles from './ScreenerTable.module.css';

export type SortKey = 'name' | 'market_cap' | 'pe_ratio' | 'net_margin' | 'roe' | 'revenue' | 'gross_margin';
export type SortDir = 'asc' | 'desc';

export type { ScreenerRow };

interface Props {
  rows: ScreenerRow[];
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'name', label: 'Company' },
  { key: 'market_cap', label: 'Market Cap' },
  { key: 'pe_ratio', label: 'P/E' },
  { key: 'net_margin', label: 'Net Margin' },
  { key: 'roe', label: 'ROE' },
  { key: 'revenue', label: 'Revenue' },
  { key: 'gross_margin', label: 'Gross Margin' },
];

export default function ScreenerTable({ rows, sortKey, sortDir, onSort }: Props) {
  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.tickerHeader}>Ticker</th>
            {COLUMNS.map(col => (
              <th
                key={col.key}
                className={`${styles.headerCell} ${col.key !== 'name' ? styles.right : ''}`}
                onClick={() => onSort(col.key)}
              >
                {col.label}
                {sortKey === col.key && (
                  <span className={styles.sortArrow}>{sortDir === 'desc' ? ' ↓' : ' ↑'}</span>
                )}
              </th>
            ))}
            <th className={styles.actionsHeader} />
          </tr>
        </thead>
        <tbody>
          {rows.map(row => {
            const currSym = row.currency ? getCurrencySymbol(row.currency) : '$';

            return (
              <tr key={row.ticker} className={styles.dataRow}>
                <td className={styles.tickerCell}>
                  <Link href={`/company/${row.ticker}`} className={styles.tickerLink}>
                    {row.ticker}
                  </Link>
                </td>
                <td className={styles.nameCell}>{row.name}</td>
                <td className={styles.valueCell}>{fmtDollar(row.market_cap, currSym)}</td>
                <td className={styles.valueCell}>{fmtMultiple(row.pe_ratio)}</td>
                <td className={styles.valueCell}>{fmtPct(row.net_margin)}</td>
                <td className={styles.valueCell}>{fmtPct(row.roe)}</td>
                <td className={styles.valueCell}>{fmtDollar(row.revenue, currSym)}</td>
                <td className={styles.valueCell}>{fmtPct(row.gross_margin)}</td>
                <td className={styles.actionsCell}>
                  <Link href={`/company/${row.ticker}`} className={styles.actionLink}>View</Link>
                  <Link href={`/compare?tickers=${row.ticker}`} className={styles.actionLink}>Compare</Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
