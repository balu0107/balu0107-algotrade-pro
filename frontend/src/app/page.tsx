"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createChart, CandlestickSeries, ColorType, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import { API_URL } from "@/lib/api";
import { ThemeToggle, useTheme } from "@/components/ThemeToggle";

// --- FIXED TYPES TO MATCH NEW BACKEND ---
type AlgoPrediction = {
  timeframe: string;
  direction: "RISE" | "FALL" | "SIDEWAYS";
  rise_probability: number;
  fall_probability: number;
  target_price: number;
  expected_change_percent: number;
  support: number;
  resistance: number;
  confidence: "Low" | "Medium" | "High";
  confidence_percent: number;
  summary: string;
};

type NewsHeadline = {
  title: string;
  sentiment: "Positive" | "Negative" | "Neutral" | "Mixed";
};

type NewsEventSummary = {
  event: string;
  event_type: string;
  sentiment: number;
  confidence: number;
  source_count: number;
};

type NewsWindow = {
  score: number | null;
  confidence: number;
  reason: string | null;
};

type NewsMomentum = {
  sentiment_change_1h: number | null;
  sentiment_change_6h: number | null;
  sentiment_change_24h: number | null;
  positive_event_velocity: number;
  negative_event_velocity: number;
};

// score/label/headlines/note are the original fields every caller has always
// rendered - kept exactly as-is. Everything below is additive, from the
// news_pipeline's event-based aggregate, and optional: a symbol with no
// pipeline data yet (or a fallback on pipeline error) simply omits them, and
// NewsPanel below degrades to the original plain render in that case.
type NewsSentiment = {
  score: number;
  label: "Positive" | "Negative" | "Neutral" | "Mixed";
  headlines: NewsHeadline[];
  note: string;
  confidence?: number;
  band_label?: string | null;
  raw_score?: number | null;
  article_count?: number;
  unique_event_count?: number;
  positive_events?: number;
  negative_events?: number;
  neutral_events?: number;
  top_events?: NewsEventSummary[];
  windows?: Record<string, NewsWindow>;
  momentum?: NewsMomentum;
  reason?: string | null;
};

type CloseOpenForecast = {
  predicted_close_today: number;
  predicted_open_tomorrow: number;
  close_change_percent: number;
  open_change_percent: number;
  confidence_percent: number;
  close_date: string;
  next_open_date: string;
  rationale: string;
};

type RbiRepoRate = {
  value_percent: number;
  last_updated: string;
  note: string;
};

type Fundamentals = {
  trailing_pe: number | null;
  forward_pe: number | null;
  eps_ttm: number | null;
  price_to_book: number | null;
  book_value: number | null;
  revenue_growth_yoy_percent: number | null;
  earnings_growth_yoy_percent: number | null;
  earnings_growth_qoq_percent: number | null;
  revenue_growth_qoq_percent: number | null;
  dividend_yield_percent: number | null;
  market_cap: number | null;
  beta: number | null;
  week52_high: number | null;
  week52_low: number | null;
  sector: string | null;
  industry: string | null;
  rbi_repo_rate: RbiRepoRate;
};

type PredictionData = {
  active: "INTRADAY" | "DELIVERY";
  market_phase: string;
  intraday: AlgoPrediction;
  delivery: AlgoPrediction;
  news: NewsSentiment;
  forecast: CloseOpenForecast;
};

type SymbolSuggestion = {
  symbol: string;
  name: string;
  current_price: number | null;
  percent_change: number | null;
};

type StockData = {
  symbol: string;
  current_price: number;
  open: number;
  high: number;
  low: number;
  previous_close: number;
  percent_change: number;
  volume: number;
  suggestion: string;
  prediction: PredictionData;
  fundamentals: Fundamentals;
  nifty: { value: number; change: number; is_positive: boolean };
  // Set when a live yfinance fetch failed (e.g. rate-limited) and this is a
  // fallback to the last successfully-fetched response instead of a bare
  // error - optional because most responses are fresh and won't carry it.
  stale?: boolean;
  stale_reason?: string | null;
};

type TopPick = {
  symbol: string;
  sector: string;
  current_price: number;
  open_price: number;
  target_price: number;
  expected_change_percent: number;
  confidence_percent: number;
  traded_value: number;
};

const formatTradedValue = (rupees: number) => {
  if (rupees >= 1e7) return `Rs. ${(rupees / 1e7).toFixed(1)} Cr/day`;
  if (rupees >= 1e5) return `Rs. ${(rupees / 1e5).toFixed(1)} L/day`;
  return `Rs. ${Math.round(rupees).toLocaleString("en-IN")}/day`;
};

type TopPickSectorGroup = {
  sector: string;
  picks: TopPick[];
};

// Snapshot of what a Top Picks/Falls/F&O click was based on at the moment of
// the click - the stock detail modal compares this against its own live,
// on-demand read and surfaces it when they disagree, instead of leaving that
// disagreement unexplained (Top Picks/Falls/F&O only rescan once a day; the
// detail modal always fetches fresh).
type PickOrigin = {
  direction: "RISE" | "FALL";
  confidence_percent: number;
  computed_at: string | null;
};

type TopPicksResponse = {
  direction: "RISE" | "FALL";
  top_overall: TopPick[];
  sectors: TopPickSectorGroup[];
  active_timeframe: "INTRADAY" | "DELIVERY";
  total_available: number;
  scanned_universe_size: number;
  computed_at: string | null;
  scan_cadence: "daily";
};

type OptionIdea = {
  symbol: string;
  sector: string;
  option_type: "CALL" | "PUT";
  current_price: number;
  suggested_strike: number;
  target_underlying_price: number;
  stop_loss_underlying_price: number;
  expected_change_percent: number;
  confidence_percent: number;
  traded_value: number;
};

type OptionIdeaSectorGroup = {
  sector: string;
  picks: OptionIdea[];
};

type FnoIdeasResponse = {
  option_type: "CALL" | "PUT";
  top_overall: OptionIdea[];
  sectors: OptionIdeaSectorGroup[];
  active_timeframe: "INTRADAY" | "DELIVERY";
  total_available: number;
  scanned_universe_size: number;
  computed_at: string | null;
  scan_cadence: "daily";
  disclaimer: string;
};

type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type CandleRange = "1D" | "5D" | "1M" | "6M" | "1Y" | "5Y" | "MAX";
const CANDLE_RANGE_OPTIONS: CandleRange[] = ["1D", "5D", "1M", "6M", "1Y", "5Y", "MAX"];

type WatchDirection = "above" | "below";
type AppTab = "scanner" | "watchlist" | "alerts" | "ipo" | "toppicks" | "topfalls" | "fno";
type GroupType = "watchlist" | "alert";

type AlertItem = {
  id: string;
  symbol: string;
  direction: WatchDirection;
  threshold: number;
  groupId: number | null;
  lastPrice?: number;
  lastChecked?: string;
  status: "idle" | "checking" | "safe" | "triggered" | "error";
  message?: string;
  prediction?: PredictionData;
  alerted?: boolean;
};

type BackendAlertItem = {
  id: number;
  symbol: string;
  upper_threshold: number | null;
  lower_threshold: number | null;
  alert_triggered: number;
  group_id: number | null;
};

const mapBackendAlertItem = (item: BackendAlertItem): AlertItem => ({
  id: String(item.id),
  symbol: item.symbol,
  direction: item.upper_threshold != null ? "above" : "below",
  threshold: item.upper_threshold ?? item.lower_threshold ?? 0,
  groupId: item.group_id,
  status: "idle",
});

type AlertEvent = {
  id: string;
  message: string;
  createdAt: string;
};

type TrackedStock = {
  id: string;
  symbol: string;
  groupId: number | null;
  lastPrice?: number;
  lastChecked?: string;
  status: "idle" | "checking" | "error";
  prediction?: PredictionData;
};

type BackendTrackedStock = {
  id: number;
  symbol: string;
  group_id: number | null;
};

const mapBackendTrackedStock = (item: BackendTrackedStock): TrackedStock => ({
  id: String(item.id),
  symbol: item.symbol,
  groupId: item.group_id,
  status: "idle",
});

type StockGroup = {
  id: number;
  group_type: GroupType;
  name: string;
};

type IpoStatus = "open" | "upcoming";

type IpoItem = {
  company_name: string;
  status: string;
  open_date: string | null;
  close_date: string | null;
  listing_date: string | null;
  price_band: string | null;
  issue_price: number | null;
  lot_size: number | null;
  gmp_percent: number | null;
  subscription_total: number | null;
  confidence_percent: number;
  outlook: "Strong Demand" | "Moderate Demand" | "Weak Demand";
  sentiment: NewsSentiment;
};

type IpoResponse = {
  configured: boolean;
  items: IpoItem[];
  error?: string;
};

const TOP_PICKS_PER_SECTOR = 10;
const MAX_GROUPS = 10;
const QUICK_SYMBOLS = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ZOMATO"];
const TOKEN_STORAGE_KEY = "algotradepro-token";
const LIVE_REFRESH_STORAGE_KEY = "algotradepro-refresh-interval-ms";
const DEFAULT_LIVE_REFRESH_MS = 60000;

const REFRESH_INTERVAL_OPTIONS = [
  { label: "1s", ms: 1000 },
  { label: "5s", ms: 5000 },
  { label: "10s", ms: 10000 },
  { label: "30s", ms: 30000 },
  { label: "1m", ms: 60000 },
  { label: "2m", ms: 120000 },
  { label: "5m", ms: 300000 },
];

const formatIsoDate = (isoDate: string) => {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) return isoDate;
  return new Date(year, month - 1, day).toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const getSavedInterval = (storageKey: string, fallbackMs: number) => {
  if (typeof window === "undefined") return fallbackMs;
  const saved = Number(window.localStorage.getItem(storageKey));
  return REFRESH_INTERVAL_OPTIONS.some((option) => option.ms === saved) ? saved : fallbackMs;
};

const getSavedToken = () => {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
};

const ACTIVE_TAB_STORAGE_KEY = "algotradepro-active-tab";
const APP_TABS: AppTab[] = ["scanner", "watchlist", "alerts", "ipo", "toppicks", "topfalls", "fno"];

const getSavedActiveTab = (): AppTab | null => {
  if (typeof window === "undefined") return null;
  const saved = window.localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
  return APP_TABS.includes(saved as AppTab) ? (saved as AppTab) : null;
};

const WATCHLIST_SUBTAB_STORAGE_KEY = "algotradepro-watchlist-subtab";
const ALERTS_SUBTAB_STORAGE_KEY = "algotradepro-alerts-subtab";

const getSavedSubtab = (storageKey: string): string | null => {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(storageKey);
};

const getInitialNotificationPermission = () => {
  if (typeof window === "undefined" || !("Notification" in window)) return "default";
  return Notification.permission;
};

