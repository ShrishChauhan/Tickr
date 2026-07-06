export interface CompanyIdentity {
  ticker: string;
  name: string;
  market: string;
  exchange: string;
  currency: string;
  asset_type: string;
  cik?: string | null;
  isin?: string | null;
}

export interface IncomeStatement {
  revenue: number | null;
  cost_of_revenue: number | null;
  gross_profit: number | null;
  operating_income: number | null;
  ebitda: number | null;
  net_income: number | null;
  eps_basic: number | null;
  eps_diluted: number | null;
  shares_outstanding_basic: number | null;
  shares_outstanding_diluted: number | null;
}

export interface BalanceSheet {
  total_assets: number | null;
  total_liabilities: number | null;
  total_equity: number | null;
  cash_and_equivalents: number | null;
  total_debt: number | null;
  net_debt: number | null;
  goodwill: number | null;
  intangible_assets: number | null;
}

export interface CashFlowStatement {
  operating_cash_flow: number | null;
  capital_expenditures: number | null;
  free_cash_flow: number | null;
  investing_cash_flow: number | null;
  financing_cash_flow: number | null;
  dividends_paid: number | null;
}

export interface Ratios {
  pe_ratio: number | null;
  ps_ratio: number | null;
  pb_ratio: number | null;
  ev_ebitda: number | null;
  ev_revenue: number | null;
  market_cap: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  roe: number | null;
  roa: number | null;
  roic: number | null;
  debt_to_equity: number | null;
  debt_to_ebitda: number | null;
  interest_coverage: number | null;
  current_ratio: number | null;
  quick_ratio: number | null;
}

export interface NormalizedFundamentals {
  company: CompanyIdentity;
  period: 'annual' | 'quarterly' | 'ttm';
  fiscal_year: number | null;
  fiscal_quarter: number | null;
  period_end_date: string;
  currency: string;
  income_statement: IncomeStatement;
  balance_sheet: BalanceSheet;
  cash_flow: CashFlowStatement;
  ratios: Ratios;
  source: string;
  fetched_at: string;
}

export interface FilingReference {
  company: CompanyIdentity;
  filing_type: string;
  filed_date: string;
  period_of_report: string | null;
  accession_number: string | null;
  url: string;
  summary: string | null;
  source: string;
  fetched_at: string;
}

export interface SearchResult {
  ticker: string;
  name: string;
  exchange: string;
  asset_type: string;
  sector: string | null;
}

export interface ScreenerRow {
  ticker: string;
  name: string;
  currency: string | null;
  market_cap: number | null;
  pe_ratio: number | null;
  net_margin: number | null;
  roe: number | null;
  debt_to_equity: number | null;
  gross_margin: number | null;
  revenue: number | null;
  free_cash_flow: number | null;
}

export async function fetchSearch(query: string): Promise<SearchResult[]> {
  if (!query.trim()) return [];
  const res = await fetch(
    `${BASE_URL}/api/v1/search?q=${encodeURIComponent(query)}`,
  );
  if (!res.ok) return [];
  return res.json() as Promise<SearchResult[]>;
}

export interface AnalysisResult {
  ticker: string;
  analysis: string;
  disclaimer: string;
  generated_at: string;
  cached: boolean;
  source: string;
  period: string;
  periods_analyzed: number;
}

export interface OHLCBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface PriceOnlyData {
  ticker: string;
  name: string;
  asset_type: string;
  currency: string;
  current_price: number | null;
  change_24h: number | null;
  change_24h_pct: number | null;
  high_52w: number | null;
  low_52w: number | null;
  market_cap: number | null;
  volume_24h: number | null;
  circulating_supply: number | null;
  contract_month: string | null;
  ohlc: OHLCBar[];
  fetched_at: string;
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function fetchCompany(ticker: string): Promise<CompanyIdentity> {
  const res = await fetch(
    `${BASE_URL}/api/v1/companies/${encodeURIComponent(ticker)}?source=edgar`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<CompanyIdentity>;
}

export async function fetchFundamentals(
  ticker: string,
  period: 'annual' | 'quarterly' = 'annual',
  limit = 5,
): Promise<NormalizedFundamentals[]> {
  const res = await fetch(
    `${BASE_URL}/api/v1/companies/${encodeURIComponent(ticker)}/fundamentals?source=yfinance&period=${period}&limit=${limit}`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<NormalizedFundamentals[]>;
}

export async function fetchFilings(ticker: string, limit = 10): Promise<FilingReference[]> {
  const res = await fetch(
    `${BASE_URL}/api/v1/companies/${encodeURIComponent(ticker)}/filings?source=edgar&limit=${limit}`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<FilingReference[]>;
}

export async function fetchPriceOnly(ticker: string): Promise<PriceOnlyData> {
  const res = await fetch(
    `${BASE_URL}/api/v1/assets/${encodeURIComponent(ticker)}/price`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<PriceOnlyData>;
}

export async function fetchScreenerRows(universeKey: string): Promise<ScreenerRow[]> {
  const res = await fetch(
    `${BASE_URL}/api/v1/screener/${encodeURIComponent(universeKey)}/rows`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<ScreenerRow[]>;
}

export async function fetchAnalysis(ticker: string): Promise<AnalysisResult> {
  const res = await fetch(
    `${BASE_URL}/api/v1/companies/${encodeURIComponent(ticker)}/analyze?source=yfinance&period=annual&limit=5`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<AnalysisResult>;
}
