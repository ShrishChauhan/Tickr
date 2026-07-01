'use client';

import type { NormalizedFundamentals } from '@/lib/api';
import { getCurrencySymbol, fmtDollar, fmtEps, fmtPct, fmtMultiple } from '@/lib/format';
import styles from './FundamentalsTable.module.css';

// ─── Formatting ──────────────────────────────────────────────────────────────

type FormatType = 'dollar' | 'eps' | 'pct' | 'multiple';
type ColorMode  = 'sign' | 'positive-good' | 'none';

// fmt is defined inside the component so it closes over currSym — see below

function colorClass(v: number | null | undefined, mode: ColorMode): string {
  if (v == null)          return styles.missing;
  if (mode === 'none')    return '';
  if (mode === 'sign')    return v < 0 ? styles.negative : '';
  // positive-good
  if (v > 0)  return styles.positive;
  if (v < 0)  return styles.negative;
  return '';
}

// ─── Row definitions ──────────────────────────────────────────────────────────

interface SectionRow { kind: 'section'; label: string }
interface DataRow {
  kind:    'data';
  label:   string;
  get:     (f: NormalizedFundamentals) => number | null | undefined;
  format:  FormatType;
  color:   ColorMode;
}
type TableRow = SectionRow | DataRow;

const ROWS: TableRow[] = [
  { kind: 'section', label: 'Income Statement' },
  { kind: 'data', label: 'Revenue',          get: f => f.income_statement.revenue,          format: 'dollar',   color: 'none' },
  { kind: 'data', label: 'Gross Profit',     get: f => f.income_statement.gross_profit,     format: 'dollar',   color: 'sign' },
  { kind: 'data', label: 'Operating Income', get: f => f.income_statement.operating_income, format: 'dollar',   color: 'sign' },
  { kind: 'data', label: 'EBITDA',           get: f => f.income_statement.ebitda,           format: 'dollar',   color: 'sign' },
  { kind: 'data', label: 'Net Income',       get: f => f.income_statement.net_income,       format: 'dollar',   color: 'sign' },
  { kind: 'data', label: 'EPS (diluted)',    get: f => f.income_statement.eps_diluted,      format: 'eps',      color: 'sign' },

  { kind: 'section', label: 'Margins' },
  { kind: 'data', label: 'Gross Margin',     get: f => f.ratios.gross_margin,     format: 'pct', color: 'positive-good' },
  { kind: 'data', label: 'Operating Margin', get: f => f.ratios.operating_margin, format: 'pct', color: 'positive-good' },
  { kind: 'data', label: 'Net Margin',       get: f => f.ratios.net_margin,       format: 'pct', color: 'positive-good' },

  { kind: 'section', label: 'Cash Flow' },
  { kind: 'data', label: 'Operating CF',     get: f => f.cash_flow.operating_cash_flow,   format: 'dollar', color: 'sign' },
  { kind: 'data', label: 'CapEx',            get: f => f.cash_flow.capital_expenditures,  format: 'dollar', color: 'none' },
  { kind: 'data', label: 'Free Cash Flow',   get: f => f.cash_flow.free_cash_flow,        format: 'dollar', color: 'sign' },

  { kind: 'section', label: 'Balance Sheet' },
  { kind: 'data', label: 'Cash & Equiv',   get: f => f.balance_sheet.cash_and_equivalents, format: 'dollar',   color: 'none' },
  { kind: 'data', label: 'Total Debt',     get: f => f.balance_sheet.total_debt,           format: 'dollar',   color: 'none' },
  { kind: 'data', label: 'Total Equity',   get: f => f.balance_sheet.total_equity,         format: 'dollar',   color: 'sign' },

  { kind: 'section', label: 'Returns & Leverage' },
  { kind: 'data', label: 'ROE',          get: f => f.ratios.roe,            format: 'pct',      color: 'positive-good' },
  { kind: 'data', label: 'ROA',          get: f => f.ratios.roa,            format: 'pct',      color: 'positive-good' },
  { kind: 'data', label: 'Debt / Equity', get: f => f.ratios.debt_to_equity, format: 'multiple', color: 'none' },
];

// ─── Column header ────────────────────────────────────────────────────────────

function colLabel(f: NormalizedFundamentals): string {
  if (f.period === 'ttm') return 'TTM';
  const fy = f.fiscal_year ?? parseInt(f.period_end_date.slice(0, 4), 10);
  if (f.period === 'quarterly' && f.fiscal_quarter != null) {
    return `Q${f.fiscal_quarter} '${String(fy).slice(2)}`;
  }
  return `FY${fy}`;
}

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  periods: NormalizedFundamentals[];
}

export default function FundamentalsTable({ periods }: Props) {
  if (periods.length === 0) return null;

  const currSym = getCurrencySymbol(periods[0].currency ?? 'USD');

  function fmt(v: number | null | undefined, type: FormatType): string {
    switch (type) {
      case 'dollar':   return fmtDollar(v, currSym);
      case 'eps':      return fmtEps(v, currSym);
      case 'pct':      return fmtPct(v);
      case 'multiple': return fmtMultiple(v);
    }
  }

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={`${styles.headerCell} ${styles.labelHeader}`} scope="col" />
            {periods.map((f, i) => (
              <th key={i} className={styles.headerCell} scope="col">
                {colLabel(f)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row, ri) => {
            if (row.kind === 'section') {
              return (
                <tr key={`s-${ri}`} className={styles.sectionRow}>
                  <td className={styles.sectionCell} colSpan={periods.length + 1}>
                    {row.label}
                  </td>
                </tr>
              );
            }

            return (
              <tr key={`d-${ri}`} className={styles.dataRow}>
                <td className={styles.labelCell}>{row.label}</td>
                {periods.map((f, ci) => {
                  const v = row.get(f);
                  const text = fmt(v, row.format);
                  const cls  = colorClass(v, row.color);
                  const isMissing = text === '—';
                  return (
                    <td
                      key={ci}
                      className={`${styles.valueCell} ${isMissing ? styles.missing : cls}`}
                    >
                      {text}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