// --- UPDATED PREDICTION PANEL ---
function PredictionPanel({ data, compact = false }: { data: PredictionData; compact?: boolean }) {
  // Select the active prediction (Intraday or Delivery) based on the market phase
  const activeKey = data.active.toLowerCase() as "intraday" | "delivery";
  const prediction = data[activeKey];

  const isRise = prediction.direction === "RISE";
  const isFall = prediction.direction === "FALL";
  const directionClass = isRise ? "text-emerald-300" : isFall ? "text-rose-300" : "text-[var(--warning-text)]";
  const barClass = isRise ? "bg-emerald-500" : isFall ? "bg-rose-500" : "bg-amber-500";
  const primaryProbability = isFall ? prediction.fall_probability : prediction.rise_probability;

  return (
    <div className={`rounded-lg border border-[var(--border)] bg-[var(--surface-0)] ${compact ? "p-3" : "p-4"}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-widest text-[var(--text-faint)]">
            {prediction.timeframe} PREDICTION
          </p>
          <p className={`mt-1 text-2xl font-black ${directionClass}`}>
            {prediction.direction} {primaryProbability}%
          </p>
          {!compact && (
            <>
              <p className="mt-2 text-sm text-[var(--text-muted)]">{prediction.summary}</p>
              <p className="mt-1 text-xs font-semibold text-blue-400">{data.market_phase}</p>
            </>
          )}
        </div>
        <div className="text-left sm:text-right">
          <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Estimated target</p>
          <p className="text-xl font-black text-[var(--text-primary)]">Rs. {prediction.target_price}</p>
          <p className={`text-sm font-bold ${directionClass}`}>
            {prediction.expected_change_percent > 0 ? "+" : ""}
            {prediction.expected_change_percent}%
          </p>
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-2 flex justify-between text-xs font-bold text-[var(--text-faint)]">
          <span>Rise {prediction.rise_probability}%</span>
          <span>Fall {prediction.fall_probability}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-2)]">
          <div className={`h-full ${barClass}`} style={{ width: `${primaryProbability}%` }}></div>
        </div>
      </div>

      {!compact && (
        <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
          <div>
            <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Support</p>
            <p className="font-bold text-[var(--text-primary)]">Rs. {prediction.support}</p>
          </div>
          <div>
            <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Resistance</p>
            <p className="font-bold text-[var(--text-primary)]">Rs. {prediction.resistance}</p>
          </div>
          <div>
            <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Confidence</p>
            <p className="font-bold text-[var(--text-primary)]">{prediction.confidence}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function ForecastPanel({ forecast, compact = false }: { forecast: CloseOpenForecast; compact?: boolean }) {
  const isCloseUp = forecast.close_change_percent >= 0;
  const isOpenUp = forecast.open_change_percent >= 0;

  return (
    <div className={`rounded-lg border border-[var(--border)] bg-[var(--surface-0)] ${compact ? "p-3" : "p-4"}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-black uppercase tracking-widest text-[var(--text-faint)]">Close &amp; Next-Open Forecast</p>
        <span className="whitespace-nowrap rounded-full bg-blue-500/20 px-2 py-0.5 text-xs font-bold text-blue-300">
          {forecast.confidence_percent}% confidence
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Close - {formatIsoDate(forecast.close_date)}</p>
          <p className="text-lg font-black text-[var(--text-primary)]">Rs. {forecast.predicted_close_today}</p>
          <p className={`text-xs font-bold ${isCloseUp ? "text-emerald-400" : "text-rose-400"}`}>
            {isCloseUp ? "+" : ""}
            {forecast.close_change_percent}%
          </p>
        </div>
        <div>
          <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Open - {formatIsoDate(forecast.next_open_date)}</p>
          <p className="text-lg font-black text-[var(--text-primary)]">Rs. {forecast.predicted_open_tomorrow}</p>
          <p className={`text-xs font-bold ${isOpenUp ? "text-emerald-400" : "text-rose-400"}`}>
            {isOpenUp ? "+" : ""}
            {forecast.open_change_percent}%
          </p>
        </div>
      </div>
      {!compact && <p className="mt-3 text-xs text-[var(--text-faint)]">{forecast.rationale}</p>}
    </div>
  );
}

function NewsPanel({ news }: { news: NewsSentiment }) {
  const labelClass =
    news.label === "Positive"
      ? "text-emerald-400"
      : news.label === "Negative"
        ? "text-rose-400"
        : news.label === "Mixed"
          ? "text-amber-400"
          : "text-[var(--warning-text)]";

  const hasEventData = news.reason == null && (news.unique_event_count ?? 0) > 0;
  const momentum24h = news.momentum?.sentiment_change_24h ?? null;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-black uppercase tracking-widest text-[var(--text-faint)]">News Sentiment</p>
        <div className="flex items-center gap-2">
          {hasEventData && typeof news.confidence === "number" && (
            <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-muted)]">
              {Math.round(news.confidence * 100)}% confidence
            </span>
          )}
          <span className={`text-sm font-black ${labelClass}`}>{news.label}</span>
        </div>
      </div>
      <p className="mt-1 text-xs text-[var(--text-faint)]">{news.note}</p>

      {hasEventData && (
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[var(--text-muted)]">
          <span>
            {news.unique_event_count} event{news.unique_event_count === 1 ? "" : "s"} / {news.article_count} article
            {news.article_count === 1 ? "" : "s"} (24h)
          </span>
          {momentum24h != null && (
            <span className={momentum24h > 0 ? "text-emerald-400" : momentum24h < 0 ? "text-rose-400" : ""}>
              {momentum24h > 0 ? "▲" : momentum24h < 0 ? "▼" : "•"} {Math.abs(momentum24h).toFixed(0)} pts vs prior 24h
            </span>
          )}
        </div>
      )}

      {hasEventData && news.top_events && news.top_events.length > 0 && (
        <div className="mt-3 space-y-1.5 border-t border-[var(--border)] pt-3">
          <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-faint)]">Top Events</p>
          {news.top_events.slice(0, 3).map((event, index) => (
            <div key={index} className="flex items-start justify-between gap-2 text-xs">
              <span className="text-[var(--text-secondary)]">{event.event}</span>
              <span
                className={`shrink-0 font-bold ${
                  event.sentiment > 0.1 ? "text-emerald-400" : event.sentiment < -0.1 ? "text-rose-400" : "text-[var(--text-faint)]"
                }`}
              >
                {event.source_count} source{event.source_count === 1 ? "" : "s"}
              </span>
            </div>
          ))}
        </div>
      )}

      {news.headlines.length > 0 && (
        <ul className="mt-3 space-y-2">
          {news.headlines.map((headline, index) => (
            <li key={index} className="flex items-start gap-2 text-sm">
              <span
                className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                  headline.sentiment === "Positive"
                    ? "bg-emerald-400"
                    : headline.sentiment === "Negative"
                      ? "bg-rose-400"
                      : headline.sentiment === "Mixed"
                        ? "bg-amber-400"
                        : "bg-[var(--text-faint)]"
                }`}
              />
              <span className="text-[var(--text-secondary)]">{headline.title}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- CANDLESTICK CHART with a Google-Finance-style range selector ---
function CandlestickChart({ symbol, token }: { symbol: string; token: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [range, setRange] = useState<CandleRange>("1M");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#94a3b8" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      width: containerRef.current.clientWidth,
      height: 280,
      timeScale: { timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: "#334155" },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#34d399",
      downColor: "#fb7185",
      borderVisible: false,
      wickUpColor: "#34d399",
      wickDownColor: "#fb7185",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError("");

    fetch(`${API_URL}/api/stock/${symbol}/candles?range=${range}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("Could not load chart data.");
        return (await res.json()) as { candles: Candle[] };
      })
      .then((data) => {
        if (cancelled || !seriesRef.current) return;
        seriesRef.current.setData(
          data.candles.map((candle) => ({
            time: candle.time as UTCTimestamp,
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
          })),
        );
        chartRef.current?.timeScale().fitContent();
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load chart data.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, range, token]);

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-black uppercase tracking-widest text-[var(--text-faint)]">Price Chart</p>
        <div className="flex gap-1 rounded-lg border border-[var(--border-strong)] bg-[var(--surface-1)] p-1">
          {CANDLE_RANGE_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setRange(option)}
              className={`rounded px-2 py-1 text-xs font-bold transition ${
                range === option ? "bg-blue-600 text-white" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="mb-2 text-xs text-rose-400">{error}</p>}
      {isLoading && !error && <p className="mb-2 text-xs text-[var(--text-faint)]">Loading chart...</p>}
      <div ref={containerRef} />
    </div>
  );
}

const formatMarketCap = (value: number | null) => {
  if (value === null || value === undefined) return "N/A";
  if (value >= 1e12) return `Rs. ${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `Rs. ${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e7) return `Rs. ${(value / 1e7).toFixed(2)}Cr`;
  return `Rs. ${value.toLocaleString("en-IN")}`;
};

const formatPercent = (value: number | null) => (value === null || value === undefined ? "N/A" : `${value}%`);
const formatNumber = (value: number | null) => (value === null || value === undefined ? "N/A" : value);

function FundamentalsPanel({ fundamentals }: { fundamentals: Fundamentals }) {
  const looksLikeFund = !fundamentals.sector && !fundamentals.trailing_pe && !fundamentals.eps_ttm;
  const rows = [
    { label: "P/E (Trailing)", value: formatNumber(fundamentals.trailing_pe) },
    { label: "P/E (Forward)", value: formatNumber(fundamentals.forward_pe) },
    { label: "EPS (TTM)", value: formatNumber(fundamentals.eps_ttm) },
    { label: "Price / Book", value: formatNumber(fundamentals.price_to_book) },
    { label: "Revenue Growth (YoY)", value: formatPercent(fundamentals.revenue_growth_yoy_percent) },
    { label: "Earnings Growth (YoY)", value: formatPercent(fundamentals.earnings_growth_yoy_percent) },
    { label: "Earnings Growth (QoQ)", value: formatPercent(fundamentals.earnings_growth_qoq_percent) },
    { label: "Revenue Growth (QoQ)", value: formatPercent(fundamentals.revenue_growth_qoq_percent) },
    { label: "Dividend Yield", value: formatPercent(fundamentals.dividend_yield_percent) },
    { label: "Market Cap", value: formatMarketCap(fundamentals.market_cap) },
    { label: "Beta", value: formatNumber(fundamentals.beta) },
    { label: "52-Week High", value: fundamentals.week52_high ? `Rs. ${fundamentals.week52_high}` : "N/A" },
    { label: "52-Week Low", value: fundamentals.week52_low ? `Rs. ${fundamentals.week52_low}` : "N/A" },
    { label: "Sector", value: fundamentals.sector ?? "N/A" },
    { label: "Industry", value: fundamentals.industry ?? "N/A" },
  ];

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-4">
      <p className="mb-3 text-xs font-black uppercase tracking-widest text-[var(--text-faint)]">Fundamentals</p>
      {looksLikeFund && (
        <p className="mb-3 rounded bg-[var(--warning-wash)] p-2 text-xs text-[var(--warning-text)]">
          Most fields are N/A because this looks like an ETF/fund, not an operating company - things like P/E,
          earnings growth, and sector don&apos;t apply to it.
        </p>
      )}
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-3">
        {rows.map((row) => (
          <div key={row.label}>
            <p className="text-xs font-bold uppercase text-[var(--text-faint)]">{row.label}</p>
            <p className="font-semibold text-[var(--text-primary)]">{row.value}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 border-t border-[var(--border)] pt-3 text-xs text-[var(--text-faint)]">
        RBI Repo Rate: <span className="font-bold text-[var(--text-secondary)]">{fundamentals.rbi_repo_rate.value_percent}%</span> as
        of {fundamentals.rbi_repo_rate.last_updated} - {fundamentals.rbi_repo_rate.note}
      </div>
    </div>
  );
}

// --- IN-APP SYMBOL AUTOCOMPLETE (no external redirects) ---
function SymbolAutocomplete({
  value,
  onChange,
  onSelect,
  token,
  placeholder,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  onSelect?: (symbol: string) => void;
  token: string | null;
  placeholder: string;
  className: string;
}) {
  const [suggestions, setSuggestions] = useState<SymbolSuggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token || value.trim().length === 0) {
      setSuggestions([]);
      setIsOpen(false);
      return;
    }

    const timeoutId = window.setTimeout(() => {
      fetch(`${API_URL}/api/symbols/search?q=${encodeURIComponent(value.trim())}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => (res.ok ? (res.json() as Promise<SymbolSuggestion[]>) : []))
        .then((data) => {
          setSuggestions(data);
          setIsOpen(data.length > 0);
        })
        .catch(() => {
          // Ignore network hiccups - the user can keep typing regardless.
        });
    }, 250);

    return () => window.clearTimeout(timeoutId);
  }, [value, token]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative flex-1">
      <input
        type="text"
        placeholder={placeholder}
        className={className}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setIsOpen(suggestions.length > 0)}
        autoComplete="off"
      />
      {isOpen && suggestions.length > 0 && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-[var(--border-strong)] bg-[var(--surface-1)] shadow-xl">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion.symbol}
              type="button"
              onClick={() => {
                onChange(suggestion.symbol);
                onSelect?.(suggestion.symbol);
                setIsOpen(false);
              }}
              className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition hover:bg-[var(--surface-2)]"
            >
              <span className="flex flex-col">
                <span className="font-bold text-[var(--text-primary)]">{suggestion.symbol}</span>
                <span className="truncate text-xs text-[var(--text-muted)]">{suggestion.name}</span>
              </span>
              {suggestion.current_price != null && (
                <span className="shrink-0 text-right">
                  <span className="block font-bold text-[var(--text-primary)]">Rs. {suggestion.current_price}</span>
                  {suggestion.percent_change != null && (
                    <span
                      className={`block text-xs font-bold ${
                        suggestion.percent_change >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {suggestion.percent_change >= 0 ? "+" : ""}
                      {suggestion.percent_change}%
                    </span>
                  )}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// --- IN-APP STOCK DETAIL (Basic / Advanced) - replaces the old Yahoo redirect ---
function StockDetailModal({
  symbol,
  token,
  origin,
  refreshIntervalMs,
  onClose,
}: {
  symbol: string;
  token: string;
  origin: PickOrigin | null;
  // Drives the background refresh below, but deliberately has no picker
  // control of its own here - it's the exact same global setting already
  // exposed on Watchlist/Alerts/Scanner/Top Picks/Falls/F&O, so showing a
  // second dropdown for it in this modal would just be redundant UI.
  refreshIntervalMs: number;
  onClose: () => void;
}) {
  const [detailTab, setDetailTab] = useState<"basic" | "advanced">("basic");
  const [data, setData] = useState<StockData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const isFetchingRef = useRef(false);
  const fetchDetail = useCallback(async (quiet: boolean) => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    if (!quiet) {
      setIsLoading(true);
      setError("");
    }
    try {
      const res = await fetch(`${API_URL}/api/stock/${symbol}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error("Could not load this stock.");
      const result = (await res.json()) as StockData;
      if (isMountedRef.current) setData(result);
    } catch (err) {
      // A quiet background refresh failing just leaves the last-good data on screen.
      if (!quiet && isMountedRef.current) {
        setError(err instanceof Error ? err.message : "Could not load this stock.");
      }
    } finally {
      isFetchingRef.current = false;
      if (!quiet && isMountedRef.current) setIsLoading(false);
    }
  }, [symbol, token]);

  useEffect(() => {
    setData(null);
    fetchDetail(false);
  }, [fetchDetail]);

  useEffect(() => {
    const intervalId = window.setInterval(() => fetchDetail(true), refreshIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [fetchDetail, refreshIntervalMs]);

  const activeKey = data ? (data.prediction.active.toLowerCase() as "intraday" | "delivery") : "intraday";
  const activePrediction = data?.prediction[activeKey];
  const topProbability = activePrediction
    ? Math.max(activePrediction.rise_probability, activePrediction.fall_probability)
    : 0;

  // Top Picks/Falls/F&O only rescan once a day, but this modal always fetches
  // live - on a volatile stock the two can genuinely disagree by the time you
  // click in. SIDEWAYS is excluded: it's not a contradiction of RISE/FALL, just
  // a weaker read, and calling that out too would just be noise.
  const originMismatch =
    origin !== null &&
    activePrediction !== undefined &&
    activePrediction.direction !== "SIDEWAYS" &&
    activePrediction.direction !== origin.direction;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto overflow-x-hidden rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-2xl font-black text-[var(--text-primary)]">
            {symbol} <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">NSE</span>
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-xl text-[var(--text-muted)] transition hover:text-[var(--text-primary)]"
          >
            &times;
          </button>
        </div>

        <div className="mb-4 flex rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-1" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={detailTab === "basic"}
            onClick={() => setDetailTab("basic")}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-bold transition ${
              detailTab === "basic" ? "bg-blue-600 text-white" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            Basic
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={detailTab === "advanced"}
            onClick={() => setDetailTab("advanced")}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-bold transition ${
              detailTab === "advanced" ? "bg-blue-600 text-white" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            Advanced
          </button>
        </div>

        {isLoading && <p className="py-10 text-center text-[var(--text-muted)]">Loading...</p>}
        {error && <p className="py-10 text-center text-rose-400">{error}</p>}

        {data && data.stale && (
          <div className="mb-3 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-surface)] px-3 py-2 text-xs text-[var(--warning-text)]">
            Showing last known data - live prices are temporarily unavailable.
            {data.stale_reason ? ` (${data.stale_reason})` : ""}
          </div>
        )}

        {originMismatch && origin && activePrediction && (
          <div className="mb-3 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-surface)] px-3 py-2 text-xs text-[var(--warning-text)]">
            {origin.computed_at ? `Today's scan (${new Date(origin.computed_at).toLocaleString()})` : "Today's scan"} called this a{" "}
            <span className="font-bold">{origin.direction}</span> pick at {origin.confidence_percent}% confidence. Live conditions
            have since shifted to <span className="font-bold">{activePrediction.direction}</span> at{" "}
            {activePrediction.confidence_percent}% confidence - Top Picks/Falls/F&amp;O only rescan once a day, this view is
            always live, and on a volatile stock the two can genuinely disagree.
          </div>
        )}

        {data && activePrediction && (
          <>
            {detailTab === "basic" ? (
              <div className="space-y-4">
                <div>
                  <p className="text-4xl font-black text-[var(--text-primary)]">Rs. {data.current_price}</p>
                  <p className={`text-lg font-bold ${data.percent_change >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {data.percent_change >= 0 ? "Up" : "Down"} {Math.abs(data.percent_change)}% today
                  </p>
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-4 text-sm text-[var(--text-secondary)]">
                  Our <span className="font-bold text-[var(--text-primary)]">{activePrediction.timeframe}</span> algorithm currently
                  reads this as a <span className="font-bold text-[var(--text-primary)]">{activePrediction.direction}</span> signal,
                  with about <span className="font-bold text-[var(--text-primary)]">{topProbability}%</span> odds of that move and{" "}
                  <span className="font-bold text-[var(--text-primary)]">{activePrediction.confidence_percent}%</span> confidence.
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-4 text-sm text-[var(--text-secondary)]">
                  <p>
                    Closing <span className="font-bold text-[var(--text-primary)]">{formatIsoDate(data.prediction.forecast.close_date)}</span>{" "}
                    near <span className="font-bold text-[var(--text-primary)]">Rs. {data.prediction.forecast.predicted_close_today}</span>
                  </p>
                  <p className="mt-2">
                    Opening <span className="font-bold text-[var(--text-primary)]">{formatIsoDate(data.prediction.forecast.next_open_date)}</span>{" "}
                    near <span className="font-bold text-[var(--text-primary)]">Rs. {data.prediction.forecast.predicted_open_tomorrow}</span>
                  </p>
                  <p className="mt-2 text-xs text-[var(--text-faint)]">{data.prediction.forecast.confidence_percent}% confidence</p>
                </div>
                <p
                  className={`text-2xl font-black uppercase ${
                    data.suggestion.includes("DON'T") || data.suggestion.includes("SHORT")
                      ? "text-rose-400"
                      : data.suggestion.includes("BUY")
                        ? "text-emerald-400"
                        : "text-[var(--warning-text)]"
                  }`}
                >
                  {data.suggestion}
                </p>
                <p className="text-xs text-[var(--text-faint)]">
                  Simple view for a quick read. Switch to Advanced for the full breakdown.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-3">
                    <p className="text-xs font-bold text-[var(--text-faint)]">OPEN</p>
                    <p className="font-semibold text-[var(--text-primary)]">Rs. {data.open}</p>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-3">
                    <p className="text-xs font-bold text-[var(--text-faint)]">HIGH / LOW</p>
                    <p className="font-semibold text-[var(--text-primary)]">
                      Rs. {data.high} / Rs. {data.low}
                    </p>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-3">
                    <p className="text-xs font-bold text-[var(--text-faint)]">VOLUME</p>
                    <p className="font-semibold text-[var(--text-primary)]">{(data.volume / 100000).toFixed(2)}L</p>
                  </div>
                </div>
                <CandlestickChart symbol={symbol} token={token} />
                <PredictionPanel data={data.prediction} />
                <ForecastPanel forecast={data.prediction.forecast} />
                <FundamentalsPanel fundamentals={data.fundamentals} />
                <NewsPanel news={data.prediction.news} />
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-4 text-sm text-[var(--text-secondary)]">
                  NIFTY 50 trend: {data.nifty.is_positive ? "Up" : "Down"} {data.nifty.value}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// --- Shared refresh-interval picker, reused across Watchlist / Top Picks / Top Falls / F&O ---
function RefreshIntervalPicker({ valueMs, onChange }: { valueMs: number; onChange: (ms: number) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm font-bold text-[var(--text-muted)]">
      Refresh
      <select
        value={valueMs}
        onChange={(e) => onChange(Number(e.target.value))}
        className="rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-blue-500"
      >
        {REFRESH_INTERVAL_OPTIONS.map((option) => (
          <option key={option.ms} value={option.ms}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// --- Chrome-style tab strip look, shared by the main nav, the Top Picks/Top
// Falls sector sub-tabs, and the Watchlist/Alerts group tabs: active tab pops
// forward (fills with the surrounding surface, border on 3 sides, no bottom
// border so it visually merges with what's below it), inactive tabs sit dull
// against the strip's baseline - like an actual browser tab bar, not a row of
// pill buttons in a box.
// Deliberately no scrollbar-visibility class baked in here - the main nav
// hides its scrollbar (.tab-strip), sub-tab strips (sectors, groups) show a
// thin one instead (.sub-tab-strip) as a manual fallback, and mixing both
// classes on one element would fight over the same ::-webkit-scrollbar rule.
// overflow-y-hidden is NOT optional here: per the CSS overflow spec, setting
// only overflow-x forces overflow-y to also compute to "auto" - a 1px mismatch
// from the border/items-end alignment was enough to pop a pointless vertical
// scrollbar on this single-row strip.
const CHROME_TAB_STRIP_CLASS = "flex items-end gap-0.5 overflow-x-auto overflow-y-hidden border-b border-[var(--border-strong)]";

function chromeTabClass(isActive: boolean) {
  return `shrink-0 -mb-px rounded-t-lg border border-b-0 px-4 py-2 text-sm font-bold transition ${
    isActive
      ? "border-[var(--border-strong)] bg-[var(--surface-1)] text-[var(--text-primary)]"
      : "border-transparent text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)]"
  }`;
}

// Scrolls the active tab to the front of its strip whenever it changes.
// Deliberately NOT one shared ref conditionally handed to whichever button is
// active (`ref={isActive ? activeRef : undefined}`) - that only worked going
// forward. React processes ref attach/detach per-fiber in render order: going
// forward, the earlier (old) button's detach runs before the later (new)
// button's attach, so the final ref.current is correct; going backward, the
// later (old) button's detach runs AFTER the earlier (new) button's attach,
// wiping ref.current back to null right after it was set. Every button
// registering itself into a Map, independent of active state, sidesteps that
// ordering hazard entirely - each button's own attach/detach never touches
// another button's entry.
function useActiveTabScroll(activeKey: string) {
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonsRef = useRef(new Map<string, HTMLButtonElement>());

  const registerButton = (key: string) => (el: HTMLButtonElement | null) => {
    if (el) buttonsRef.current.set(key, el);
    else buttonsRef.current.delete(key);
  };

  useEffect(() => {
    const container = containerRef.current;
    const button = buttonsRef.current.get(activeKey);
    if (!container || !button) return;
    const delta = button.getBoundingClientRect().left - container.getBoundingClientRect().left;
    container.scrollTo({ left: container.scrollLeft + delta, behavior: "smooth" });
  }, [activeKey]);

  return { containerRef, registerButton };
}

const MAIN_TABS: { id: AppTab; label: string }[] = [
  { id: "scanner", label: "Scanner" },
  { id: "watchlist", label: "Watchlist" },
  { id: "alerts", label: "Alerts" },
  { id: "ipo", label: "IPO" },
  { id: "toppicks", label: "Top Picks" },
  { id: "topfalls", label: "Top Falls" },
  { id: "fno", label: "F&O" },
];

function MainTabStrip({
  activeTab,
  onSelect,
  triggeredCount,
}: {
  activeTab: AppTab;
  onSelect: (tab: AppTab) => void;
  triggeredCount: number;
}) {
  const { containerRef, registerButton } = useActiveTabScroll(activeTab);
  return (
    <div ref={containerRef} className={`${CHROME_TAB_STRIP_CLASS} tab-strip px-2`} role="tablist">
      {MAIN_TABS.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            ref={registerButton(tab.id)}
            onClick={() => onSelect(tab.id)}
            className={chromeTabClass(isActive)}
          >
            {tab.label}
            {tab.id === "alerts" && triggeredCount > 0 && (
              <span className="ml-2 rounded-full bg-rose-500 px-2 py-0.5 text-xs text-white">{triggeredCount}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// --- Shared named-group sub-tab bar, used by both Watchlist and Alerts to
// organize stocks into up to 10 user-created folders. Controlled component -
// no internal data-fetching, modeled on TopPicksTab's sector sub-tab strip.
function GroupTabBar({
  groups,
  activeGroupId,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: {
  groups: StockGroup[];
  activeGroupId: number | null;
  onSelect: (groupId: number | null) => void;
  onCreate: (name: string) => void;
  onRename: (groupId: number, name: string) => void;
  onDelete: (groupId: number) => void;
}) {
  const [isAdding, setIsAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const activeGroup = groups.find((g) => g.id === activeGroupId) ?? null;
  const groupKey = (id: number | null) => (id == null ? "all" : String(id));
  const { containerRef, registerButton } = useActiveTabScroll(groupKey(activeGroupId));

  const submitNewGroup = () => {
    const trimmed = newName.trim();
    if (trimmed) onCreate(trimmed);
    setNewName("");
    setIsAdding(false);
  };

  return (
    <div ref={containerRef} className={`${CHROME_TAB_STRIP_CLASS} sub-tab-strip`} role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={activeGroupId === null}
        ref={registerButton(groupKey(null))}
        onClick={() => onSelect(null)}
        className={chromeTabClass(activeGroupId === null)}
      >
        All
      </button>
      {groups.map((group) => (
        <button
          key={group.id}
          type="button"
          role="tab"
          aria-selected={activeGroupId === group.id}
          ref={registerButton(groupKey(group.id))}
          onClick={() => onSelect(group.id)}
          className={chromeTabClass(activeGroupId === group.id)}
        >
          {group.name}
        </button>
      ))}

      {isAdding ? (
        <span className="flex shrink-0 items-center gap-1">
          <input
            autoFocus
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitNewGroup();
              if (e.key === "Escape") { setIsAdding(false); setNewName(""); }
            }}
            placeholder="Group name"
            className="w-32 rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-blue-500"
          />
          <button type="button" onClick={submitNewGroup} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-bold text-white transition hover:bg-emerald-500">
            Add
          </button>
        </span>
      ) : groups.length < MAX_GROUPS ? (
        <button
          type="button"
          onClick={() => setIsAdding(true)}
          className="shrink-0 rounded-lg border border-dashed border-[var(--border-strong)] px-4 py-2 text-sm font-bold text-[var(--text-muted)] transition hover:text-[var(--text-primary)]"
        >
          + New
        </button>
      ) : null}

      {activeGroup && (
        <span className="flex shrink-0 items-center gap-1 text-xs text-[var(--text-faint)]">
          <button
            type="button"
            onClick={() => {
              const name = window.prompt("Rename group", activeGroup.name);
              if (name && name.trim()) onRename(activeGroup.id, name.trim());
            }}
            className="underline decoration-dotted hover:text-[var(--text-primary)]"
          >
            Rename
          </button>
          <button
            type="button"
            onClick={() => {
              if (window.confirm(`Delete "${activeGroup.name}"? Stocks in it will move to "All", not be deleted.`)) {
                onDelete(activeGroup.id);
              }
            }}
            className="underline decoration-dotted hover:text-rose-300"
          >
            Delete
          </button>
        </span>
      )}
    </div>
  );
}

type LiveQuote = { current_price: number; percent_change: number };

// Refreshes just the current price/percent-change for a bounded set of
// symbols already on screen - shared by Top Picks/Falls (TopPicksTab) and
// F&O (FnoTab), both of which otherwise only get a fresh number once a day
// from the backend's own scan cache. Direction/confidence/target intentionally
// stay pinned to that once-daily call; only the price ticks live here.
function useLiveQuotes(token: string, symbols: string[], refreshIntervalMs: number) {
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const isFetchingRef = useRef(false);
  // A stable string key so the effects below don't refire just because
  // `symbols` is a new array instance with the same contents every render.
  const symbolsKey = symbols.join(",");

  const fetchQuotes = useCallback(async () => {
    if (!token || !symbolsKey || isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      const res = await fetch(`${API_URL}/api/quotes?symbols=${encodeURIComponent(symbolsKey)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = (await res.json()) as { quotes: Record<string, LiveQuote> };
      setQuotes((current) => ({ ...current, ...data.quotes }));
    } catch {
      // A failed quote refresh just leaves the last-known prices on screen.
    } finally {
      isFetchingRef.current = false;
    }
  }, [token, symbolsKey]);

  useEffect(() => {
    fetchQuotes();
  }, [fetchQuotes]);

  useEffect(() => {
    const intervalId = window.setInterval(fetchQuotes, refreshIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [fetchQuotes, refreshIntervalMs]);

  return quotes;
}

// --- TOP PICKS / TOP FALLS (same scan, opposite direction) ---
function TopPicksTab({
  token,
  direction,
  refreshIntervalMs,
  onChangeRefreshIntervalMs,
  onSelectSymbol,
}: {
  token: string;
  direction: "RISE" | "FALL";
  refreshIntervalMs: number;
  onChangeRefreshIntervalMs: (ms: number) => void;
  onSelectSymbol: (symbol: string, origin?: PickOrigin) => void;
}) {
  const [sectors, setSectors] = useState<TopPickSectorGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [meta, setMeta] = useState<TopPicksResponse | null>(null);
  const [section, setSection] = useState("overall");
  const { containerRef: sectionTabContainerRef, registerButton: registerSectionTab } = useActiveTabScroll(section);

  const isRise = direction === "RISE";
  const accentClass = isRise ? "text-emerald-400" : "text-rose-400";
  const hoverBorderClass = isRise ? "hover:border-emerald-500/50" : "hover:border-rose-500/50";

  const isFetchingRef = useRef(false);
  const fetchPicks = useCallback(async () => {
    if (!token || isFetchingRef.current) return;
    isFetchingRef.current = true;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/top-picks?direction=${direction}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Could not load this scan.");
      const data = (await res.json()) as TopPicksResponse;
      setSectors(data.sectors);
      setMeta(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this scan.");
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  }, [token, direction]);

  useEffect(() => {
    setSection("overall");
    fetchPicks();
  }, [fetchPicks]);

  const activePicks =
    section === "overall" ? meta?.top_overall ?? [] : sectors.find((group) => group.sector === section)?.picks ?? [];
  const visibleSymbols = activePicks.map((pick) => pick.symbol);
  const liveQuotes = useLiveQuotes(token, visibleSymbols, refreshIntervalMs);

  return (
    <main className="mx-auto max-w-3xl space-y-6">
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-6">
        <div className="mb-2 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-2xl font-black text-[var(--text-primary)]">Top Intraday {isRise ? "Picks" : "Falls"}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Scans {meta?.scanned_universe_size ?? "the full"} NSE directory - top 10 overall, plus the top{" "}
              {TOP_PICKS_PER_SECTOR} in each sector.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <RefreshIntervalPicker valueMs={refreshIntervalMs} onChange={onChangeRefreshIntervalMs} />
            <button
              type="button"
              onClick={() => fetchPicks()}
              disabled={loading}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-blue-500 disabled:opacity-50"
            >
              {loading ? "Scanning..." : "Refresh"}
            </button>
          </div>
        </div>
        <p className="text-xs text-[var(--text-faint)]">
          The price shown below on each pick refreshes on the interval above. Direction, target, and confidence stay
          as today&apos;s scan called them - see the note below.
        </p>
        {meta?.computed_at && (
          <p className="text-xs text-[var(--text-faint)]">
            Computed {new Date(meta.computed_at).toLocaleString()} - today&apos;s picks are a stable call for the day,
            not a live feed, so they won&apos;t change again until tomorrow&apos;s scan.
          </p>
        )}
        {meta?.active_timeframe && (
          <p className="mt-1 text-xs font-bold text-blue-400">
            Scoring by {meta.active_timeframe} right now
            {meta.active_timeframe === "DELIVERY" ? " - markets are closed, so this uses daily data, not live intraday ticks" : ""}
            . These numbers match what you&apos;ll see in each stock&apos;s detail view.
          </p>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-rose-900 bg-rose-950/50 p-4 text-center font-medium text-rose-400">
          {error}
        </div>
      )}

      {loading && sectors.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
          Scanning the market - this scans the full directory, so it can take a bit longer the first time.
        </div>
      )}

      {!loading && !error && sectors.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
          No stocks in today&apos;s scan currently show a {isRise ? "rising" : "falling"} signal.
        </div>
      )}

      {sectors.length > 0 && (
        <>
          <div ref={sectionTabContainerRef} className={`${CHROME_TAB_STRIP_CLASS} sub-tab-strip`} role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={section === "overall"}
              ref={registerSectionTab("overall")}
              onClick={() => setSection("overall")}
              className={chromeTabClass(section === "overall")}
            >
              Top 10 Overall
            </button>
            {sectors.map((group) => (
              <button
                key={group.sector}
                type="button"
                role="tab"
                aria-selected={section === group.sector}
                ref={registerSectionTab(group.sector)}
                onClick={() => setSection(group.sector)}
                className={chromeTabClass(section === group.sector)}
              >
                {group.sector} <span className="text-xs opacity-70">({group.picks.length})</span>
              </button>
            ))}
          </div>

          <div className="grid gap-3">
            {activePicks.map((pick, index) => (
              <button
                key={pick.symbol}
                type="button"
                onClick={() =>
                  onSelectSymbol(pick.symbol, {
                    direction,
                    confidence_percent: pick.confidence_percent,
                    computed_at: meta?.computed_at ?? null,
                  })
                }
                className={`flex items-center justify-between gap-4 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-4 text-left transition ${hoverBorderClass}`}
              >
                <div className="flex items-center gap-4">
                  <span className="w-6 text-lg font-black text-[var(--text-faint)]">{index + 1}</span>
                  <div>
                    <p className="text-lg font-black text-blue-300">{pick.symbol}</p>
                    <p className="text-sm text-[var(--text-muted)]">
                      Open Rs. {pick.open_price} &rarr; target Rs. {pick.target_price}
                    </p>
                    <p className="text-xs text-[var(--text-faint)]">{formatTradedValue(pick.traded_value)} traded</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Current</p>
                  <p className="text-lg font-black text-[var(--text-primary)]">Rs. {liveQuotes[pick.symbol]?.current_price ?? pick.current_price}</p>
                  <p className={`text-sm font-black ${accentClass}`}>
                    {isRise ? "+" : ""}
                    {pick.expected_change_percent}%
                  </p>
                  <p className="text-xs font-bold uppercase text-[var(--text-faint)]">{pick.confidence_percent}% confidence</p>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </main>
  );
}

// --- F&O IDEAS (directional lean mapped to Call/Put terms - not real options-chain data) ---
function FnoTab({
  token,
  refreshIntervalMs,
  onChangeRefreshIntervalMs,
  onSelectSymbol,
}: {
  token: string;
  refreshIntervalMs: number;
  onChangeRefreshIntervalMs: (ms: number) => void;
  onSelectSymbol: (symbol: string, origin?: PickOrigin) => void;
}) {
  const [optionType, setOptionType] = useState<"CALL" | "PUT">("CALL");
  const [sectors, setSectors] = useState<OptionIdeaSectorGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [meta, setMeta] = useState<FnoIdeasResponse | null>(null);
  const [section, setSection] = useState("overall");
  const { containerRef: sectionTabContainerRef, registerButton: registerSectionTab } = useActiveTabScroll(section);

  const isCall = optionType === "CALL";
  const accentClass = isCall ? "text-emerald-400" : "text-rose-400";
  const hoverBorderClass = isCall ? "hover:border-emerald-500/50" : "hover:border-rose-500/50";

  const isFetchingRef = useRef(false);
  const fetchIdeas = useCallback(async () => {
    if (!token || isFetchingRef.current) return;
    isFetchingRef.current = true;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/fno-ideas?option_type=${optionType}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Could not load F&O ideas.");
      const data = (await res.json()) as FnoIdeasResponse;
      setSectors(data.sectors);
      setMeta(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load F&O ideas.");
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  }, [token, optionType]);

  useEffect(() => {
    setSection("overall");
    fetchIdeas();
  }, [fetchIdeas]);

  const activeIdeas =
    section === "overall" ? meta?.top_overall ?? [] : sectors.find((group) => group.sector === section)?.picks ?? [];
  const visibleSymbols = activeIdeas.map((idea) => idea.symbol);
  const liveQuotes = useLiveQuotes(token, visibleSymbols, refreshIntervalMs);

  const exitGuidance =
    meta?.active_timeframe === "INTRADAY"
      ? "sell/exit before today's 3:30 PM close"
      : "this is a multi-day swing - hold toward the target, but get out if it hits the stop-loss level instead";

  return (
    <main className="mx-auto max-w-3xl space-y-6">
      <div className="rounded-lg border border-[var(--warning-border)] bg-[var(--warning-wash)] p-4 text-xs text-[var(--warning-text-soft)]">{meta?.disclaimer}</div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-6">
        <div className="mb-2 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-2xl font-black text-[var(--text-primary)]">F&amp;O Ideas</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Same scan as Top Picks/Top Falls, mapped to a {isCall ? "Call" : "Put"} lean with a suggested strike,
              target, and stop-loss on the underlying.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <RefreshIntervalPicker valueMs={refreshIntervalMs} onChange={onChangeRefreshIntervalMs} />
            <button
              type="button"
              onClick={() => fetchIdeas()}
              disabled={loading}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-blue-500 disabled:opacity-50"
            >
              {loading ? "Scanning..." : "Refresh"}
            </button>
            <div className="flex rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-1">
              <button
                type="button"
                onClick={() => setOptionType("CALL")}
                className={`rounded-md px-4 py-2 text-sm font-bold transition ${
                  isCall ? "bg-emerald-600 text-white" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                CALL
              </button>
              <button
                type="button"
                onClick={() => setOptionType("PUT")}
                className={`rounded-md px-4 py-2 text-sm font-bold transition ${
                  !isCall ? "bg-rose-600 text-white" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                PUT
              </button>
            </div>
          </div>
        </div>
        {meta?.computed_at && (
          <p className="text-xs text-[var(--text-faint)]">
            Computed {new Date(meta.computed_at).toLocaleString()} - today&apos;s ideas are a stable call for the day,
            not a live feed, so they won&apos;t change again until tomorrow&apos;s scan.
          </p>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-rose-900 bg-rose-950/50 p-4 text-center font-medium text-rose-400">
          {error}
        </div>
      )}

      {loading && sectors.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
          Scanning the market...
        </div>
      )}

      {!loading && !error && sectors.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
          No {isCall ? "Call" : "Put"} ideas from today&apos;s scan.
        </div>
      )}

      {sectors.length > 0 && (
        <>
          <div ref={sectionTabContainerRef} className={`${CHROME_TAB_STRIP_CLASS} sub-tab-strip`} role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={section === "overall"}
              ref={registerSectionTab("overall")}
              onClick={() => setSection("overall")}
              className={chromeTabClass(section === "overall")}
            >
              Top 10 Overall
            </button>
            {sectors.map((group) => (
              <button
                key={group.sector}
                type="button"
                role="tab"
                aria-selected={section === group.sector}
                ref={registerSectionTab(group.sector)}
                onClick={() => setSection(group.sector)}
                className={chromeTabClass(section === group.sector)}
              >
                {group.sector} <span className="text-xs opacity-70">({group.picks.length})</span>
              </button>
            ))}
          </div>

          <div className="grid gap-3">
            {activeIdeas.map((idea, index) => (
              <button
                key={idea.symbol}
                type="button"
                onClick={() =>
                  onSelectSymbol(idea.symbol, {
                    direction: idea.option_type === "CALL" ? "RISE" : "FALL",
                    confidence_percent: idea.confidence_percent,
                    computed_at: meta?.computed_at ?? null,
                  })
                }
                className={`rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-4 text-left transition ${hoverBorderClass}`}
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <span className="w-6 text-lg font-black text-[var(--text-faint)]">{index + 1}</span>
                    <div>
                      <p className="text-lg font-black text-blue-300">
                        {idea.symbol} <span className={`text-sm font-bold ${accentClass}`}>{idea.option_type}</span>
                      </p>
                      <p className="text-sm text-[var(--text-muted)]">Current price: Rs. {liveQuotes[idea.symbol]?.current_price ?? idea.current_price}</p>
                      <p className="text-xs text-[var(--text-faint)]">{formatTradedValue(idea.traded_value)} traded</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`text-xl font-black ${accentClass}`}>{idea.confidence_percent}%</p>
                    <p className="text-xs font-bold uppercase text-[var(--text-faint)]">confidence</p>
                  </div>
                </div>
                <p className="mt-3 rounded bg-[var(--surface-0)] p-3 text-sm text-[var(--text-secondary)]">
                  Buy a <span className="font-bold text-[var(--text-primary)]">{idea.suggested_strike} {idea.option_type}</span>.
                  Book profit if the stock reaches{" "}
                  <span className="font-bold text-emerald-400">Rs. {idea.target_underlying_price}</span>. Get out if
                  it {isCall ? "drops to" : "rises to"}{" "}
                  <span className="font-bold text-rose-400">Rs. {idea.stop_loss_underlying_price}</span> instead -{" "}
                  {exitGuidance}.
                </p>
                <p className="mt-2 text-xs text-[var(--text-faint)]">
                  Short-seller activity: not available - there is no free data source for NSE F&amp;O short
                  positioning, so this cannot be shown honestly.
                </p>
              </button>
            ))}
          </div>
        </>
      )}
    </main>
  );
}

export default function App() {
  const { theme, toggleTheme } = useTheme();
  // Always starts null (matches what the server renders) - a saved token is
  // hydrated in an effect below, client-side only, to avoid a hydration
  // mismatch between the server's logged-out render and localStorage's value.
  const [token, setToken] = useState<string | null>(null);
  // Starts false on both server and client, so the very first client render
  // still matches the server's (avoiding a hydration mismatch) - flips true
  // once the token-hydration effect below has actually checked localStorage.
  // Rendering nothing until then (see the early return further down) is what
  // stops a real login from refresh briefly flashing the login form before
  // the saved session kicks back in.
  const [hasCheckedSession, setHasCheckedSession] = useState(false);
  // Shown once right after a fresh username/password login (never after a
  // refresh that merely restores an already-accepted session) - see
  // handleLogin below, which is the only place this gets set to true.
  const [showTerms, setShowTerms] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // Reads localStorage directly in the initializer (same proven-safe pattern
  // as refreshIntervalMs below) rather than a separate hydration effect - the
  // login form is what actually renders server-side regardless of activeTab
  // (token is always null on the server), so there's no hydration-mismatch
  // risk here to guard against, unlike token itself.
  const [activeTab, setActiveTab] = useState<AppTab>(() => getSavedActiveTab() ?? "scanner");

  const [symbol, setSymbol] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [stockData, setStockData] = useState<StockData | null>(null);
  const [error, setError] = useState("");

  const [watchSymbol, setWatchSymbol] = useState("");
  const [watchThreshold, setWatchThreshold] = useState("");
  const [watchDirection, setWatchDirection] = useState<WatchDirection>("above");
  const [alertItems, setAlertItems] = useState<AlertItem[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [alertsChecking, setAlertsChecking] = useState(false);
  const [alertsMessage, setAlertsMessage] = useState("");
  const [notificationPermission, setNotificationPermission] =
    useState<NotificationPermission>(getInitialNotificationPermission);
  const [alertEvents, setAlertEvents] = useState<AlertEvent[]>([]);
  const [detailSymbol, setDetailSymbolState] = useState<string | null>(null);
  const [detailOrigin, setDetailOrigin] = useState<PickOrigin | null>(null);
  // Watchlist/Alerts/Scanner opens carry no origin snapshot (there's no "this
  // morning's scan" for those) - only Top Picks/Falls/F&O pass one in.
  const setDetailSymbol = (symbol: string | null, origin?: PickOrigin) => {
    setDetailSymbolState(symbol);
    setDetailOrigin(symbol ? origin ?? null : null);
  };

  // Plain Watchlist (no thresholds) - separate state from the Alerts above.
  const [trackedStocks, setTrackedStocks] = useState<TrackedStock[]>([]);
  const [trackedStocksLoading, setTrackedStocksLoading] = useState(false);
  const [trackedStocksMessage, setTrackedStocksMessage] = useState("");
  const [newTrackedSymbol, setNewTrackedSymbol] = useState("");

  // Named groups (up to 10 each), shared component/backend, one array per page.
  const [watchlistGroups, setWatchlistGroups] = useState<StockGroup[]>([]);
  const [alertGroups, setAlertGroups] = useState<StockGroup[]>([]);
  const [activeWatchlistGroupId, setActiveWatchlistGroupId] = useState<number | null>(() => {
    const saved = getSavedSubtab(WATCHLIST_SUBTAB_STORAGE_KEY);
    return saved && saved !== "all" ? Number(saved) : null;
  });
  const [activeAlertGroupId, setActiveAlertGroupId] = useState<number | null>(() => {
    const saved = getSavedSubtab(ALERTS_SUBTAB_STORAGE_KEY);
    return saved && saved !== "all" ? Number(saved) : null;
  });

  // IPO tab
  const [ipoStatus, setIpoStatus] = useState<IpoStatus>("open");
  const [ipoItems, setIpoItems] = useState<IpoItem[]>([]);
  const [ipoLoading, setIpoLoading] = useState(false);
  const [ipoConfigured, setIpoConfigured] = useState(true);
  const [ipoError, setIpoError] = useState("");
  const [refreshIntervalMs, setRefreshIntervalMs] = useState<number>(() =>
    getSavedInterval(LIVE_REFRESH_STORAGE_KEY, DEFAULT_LIVE_REFRESH_MS),
  );

  // Skips its first run entirely, so a fresh mount never wipes out a saved
  // token before the hydration effect below has had a chance to read it.
  const isFirstTokenPersist = useRef(true);
  useEffect(() => {
    if (isFirstTokenPersist.current) {
      isFirstTokenPersist.current = false;
      return;
    }
    if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }, [token]);

  useEffect(() => {
    const saved = getSavedToken();
    if (saved) setToken(saved);
    setHasCheckedSession(true);
  }, []);

  // Plain "always persist on change" effects - safe now that the initial
  // value above is already read from storage, so there's no stale-default
  // ever in play for these to clobber.
  useEffect(() => {
    window.localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
  }, [activeTab]);

  useEffect(() => {
    window.localStorage.setItem(WATCHLIST_SUBTAB_STORAGE_KEY, activeWatchlistGroupId == null ? "all" : String(activeWatchlistGroupId));
  }, [activeWatchlistGroupId]);

  useEffect(() => {
    window.localStorage.setItem(ALERTS_SUBTAB_STORAGE_KEY, activeAlertGroupId == null ? "all" : String(activeAlertGroupId));
  }, [activeAlertGroupId]);

  useEffect(() => {
    window.localStorage.setItem(LIVE_REFRESH_STORAGE_KEY, String(refreshIntervalMs));
  }, [refreshIntervalMs]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setAlertsLoading(true);
    fetch(`${API_URL}/api/alerts`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!res.ok) throw new Error();
        return (await res.json()) as BackendAlertItem[];
      })
      .then((items) => {
        if (!cancelled) setAlertItems(items.map(mapBackendAlertItem));
      })
      .catch(() => {
        if (!cancelled) setAlertsMessage("Could not load your saved alerts.");
      })
      .finally(() => {
        if (!cancelled) setAlertsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setTrackedStocksLoading(true);
    fetch(`${API_URL}/api/tracked-stocks`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!res.ok) throw new Error();
        return (await res.json()) as BackendTrackedStock[];
      })
      .then((items) => {
        if (!cancelled) setTrackedStocks(items.map(mapBackendTrackedStock));
      })
      .catch(() => {
        if (!cancelled) setTrackedStocksMessage("Could not load your saved watchlist.");
      })
      .finally(() => {
        if (!cancelled) setTrackedStocksLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const fetchGroups = useCallback(async (groupType: GroupType): Promise<StockGroup[]> => {
    if (!token) return [];
    const res = await fetch(`${API_URL}/api/groups?group_type=${groupType}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return [];
    return (await res.json()) as StockGroup[];
  }, [token]);

  useEffect(() => {
    if (!token) return;
    fetchGroups("watchlist").then(setWatchlistGroups);
    fetchGroups("alert").then(setAlertGroups);
  }, [token, fetchGroups]);

  const makeGroupHandlers = (groupType: GroupType, groups: StockGroup[], setGroups: (g: StockGroup[]) => void, activeGroupId: number | null, setActiveGroupId: (id: number | null) => void) => ({
    onSelect: setActiveGroupId,
    onCreate: async (name: string) => {
      if (!token) return;
      const res = await fetch(`${API_URL}/api/groups`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ group_type: groupType, name }),
      });
      if (res.ok) {
        const created = (await res.json()) as StockGroup;
        setGroups([...groups, created]);
      }
    },
    onRename: async (groupId: number, name: string) => {
      if (!token) return;
      const res = await fetch(`${API_URL}/api/groups/${groupId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name }),
      });
      if (res.ok) {
        const updated = (await res.json()) as StockGroup;
        setGroups(groups.map((g) => (g.id === groupId ? updated : g)));
      }
    },
    onDelete: async (groupId: number) => {
      if (!token) return;
      const res = await fetch(`${API_URL}/api/groups/${groupId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setGroups(groups.filter((g) => g.id !== groupId));
        if (activeGroupId === groupId) setActiveGroupId(null);
        if (groupType === "watchlist") {
          setTrackedStocks((items) => items.map((item) => (item.groupId === groupId ? { ...item, groupId: null } : item)));
        } else {
          setAlertItems((items) => items.map((item) => (item.groupId === groupId ? { ...item, groupId: null } : item)));
        }
      }
    },
  });

  const watchlistGroupHandlers = makeGroupHandlers("watchlist", watchlistGroups, setWatchlistGroups, activeWatchlistGroupId, setActiveWatchlistGroupId);
  const alertGroupHandlers = makeGroupHandlers("alert", alertGroups, setAlertGroups, activeAlertGroupId, setActiveAlertGroupId);

  const visibleTrackedStocks = useMemo(
    () => trackedStocks.filter((item) => activeWatchlistGroupId == null || item.groupId === activeWatchlistGroupId),
    [trackedStocks, activeWatchlistGroupId],
  );
  const visibleAlertItems = useMemo(
    () => alertItems.filter((item) => activeAlertGroupId == null || item.groupId === activeAlertGroupId),
    [alertItems, activeAlertGroupId],
  );

  const triggeredCount = useMemo(
    () => alertItems.filter((item) => item.status === "triggered").length,
    [alertItems],
  );

  const requestStock = useCallback(async (query: string) => {
    if (!token) throw new Error("You need to log in again.");

    const res = await fetch(`${API_URL}/api/stock/${query}`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) {
      throw new Error("Stock not found on NSE. Check spelling.");
    }

    return (await res.json()) as StockData;
  }, [token]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    const res = await fetch(`${API_URL}/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData,
    });

    if (res.ok) {
      const data = await res.json();
      setToken(data.access_token);
      setShowTerms(true);
      setError("");
    } else {
      setError("Login failed. Check credentials.");
    }
  };

  const fetchStock = async (query: string) => {
    if (!token || !query) return;
    setIsLoading(true);
    setError("");
    setStockData(null);

    try {
      const data = await requestStock(query);
      setStockData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Server error. Ensure backend is running.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchStock(symbol);
  };

  const stockDataRef = useRef(stockData);
  useEffect(() => {
    stockDataRef.current = stockData;
  }, [stockData]);

  const isRefreshingStockRef = useRef(false);
  const refreshCurrentStockQuietly = useCallback(async () => {
    if (!token || !stockDataRef.current || isRefreshingStockRef.current) return;
    isRefreshingStockRef.current = true;
    try {
      const data = await requestStock(stockDataRef.current.symbol);
      setStockData(data);
    } catch {
      // Ignore transient errors on a background refresh - the visible data just stays as-is.
    } finally {
      isRefreshingStockRef.current = false;
    }
  }, [token, requestStock]);

  useEffect(() => {
    if (!token || activeTab !== "scanner") return;
    const intervalId = window.setInterval(refreshCurrentStockQuietly, refreshIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [activeTab, token, refreshIntervalMs, refreshCurrentStockQuietly]);

  const sendAlert = useCallback(async (data: StockData) => {
    if (!token) return;

    await fetch(`${API_URL}/api/telegram/alert`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });
  }, [token]);

  const sendManualAlert = async () => {
    if (!stockData) return;
    await sendAlert(stockData);
    alert("Pro alert sent to Telegram.");
  };

  const requestNotificationPermission = async () => {
    if (!("Notification" in window)) {
      setAlertsMessage("This browser does not support desktop notifications.");
      return;
    }

    const permission = await Notification.requestPermission();
    setNotificationPermission(permission);
    setAlertsMessage(
      permission === "granted"
        ? "Browser notifications are enabled."
        : "Browser notifications were not enabled.",
    );
  };

  const createLocalNotification = (title: string, body: string) => {
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(title, { body });
    }
  };

  const addAlertItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;

    const cleanSymbol = watchSymbol.trim().toUpperCase().replace(".NS", "");
    const threshold = Number(watchThreshold);

    if (!cleanSymbol || !Number.isFinite(threshold) || threshold <= 0) {
      setAlertsMessage("Add a symbol and a positive threshold price.");
      return;
    }

    const duplicate = alertItems.some(
      (item) =>
        item.symbol === cleanSymbol &&
        item.direction === watchDirection &&
        item.threshold === threshold,
    );

    if (duplicate) {
      setAlertsMessage("That watch rule already exists.");
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          symbol: cleanSymbol,
          upper_threshold: watchDirection === "above" ? threshold : null,
          lower_threshold: watchDirection === "below" ? threshold : null,
          group_id: activeAlertGroupId,
        }),
      });
      if (!res.ok) throw new Error("Could not save this alert.");
      const created = (await res.json()) as BackendAlertItem;
      setAlertItems((items) => [mapBackendAlertItem(created), ...items]);
      setWatchSymbol("");
      setWatchThreshold("");
      setAlertsMessage(`${cleanSymbol} added to your alerts.`);
    } catch (err) {
      setAlertsMessage(err instanceof Error ? err.message : "Could not save this alert.");
    }
  };

  const removeAlertItem = (id: string) => {
    setAlertItems((items) => items.filter((item) => item.id !== id));
    if (!token) return;
    fetch(`${API_URL}/api/alerts/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {
      // Best-effort - it's already gone from view; a stale DB row isn't worth blocking the UI on.
    });
  };

  const checkAlerts = useCallback(async () => {
    if (!token || alertItems.length === 0 || alertsChecking) return;

    setAlertsChecking(true);
    setAlertItems((items) =>
      items.map((item) => ({
        ...item,
        status: item.status === "error" ? "checking" : item.status,
      })),
    );

    const updatedItems = await Promise.all(
      alertItems.map(async (item) => {
        try {
          const data = await requestStock(item.symbol);
          const crossed =
            item.direction === "above"
              ? data.current_price >= item.threshold
              : data.current_price <= item.threshold;

          const activeKey = data.prediction.active.toLowerCase() as "intraday" | "delivery";
          const currentPred = data.prediction[activeKey];

          const message = `${data.symbol} is Rs. ${data.current_price}, ${
            crossed ? "past" : "not past"
          } your ${item.direction} Rs. ${item.threshold} alert. Algo sees ${currentPred.direction.toLowerCase()} bias toward Rs. ${currentPred.target_price}.`;

          if (crossed && !item.alerted) {
            createLocalNotification("Stock threshold crossed", message);
            await sendAlert(data);
            setAlertEvents((events) => [
              {
                id: `${item.id}-${Date.now()}`,
                message,
                createdAt: new Date().toLocaleTimeString(),
              },
              ...events.slice(0, 5),
            ]);
          }

          return {
            ...item,
            lastPrice: data.current_price,
            lastChecked: new Date().toLocaleTimeString(),
            status: crossed ? "triggered" : "safe",
            message,
            prediction: data.prediction,
            alerted: crossed,
          } satisfies AlertItem;
        } catch (err) {
          return {
            ...item,
            status: "error",
            lastChecked: new Date().toLocaleTimeString(),
            message: err instanceof Error ? err.message : "Unable to check this symbol.",
          } satisfies AlertItem;
        }
      }),
    );

    // Merge by id into the *current* state, rather than replacing it outright - if an item
    // was added or removed while this check was in flight (a real risk once refresh intervals
    // can be a few seconds), a blind replace would silently discard that edit.
    setAlertItems((current) =>
      current.map((item) => updatedItems.find((updated) => updated.id === item.id) ?? item),
    );
    setAlertsChecking(false);
  }, [token, alertItems, alertsChecking, requestStock, sendAlert]);

  useEffect(() => {
    if (!token || activeTab !== "alerts" || alertItems.length === 0) return;
    const intervalId = window.setInterval(checkAlerts, refreshIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [activeTab, token, alertItems.length, checkAlerts, refreshIntervalMs]);

  // --- Plain Watchlist: just track a symbol, no threshold/alert logic ---
  const addTrackedStock = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;

    const cleanSymbol = newTrackedSymbol.trim().toUpperCase().replace(".NS", "");
    if (!cleanSymbol) {
      setTrackedStocksMessage("Enter a symbol to track.");
      return;
    }
    if (trackedStocks.some((item) => item.symbol === cleanSymbol)) {
      setTrackedStocksMessage("That symbol is already on your watchlist.");
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/tracked-stocks`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ symbol: cleanSymbol, group_id: activeWatchlistGroupId }),
      });
      if (!res.ok) throw new Error("Could not save this to your watchlist.");
      const created = (await res.json()) as BackendTrackedStock;
      setTrackedStocks((items) => [mapBackendTrackedStock(created), ...items]);
      setNewTrackedSymbol("");
      setTrackedStocksMessage(`${cleanSymbol} added to your watchlist.`);
    } catch (err) {
      setTrackedStocksMessage(err instanceof Error ? err.message : "Could not save this to your watchlist.");
    }
  };

  const removeTrackedStock = (id: string) => {
    setTrackedStocks((items) => items.filter((item) => item.id !== id));
    if (!token) return;
    fetch(`${API_URL}/api/tracked-stocks/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {
      // Best-effort - it's already gone from view; a stale DB row isn't worth blocking the UI on.
    });
  };

  const [trackedStocksChecking, setTrackedStocksChecking] = useState(false);
  const checkTrackedStocks = useCallback(async () => {
    if (!token || trackedStocks.length === 0 || trackedStocksChecking) return;

    setTrackedStocksChecking(true);
    setTrackedStocks((items) => items.map((item) => ({ ...item, status: item.status === "error" ? "checking" : item.status })));

    const updated = await Promise.all(
      trackedStocks.map(async (item) => {
        try {
          const data = await requestStock(item.symbol);
          return {
            ...item,
            lastPrice: data.current_price,
            lastChecked: new Date().toLocaleTimeString(),
            status: "idle",
            prediction: data.prediction,
          } satisfies TrackedStock;
        } catch {
          return { ...item, status: "error", lastChecked: new Date().toLocaleTimeString() } satisfies TrackedStock;
        }
      }),
    );

    setTrackedStocks((current) => current.map((item) => updated.find((u) => u.id === item.id) ?? item));
    setTrackedStocksChecking(false);
  }, [token, trackedStocks, trackedStocksChecking, requestStock]);

  useEffect(() => {
    if (!token || activeTab !== "watchlist" || trackedStocks.length === 0) return;
    const intervalId = window.setInterval(checkTrackedStocks, refreshIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [activeTab, token, trackedStocks.length, checkTrackedStocks, refreshIntervalMs]);

  // --- IPO tab ---
  useEffect(() => {
    if (!token || activeTab !== "ipo") return;
    let cancelled = false;
    setIpoLoading(true);
    setIpoError("");
    fetch(`${API_URL}/api/ipos?status=${ipoStatus}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!res.ok) throw new Error("Could not load IPO data.");
        return (await res.json()) as IpoResponse;
      })
      .then((data) => {
        if (cancelled) return;
        setIpoConfigured(data.configured);
        setIpoItems(data.items);
        if (data.error) setIpoError(data.error);
      })
      .catch((err) => {
        if (!cancelled) setIpoError(err instanceof Error ? err.message : "Could not load IPO data.");
      })
      .finally(() => {
        if (!cancelled) setIpoLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, activeTab, ipoStatus]);

  const getRangePercentage = () => {
    if (!stockData || stockData.high === stockData.low) return 50;
    const range = stockData.high - stockData.low;
    const position = ((stockData.current_price - stockData.low) / range) * 100;
    return Math.max(0, Math.min(100, position));
  };

  // Render nothing while the saved-session check is still in flight - see
  // hasCheckedSession's declaration above for why this specifically fixes
  // the "login page flashes on refresh" complaint.
  if (!hasCheckedSession) {
    return <div className="min-h-screen bg-[var(--surface-0)]" />;
  }

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface-0)] p-4 text-[var(--text-primary)]">
        <form
          onSubmit={handleLogin}
          className="w-full max-w-sm space-y-6 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-8 shadow-2xl"
        >
          <div className="flex justify-end">
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
          <div className="text-center">
            <h2 className="text-3xl font-extrabold text-[var(--text-primary)]">Pro Terminal</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">Authenticate to access algorithm</p>
          </div>
          {error && (
            <p className="rounded bg-red-900/20 p-2 text-center text-sm text-red-400">{error}</p>
          )}
          <input
            type="text"
            placeholder="Username"
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-3 outline-none transition focus:ring-2 focus:ring-blue-500"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            type="password"
            placeholder="Password"
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-3 outline-none transition focus:ring-2 focus:ring-blue-500"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            type="submit"
            className="w-full rounded-lg bg-blue-600 p-3 font-bold text-white shadow-lg shadow-blue-900/50 transition hover:bg-blue-500"
          >
            SECURE LOGIN
          </button>
          <p className="text-center text-sm text-[var(--text-muted)]">
            New here?{" "}
            <Link href="/signup" className="font-semibold text-blue-400 transition hover:text-blue-300">
              Create an account
            </Link>
          </p>
        </form>
      </div>
    );
  }

  if (showTerms) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface-0)] p-4 text-[var(--text-primary)]">
        <div className="w-full max-w-lg space-y-4 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-6 shadow-2xl sm:p-8">
          <div>
            <h2 className="text-2xl font-extrabold text-[var(--text-primary)]">Before You Continue</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">Please read this every time you log in - it matters.</p>
          </div>
          <div className="max-h-72 space-y-3 overflow-y-auto rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-4 text-sm text-[var(--text-secondary)]">
            <p>
              <strong className="text-[var(--text-primary)]">This app is a prediction algorithm, not a source of truth.</strong>{" "}
              Every figure you see here - Top Picks, Top Falls, F&amp;O ideas, the &quot;confidence&quot; and
              &quot;probability&quot; numbers on a stock&apos;s detail page, the news-sentiment score - is generated
              by an internal heuristic based on historical price patterns, moving averages, momentum, and news
              sentiment. None of it is financial advice.
            </p>
            <p>
              These numbers are <strong className="text-[var(--text-primary)]">not statistically validated
              forecasts</strong>. We have actually backtested this algorithm against real historical data, and it
              does not reliably beat even the simplest baseline (&quot;the market generally goes up&quot;). Treat
              every prediction and confidence score in this app as illustrative, not guaranteed.
            </p>
            <p>
              F&amp;O ideas are our own directional algorithm mapped onto option terms - not a real NSE options
              chain, and not based on live premium, open interest, or positioning data.
            </p>
            <p>
              Markets are volatile and unpredictable. Past patterns do not guarantee future results. This
              algorithm can be, and regularly is, wrong - it does not always happen the way it predicts.
            </p>
            <p>
              You are solely responsible for any trading or investment decisions you make. This app, its
              developers, and its operators accept no liability for any financial loss arising from its use.
            </p>
            <p>
              By clicking &quot;I Understand &amp; Accept&quot; below, you confirm you have read and understood
              this, and that you will not treat any prediction, score, or percentage shown in this app as a
              guaranteed outcome.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowTerms(false)}
            className="w-full rounded-lg bg-blue-600 p-3 font-bold text-white shadow-lg shadow-blue-900/50 transition hover:bg-blue-500"
          >
            I Understand &amp; Accept
          </button>
        </div>
      </div>
    );
  }

  const isBuy = stockData?.suggestion.includes("BUY") && !stockData?.suggestion.includes("DON'T");
  const isSell = stockData?.suggestion.includes("DON'T") || stockData?.suggestion.includes("SHORT");
  const cardBorderClass = isBuy
    ? "border-emerald-500/50 shadow-emerald-900/20"
    : isSell
      ? "border-rose-500/50 shadow-rose-900/20"
      : "border-[var(--border-strong)] shadow-black/50";
  const suggestionTextClass = isBuy ? "text-emerald-400" : isSell ? "text-rose-400" : "text-[var(--warning-text)]";

  return (
    <div className="min-h-screen bg-[var(--surface-0)] p-4 font-sans text-[var(--text-primary)] md:p-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-4 p-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 rounded-full bg-emerald-500"></div>
              <h1 className="text-xl font-black tracking-tight text-[var(--text-primary)] md:text-2xl">
                ALGOTRADE<span className="text-blue-500">PRO</span>
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <ThemeToggle theme={theme} onToggle={toggleTheme} />
              <button onClick={() => setToken(null)} className="text-sm text-[var(--text-muted)] transition hover:text-[var(--text-primary)]">
                Disconnect
              </button>
            </div>
          </div>
          <MainTabStrip activeTab={activeTab} onSelect={setActiveTab} triggeredCount={triggeredCount} />
        </div>

        {activeTab === "scanner" && (
          <main className="mx-auto max-w-3xl space-y-6">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-6">
              <form onSubmit={handleSearchSubmit} className="flex flex-col gap-3 sm:flex-row">
                <SymbolAutocomplete
                  value={symbol}
                  onChange={setSymbol}
                  onSelect={(selected) => fetchStock(selected)}
                  token={token}
                  placeholder="ENTER NSE SYMBOL..."
                  className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-4 uppercase tracking-wider text-[var(--text-primary)] outline-none focus:border-blue-500"
                />
                <button
                  type="submit"
                  disabled={isLoading}
                  className="rounded-lg bg-blue-600 px-8 py-4 font-bold text-white shadow-lg shadow-blue-900/50 transition hover:bg-blue-500 disabled:opacity-50"
                >
                  {isLoading ? "SCANNING..." : "SCAN"}
                </button>
              </form>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="py-1 text-xs font-bold text-[var(--text-faint)]">QUICK SYMBOLS:</span>
                  {QUICK_SYMBOLS.map((item) => (
                    <button
                      key={item}
                      onClick={() => {
                        setSymbol(item);
                        fetchStock(item);
                      }}
                      className="rounded-full border border-[var(--border-strong)] bg-[var(--surface-2)] px-3 py-1 text-xs font-bold text-[var(--text-secondary)] transition hover:bg-[var(--surface-3)]"
                    >
                      {item}
                    </button>
                  ))}
                </div>
                {stockData && <RefreshIntervalPicker valueMs={refreshIntervalMs} onChange={setRefreshIntervalMs} />}
              </div>
            </div>

            {error && (
              <div className="rounded-lg border border-rose-900 bg-rose-950/50 p-4 text-center font-medium text-rose-400">
                {error}
              </div>
            )}

            {stockData && !isLoading && (
              <div className={`rounded-lg border-2 bg-[var(--surface-1)] p-6 shadow-2xl transition-all duration-500 ${cardBorderClass}`}>
                <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="mb-1 flex items-center gap-2 font-semibold text-[var(--text-muted)]">
                      <button
                        type="button"
                        onClick={() => setDetailSymbol(stockData.symbol)}
                        className="text-blue-300 underline decoration-blue-400/60 underline-offset-4 transition hover:text-blue-200"
                      >
                        {stockData.symbol}
                      </button>
                      <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">NSE</span>
                    </p>
                    <div className="flex flex-wrap items-baseline gap-3">
                      <h2 className="text-5xl font-black tracking-tight text-[var(--text-primary)]">Rs. {stockData.current_price}</h2>
                      <p className={`text-xl font-bold ${stockData.percent_change >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                        {stockData.percent_change >= 0 ? "UP +" : "DOWN "}
                        {stockData.percent_change}%
                      </p>
                    </div>
                  </div>

                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] px-4 py-2 text-left sm:text-right">
                    <p className="mb-1 text-xs font-bold tracking-wider text-[var(--text-faint)]">NIFTY 50 TREND</p>
                    <p className={`text-lg font-black ${stockData.nifty.is_positive ? "text-emerald-400" : "text-rose-400"}`}>
                      {stockData.nifty.is_positive ? "UP" : "DOWN"} {stockData.nifty.value}
                    </p>
                  </div>
                </div>

                <div className="mb-8 rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-4">
                  <div className="mb-2 flex justify-between text-xs font-bold text-[var(--text-faint)]">
                    <span>LOW: Rs. {stockData.low}</span>
                    <span>DAY&apos;S RANGE</span>
                    <span>HIGH: Rs. {stockData.high}</span>
                  </div>
                  <div className="relative h-2 overflow-hidden rounded-full bg-[var(--surface-2)]">
                    <div className="absolute left-0 top-0 h-full w-full bg-gradient-to-r from-rose-500 via-amber-500 to-emerald-500 opacity-50"></div>
                    <div
                      className="absolute top-0 h-full w-2 rounded-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.8)] transition-all duration-1000"
                      style={{ left: `${getRangePercentage()}%` }}
                    ></div>
                  </div>
                </div>

                <div className="mb-8 grid grid-cols-1 gap-4 text-sm sm:grid-cols-3">
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-3">
                    <p className="text-xs font-bold text-[var(--text-faint)]">OPEN</p>
                    <p className="font-semibold text-[var(--text-primary)]">Rs. {stockData.open}</p>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-3">
                    <p className="text-xs font-bold text-[var(--text-faint)]">PREV CLOSE</p>
                    <p className="font-semibold text-[var(--text-primary)]">Rs. {stockData.previous_close}</p>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-3">
                    <p className="text-xs font-bold text-[var(--text-faint)]">VOLUME</p>
                    <p className="font-semibold text-[var(--text-primary)]">{(stockData.volume / 100000).toFixed(2)}L</p>
                  </div>
                </div>

                <div className="mb-8 space-y-4">
                  <PredictionPanel data={stockData.prediction} />
                  <ForecastPanel forecast={stockData.prediction.forecast} compact />
                  <p className="text-xs text-[var(--text-faint)]">
                    Rule-based estimates from recent candles, momentum, and news sentiment - not financial advice.
                  </p>
                </div>

                <div className="flex flex-col gap-4 border-t border-[var(--border)] pt-6 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="mb-1 text-xs font-black uppercase tracking-widest text-[var(--text-faint)]">AI Trading Signal</p>
                    <p className={`text-3xl font-black uppercase tracking-tight ${suggestionTextClass}`}>
                      {stockData.suggestion}
                    </p>
                  </div>
                  <button
                    onClick={sendManualAlert}
                    className="rounded-lg bg-[#0088cc] px-6 py-4 font-bold text-white shadow-lg transition hover:bg-[#0077b3]"
                  >
                    Send Telegram Alert
                  </button>
                </div>
              </div>
            )}
          </main>
        )}

        {activeTab === "watchlist" && (
          <main className="space-y-6">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-6">
              <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-2xl font-black text-[var(--text-primary)]">Watchlist</h2>
                  <p className="mt-1 text-sm text-[var(--text-muted)]">
                    Just tracking price and sentiment - no thresholds. Refreshes every{" "}
                    {REFRESH_INTERVAL_OPTIONS.find((o) => o.ms === refreshIntervalMs)?.label ?? "60s"} while this tab is
                    open.
                  </p>
                </div>
                <RefreshIntervalPicker valueMs={refreshIntervalMs} onChange={setRefreshIntervalMs} />
              </div>

              <GroupTabBar
                groups={watchlistGroups}
                activeGroupId={activeWatchlistGroupId}
                {...watchlistGroupHandlers}
              />

              <form onSubmit={addTrackedStock} className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
                <SymbolAutocomplete
                  value={newTrackedSymbol}
                  onChange={setNewTrackedSymbol}
                  token={token}
                  placeholder="NSE SYMBOL"
                  className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-3 uppercase text-[var(--text-primary)] outline-none focus:border-blue-500"
                />
                <button
                  type="submit"
                  className="rounded-lg bg-emerald-600 px-6 py-3 font-bold text-white transition hover:bg-emerald-500"
                >
                  Add
                </button>
              </form>

              {trackedStocksMessage && <p className="mt-4 text-sm text-[var(--text-secondary)]">{trackedStocksMessage}</p>}
            </div>

            <div className="grid gap-3">
              {trackedStocksLoading && visibleTrackedStocks.length === 0 ? (
                <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
                  Loading your saved watchlist...
                </div>
              ) : visibleTrackedStocks.length === 0 ? (
                <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
                  Add a stock to start tracking it here.
                </div>
              ) : (
                visibleTrackedStocks.map((item) => (
                  <div
                    key={item.id}
                    className={`rounded-lg border p-4 ${
                      item.status === "error"
                        ? "border-[var(--warning-border-strong)] bg-[var(--warning-surface)]"
                        : "border-[var(--border)] bg-[var(--surface-1)]"
                    }`}
                  >
                    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                      <div>
                        <button
                          type="button"
                          onClick={() => setDetailSymbol(item.symbol)}
                          className="text-2xl font-black text-blue-300 underline decoration-blue-400/60 underline-offset-4 transition hover:text-blue-200"
                        >
                          {item.symbol}
                        </button>
                        {item.prediction && (
                          <div className="mt-4 max-w-xl">
                            <PredictionPanel data={item.prediction} compact />
                          </div>
                        )}
                      </div>
                      <div className="flex items-center justify-between gap-4 md:justify-end">
                        <div className="text-right">
                          <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Last price</p>
                          <p className="text-xl font-black text-[var(--text-primary)]">
                            {item.lastPrice ? `Rs. ${item.lastPrice}` : "-"}
                          </p>
                          <p className="text-xs text-[var(--text-faint)]">{item.lastChecked ?? "Not checked yet"}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeTrackedStock(item.id)}
                          className="rounded-lg border border-[var(--border-strong)] px-3 py-2 text-sm font-bold text-[var(--text-secondary)] transition hover:border-rose-500 hover:text-rose-300"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </main>
        )}

        {activeTab === "alerts" && (
          <main className="space-y-6">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-6">
              <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-2xl font-black text-[var(--text-primary)]">Threshold Alerts</h2>
                  <p className="mt-1 text-sm text-[var(--text-muted)]">
                    Checks every {REFRESH_INTERVAL_OPTIONS.find((o) => o.ms === refreshIntervalMs)?.label ?? "60s"} while
                    this tab is open.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <RefreshIntervalPicker valueMs={refreshIntervalMs} onChange={setRefreshIntervalMs} />
                  <button
                    type="button"
                    onClick={requestNotificationPermission}
                    className="rounded-lg border border-[var(--border-strong)] px-4 py-2 text-sm font-bold text-[var(--text-primary)] transition hover:bg-[var(--surface-2)]"
                  >
                    {notificationPermission === "granted" ? "Notifications On" : "Enable Notifications"}
                  </button>
                  <button
                    type="button"
                    onClick={checkAlerts}
                    disabled={alertsChecking || alertItems.length === 0}
                    className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-blue-500 disabled:opacity-50"
                  >
                    {alertsChecking ? "Checking..." : "Check Now"}
                  </button>
                </div>
              </div>
              {refreshIntervalMs < 10000 && (
                <p className="mt-2 text-xs text-[var(--warning-text)]">
                  Heads up: refreshing faster than every 10s can hit Yahoo Finance rate limits if you have several
                  symbols watched.
                </p>
              )}

              <GroupTabBar
                groups={alertGroups}
                activeGroupId={activeAlertGroupId}
                {...alertGroupHandlers}
              />

              <form onSubmit={addAlertItem} className="mt-4 grid gap-3 md:grid-cols-[1fr_150px_170px_auto]">
                <SymbolAutocomplete
                  value={watchSymbol}
                  onChange={setWatchSymbol}
                  token={token}
                  placeholder="NSE SYMBOL"
                  className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-3 uppercase text-[var(--text-primary)] outline-none focus:border-blue-500"
                />
                <select
                  value={watchDirection}
                  onChange={(e) => setWatchDirection(e.target.value as WatchDirection)}
                  className="rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-3 text-[var(--text-primary)] outline-none focus:border-blue-500"
                >
                  <option value="above">Goes above</option>
                  <option value="below">Goes below</option>
                </select>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="Threshold"
                  className="rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-3 text-[var(--text-primary)] outline-none focus:border-blue-500"
                  value={watchThreshold}
                  onChange={(e) => setWatchThreshold(e.target.value)}
                />
                <button
                  type="submit"
                  className="rounded-lg bg-emerald-600 px-6 py-3 font-bold text-white transition hover:bg-emerald-500"
                >
                  Add
                </button>
              </form>

              {alertsMessage && <p className="mt-4 text-sm text-[var(--text-secondary)]">{alertsMessage}</p>}
            </div>

            {alertEvents.length > 0 && (
              <div className="rounded-lg border border-rose-900/70 bg-rose-950/30 p-4">
                <h3 className="mb-3 text-sm font-black uppercase tracking-widest text-rose-300">Recent alerts</h3>
                <div className="space-y-2">
                  {alertEvents.map((event) => (
                    <div key={event.id} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-center sm:justify-between">
                      <span className="font-semibold text-[var(--text-primary)]">{event.message}</span>
                      <span className="text-[var(--text-muted)]">{event.createdAt}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="grid gap-3">
              {alertsLoading && visibleAlertItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
                  Loading your saved alerts...
                </div>
              ) : visibleAlertItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
                  Add your first stock threshold to start monitoring.
                </div>
              ) : (
                visibleAlertItems.map((item) => (
                  <div
                    key={item.id}
                    className={`rounded-lg border p-4 ${
                      item.status === "triggered"
                        ? "border-rose-500/70 bg-rose-950/30"
                        : item.status === "error"
                          ? "border-[var(--warning-border-strong)] bg-[var(--warning-surface)]"
                          : "border-[var(--border)] bg-[var(--surface-1)]"
                    }`}
                  >
                    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <button
                            type="button"
                            onClick={() => setDetailSymbol(item.symbol)}
                            className="text-2xl font-black text-blue-300 underline decoration-blue-400/60 underline-offset-4 transition hover:text-blue-200"
                          >
                            {item.symbol}
                          </button>
                          <span className="rounded-full border border-[var(--border-strong)] px-3 py-1 text-xs font-bold uppercase text-[var(--text-secondary)]">
                            {item.direction} Rs. {item.threshold}
                          </span>
                          <span
                            className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${
                              item.status === "triggered"
                                ? "bg-rose-500 text-white"
                                : item.status === "safe"
                                  ? "bg-emerald-500/20 text-emerald-300"
                                  : item.status === "checking"
                                    ? "bg-blue-500/20 text-blue-300"
                                    : item.status === "error"
                                      ? "bg-[var(--warning-wash-strong)] text-[var(--warning-text)]"
                                      : "bg-[var(--surface-2)] text-[var(--text-secondary)]"
                            }`}
                          >
                            {item.status}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-[var(--text-muted)]">
                          {item.message ?? "Waiting for the next check."}
                        </p>
                        {item.prediction && (
                          <div className="mt-4 max-w-xl">
                            <PredictionPanel data={item.prediction} compact />
                          </div>
                        )}
                      </div>
                      <div className="flex items-center justify-between gap-4 md:justify-end">
                        <div className="text-right">
                          <p className="text-xs font-bold uppercase text-[var(--text-faint)]">Last price</p>
                          <p className="text-xl font-black text-[var(--text-primary)]">
                            {item.lastPrice ? `Rs. ${item.lastPrice}` : "-"}
                          </p>
                          <p className="text-xs text-[var(--text-faint)]">{item.lastChecked ?? "Not checked yet"}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeAlertItem(item.id)}
                          className="rounded-lg border border-[var(--border-strong)] px-3 py-2 text-sm font-bold text-[var(--text-secondary)] transition hover:border-rose-500 hover:text-rose-300"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </main>
        )}

        {activeTab === "ipo" && (
          <main className="space-y-6">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-6">
              <div className="mb-5 flex items-center justify-between">
                <h2 className="text-2xl font-black text-[var(--text-primary)]">IPOs</h2>
                <div className="flex rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-1" role="tablist">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={ipoStatus === "open"}
                    onClick={() => setIpoStatus("open")}
                    className={`rounded-md px-4 py-2 text-sm font-bold transition ${
                      ipoStatus === "open" ? "bg-blue-600 text-white" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    Open now
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={ipoStatus === "upcoming"}
                    onClick={() => setIpoStatus("upcoming")}
                    className={`rounded-md px-4 py-2 text-sm font-bold transition ${
                      ipoStatus === "upcoming" ? "bg-blue-600 text-white" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    Upcoming
                  </button>
                </div>
              </div>

              {!ipoConfigured ? (
                <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
                  IPO data isn&apos;t connected yet - the backend needs an IPO Guru API key (free, email
                  ipoguru.in@gmail.com) set as <code>IPO_GURU_API_KEY</code> before this tab shows anything.
                </div>
              ) : ipoLoading ? (
                <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
                  Loading IPOs...
                </div>
              ) : ipoError ? (
                <div className="rounded-lg border border-rose-900 bg-rose-950/50 p-4 text-center font-medium text-rose-400">
                  {ipoError}
                </div>
              ) : ipoItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-10 text-center text-[var(--text-muted)]">
                  No IPOs {ipoStatus === "open" ? "are currently open" : "are currently listed as upcoming"}.
                </div>
              ) : (
                <div className="grid gap-3">
                  {ipoItems.map((ipo) => {
                    const sentimentClass =
                      ipo.sentiment.label === "Positive"
                        ? "text-emerald-400"
                        : ipo.sentiment.label === "Negative"
                          ? "text-rose-400"
                          : ipo.sentiment.label === "Mixed"
                            ? "text-amber-400"
                            : "text-[var(--warning-text)]";
                    const outlookClass =
                      ipo.outlook === "Strong Demand" ? "text-emerald-400" : ipo.outlook === "Weak Demand" ? "text-rose-400" : "text-[var(--warning-text)]";
                    return (
                      <div key={ipo.company_name} className="rounded-lg border border-[var(--border)] bg-[var(--surface-0)] p-4">
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div>
                            <p className="text-lg font-black text-[var(--text-primary)]">{ipo.company_name}</p>
                            <p className="mt-1 text-sm text-[var(--text-muted)]">
                              {ipo.price_band ? `Price band Rs. ${ipo.price_band}` : "Price band TBA"}
                              {ipo.lot_size ? ` - Lot size ${ipo.lot_size}` : ""}
                            </p>
                            <p className="mt-1 text-xs text-[var(--text-faint)]">
                              {ipo.open_date && ipo.close_date ? `Open ${ipo.open_date} to ${ipo.close_date}` : ""}
                              {ipo.listing_date ? ` - Lists ${ipo.listing_date}` : ""}
                            </p>
                          </div>
                          <div className="text-right">
                            <span className="whitespace-nowrap rounded-full bg-blue-500/20 px-2 py-0.5 text-xs font-bold text-blue-300">
                              {ipo.confidence_percent}% confidence
                            </span>
                            <p className={`mt-1 text-sm font-bold ${outlookClass}`}>{ipo.outlook}</p>
                            {ipo.gmp_percent != null && (
                              <p className="text-xs text-[var(--text-faint)]">GMP {ipo.gmp_percent}%</p>
                            )}
                          </div>
                        </div>
                        <div className="mt-3 flex items-center justify-between border-t border-[var(--border)] pt-3">
                          <p className="text-xs font-black uppercase tracking-widest text-[var(--text-faint)]">News Sentiment</p>
                          <span className={`text-sm font-black ${sentimentClass}`}>{ipo.sentiment.label}</span>
                        </div>
                        <p className="mt-1 text-xs text-[var(--text-faint)]">{ipo.sentiment.note}</p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </main>
        )}

        {activeTab === "toppicks" && token && (
          <TopPicksTab
            token={token}
            direction="RISE"
            refreshIntervalMs={refreshIntervalMs}
            onChangeRefreshIntervalMs={setRefreshIntervalMs}
            onSelectSymbol={setDetailSymbol}
          />
        )}

        {activeTab === "topfalls" && token && (
          <TopPicksTab
            token={token}
            direction="FALL"
            refreshIntervalMs={refreshIntervalMs}
            onChangeRefreshIntervalMs={setRefreshIntervalMs}
            onSelectSymbol={setDetailSymbol}
          />
        )}

        {activeTab === "fno" && token && (
          <FnoTab
            token={token}
            refreshIntervalMs={refreshIntervalMs}
            onChangeRefreshIntervalMs={setRefreshIntervalMs}
            onSelectSymbol={setDetailSymbol}
          />
        )}
      </div>

      {detailSymbol && token && (
        <StockDetailModal
          symbol={detailSymbol}
          token={token}
          origin={detailOrigin}
          refreshIntervalMs={refreshIntervalMs}
          onClose={() => setDetailSymbol(null)}
        />
      )}
    </div>
  );
}