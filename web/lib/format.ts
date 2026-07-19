const CURRENCY_SYMBOL: Record<string, string> = {
  USD: '$', GBP: '£', EUR: '€', JPY: '¥', INR: '₹', BRL: 'R$', MXN: 'MX$',
  CAD: 'CA$', AUD: 'A$', CHF: 'CHF', KRW: '₩', TWD: 'NT$', HKD: 'HK$', CNY: '¥', SAR: 'SAR', ZAR: 'R', NOK: 'kr',
};

export function getCurrencySymbol(currency: string): string {
  return CURRENCY_SYMBOL[currency] ?? currency;
}

export function relativeTime(iso: string): string {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return 'just now';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days > 1 ? 's' : ''} ago`;
}

export function fmtDollar(v: number | null | undefined, sym: string): string {
  if (v == null) return '—';
  const abs = Math.abs(v);
  const inner =
    abs >= 1e12 ? `${sym}${(abs / 1e12).toFixed(2)}T` :
    abs >= 1e9  ? `${sym}${(abs / 1e9).toFixed(1)}B`  :
    abs >= 1e6  ? `${sym}${(abs / 1e6).toFixed(1)}M`  :
                  `${sym}${abs.toFixed(0)}`;
  return v < 0 ? `(${inner})` : inner;
}

export function fmtEps(v: number | null | undefined, sym: string): string {
  if (v == null) return '—';
  const abs = Math.abs(v);
  const inner = `${sym}${abs.toFixed(2)}`;
  return v < 0 ? `(${inner})` : inner;
}

// Margin/return values from the API are decimals (0.44 = 44%). This multiplies by 100.
export function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

export function fmtMultiple(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${v.toFixed(2)}x`;
}

export function fmtPrice(value: number | null, currency: string): string {
  if (value === null) return '—';
  const prefix = currency === 'USD' ? '$' : currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : '';
  const suffix = prefix ? '' : ` ${currency}`;
  if (Math.abs(value) >= 1_000_000_000_000) return `${prefix}${(value / 1_000_000_000_000).toFixed(2)}T${suffix}`;
  if (Math.abs(value) >= 1_000_000_000) return `${prefix}${(value / 1_000_000_000).toFixed(2)}B${suffix}`;
  if (Math.abs(value) >= 1_000_000) return `${prefix}${(value / 1_000_000).toFixed(2)}M${suffix}`;
  return `${prefix}${value.toLocaleString(undefined, { maximumFractionDigits: 4 })}${suffix}`;
}

// NOTE: unlike fmtPct() above (which multiplies decimal fractions by 100 for margins/ratios),
// this assumes the input is already a percentage value (e.g. 2.35 -> "+2.35%"), matching the
// engine's change_24h_pct field. Do not use fmtPct() for that field.
export function fmtChangePct(value: number | null): string {
  if (value === null) return '—';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}
