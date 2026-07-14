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
  is_delayed: boolean;
  freshness_label: string;
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
  source: string;
  is_delayed: boolean;
  freshness_label: string;
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

export interface ExplainResult {
  ticker: string;
  explanation: string;
  generated_at: string;
  cached: boolean;
}

export interface ExplainRequest {
  ticker: string;
  asset_type: string;
  current_price: number;
  change_pct: number | null;
  gross_margin?: number | null;
  pe_ratio?: number | null;
}

export async function fetchExplain(payload: ExplainRequest): Promise<ExplainResult> {
  const res = await fetch(`${BASE_URL}/api/v1/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<ExplainResult>;
}

export interface OptionExpirations {
  ticker: string;
  available: boolean;
  expirations: string[];
}

export interface OptionContract {
  strike: number;
  bid: number | null;
  ask: number | null;
  last_price: number | null;
  volume: number | null;
  open_interest: number | null;
  implied_volatility: number | null;
  last_trade_date: string | null;
}

export interface OptionChain {
  ticker: string;
  expiration: string;
  calls: OptionContract[];
  puts: OptionContract[];
  fetched_at: string;
}

export interface GreeksInputs {
  S: number;
  K: number;
  T: number;
  r: number;
  q: number;
  sigma: number;
  price_as_of: string;
  iv_as_of: string;
  r_as_of: string;
  r_source: string;
  contract_last_trade_at: string | null;
}

export interface GreeksExplanations {
  delta: string;
  gamma: string;
  theta: string;
  vega: string;
  rho: string;
}

export interface GreeksResult {
  ticker: string;
  expiration: string;
  option_type: string;
  price: number;
  delta: number;
  gamma: number;
  theta_per_day: number;
  vega: number;
  rho_per_percent: number;
  explanations: GreeksExplanations;
  inputs_used: GreeksInputs;
}

export async function fetchOptionExpirations(ticker: string): Promise<OptionExpirations> {
  const res = await fetch(
    `${BASE_URL}/api/v1/options/${encodeURIComponent(ticker)}/expirations`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<OptionExpirations>;
}

export async function fetchOptionChain(ticker: string, expiration: string): Promise<OptionChain> {
  const res = await fetch(
    `${BASE_URL}/api/v1/options/${encodeURIComponent(ticker)}/chain?expiration=${encodeURIComponent(expiration)}`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<OptionChain>;
}

export type IndicatorType = 'SMA' | 'PRICE' | 'RSI';

export interface IndicatorSchema {
  type: IndicatorType;
  window: number | null;
}

export type ComparatorType = 'CROSSES_ABOVE' | 'CROSSES_BELOW';

export interface RuleSchema {
  left: IndicatorSchema;
  comparator: ComparatorType;
  right: IndicatorSchema | number;
}

export interface StrategySchema {
  entry: RuleSchema;
  exit: RuleSchema;
}

export interface BacktestRequestPayload {
  strategy: StrategySchema;
  cost_pct: number;
  starting_capital: number;
  start: string | null;
  end: string | null;
}

export interface TradeSchema {
  entry_date: string;
  entry_price: number;
  exit_date: string | null;
  exit_price: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  status: 'closed' | 'open';
}

export interface BacktestResponse {
  ticker: string;
  dates: string[];
  equity_curve: number[];
  trades: TradeSchema[];
  total_return_pct: number;
  max_drawdown_pct: number;
  num_trades: number;
  win_rate_pct: number | null;
  final_status: 'flat' | 'open';
  params: Record<string, unknown>;
}

export async function fetchBacktest(
  ticker: string,
  request: BacktestRequestPayload,
): Promise<BacktestResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/backtest/${encodeURIComponent(ticker)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<BacktestResponse>;
}

export async function fetchOptionCalculation(
  ticker: string,
  expiration: string,
  strike: number,
  type: 'call' | 'put',
  ivOverride?: number,
): Promise<GreeksResult> {
  const params = new URLSearchParams({
    expiration,
    strike: String(strike),
    type,
  });
  if (ivOverride != null) params.set('iv', String(ivOverride));
  const res = await fetch(
    `${BASE_URL}/api/v1/options/${encodeURIComponent(ticker)}/calculate?${params.toString()}`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<GreeksResult>;
}
