import type { FilingReference } from '@/lib/api';
import styles from './FilingsList.module.css';

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatPeriod(iso: string): string {
  const d = new Date(iso);
  const month = d.getMonth() + 1;
  const year = d.getFullYear();
  const quarter = Math.ceil(month / 3);
  return month === 12 ? `FY${year}` : `Q${quarter} ${year}`;
}

interface Props {
  filings: FilingReference[];
}

export default function FilingsList({ filings }: Props) {
  return (
    <div className={styles.card}>
      <p className={styles.sectionLabel}>Recent Filings</p>
      {filings.length === 0 ? (
        <p className={styles.empty}>No filings available.</p>
      ) : (
        <ul className={styles.list}>
          {filings.map((f, i) => (
            <li key={i} className={styles.row}>
              <span className={styles.typeBadge}>{f.filing_type}</span>
              <span className={styles.date}>{formatDate(f.filed_date)}</span>
              {f.period_of_report && (
                <span className={styles.period}>{formatPeriod(f.period_of_report)}</span>
              )}
              <a
                href={f.url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.link}
                aria-label={`Open ${f.filing_type} filed ${f.filed_date}`}
              >
                ↗
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
