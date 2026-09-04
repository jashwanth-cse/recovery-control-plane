"use client";

import { useCallback, useEffect, useState } from "react";

type CurrencySummary = {
  currency: string;
  revenue_at_risk: number;
  expected_recoverable: number;
  active_cases: number;
  estimated_cases: number;
};

type Opportunity = {
  case_id: string;
  source_type: "PAYMENT" | "ORDER" | "PAYMENT_LINK";
  source_id: string;
  status: string;
  amount_at_risk: number;
  currency: string;
  recovery_probability: string | null;
  expected_recoverable: number | null;
  priority_score: number;
  recovery_window_end: string;
};

type DashboardSummary = {
  generated_at: string;
  currencies: CurrencySummary[];
  top_opportunities: Opportunity[];
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function formatMoney(amount: number, currency: string) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount / 100);
}

function formatSource(source: Opportunity["source_type"]) {
  return source
    .toLowerCase()
    .split("_")
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function formatProbability(value: string | null) {
  if (value === null) return "Pending";
  return `${Math.round(Number(value) * 100)}%`;
}

export default function Home() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadDashboard = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/dashboard/summary`, {
        signal,
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`Dashboard API returned ${response.status}`);
      setSummary((await response.json()) as DashboardSummary);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof Error && requestError.name !== "AbortError") {
        setError(requestError.message);
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadDashboard(controller.signal);
    const refreshTimer = window.setInterval(() => {
      void loadDashboard();
    }, 3000);
    return () => {
      controller.abort();
      window.clearInterval(refreshTimer);
    };
  }, [loadDashboard]);

  return (
    <main className="app-shell">
      <header className="product-bar">
        <div>
          <span className="product-mark" aria-hidden="true">RC</span>
          <span className="product-name">Revenue Recovery</span>
        </div>
        <button
          className={error ? "connection connection-error" : "connection"}
          type="button"
          onClick={() => void loadDashboard()}
          title="Refresh dashboard"
        >
          <span aria-hidden="true" />
          {error ? "Disconnected" : loading ? "Refreshing" : "Live data"}
        </button>
      </header>

      <section className="page-heading">
        <div>
          <p className="eyebrow">Control plane</p>
          <h1>Revenue overview</h1>
        </div>
        {summary && (
          <p className="updated-at">
            Updated {new Intl.DateTimeFormat("en-IN", {
              hour: "2-digit",
              minute: "2-digit",
            }).format(new Date(summary.generated_at))}
          </p>
        )}
      </section>

      {loading && !summary ? (
        <section className="loading-grid" aria-label="Loading dashboard">
          <div /><div /><div />
        </section>
      ) : error && !summary ? (
        <section className="error-state" role="alert">
          <strong>Dashboard data is unavailable</strong>
          <p>{error}</p>
          <button type="button" onClick={() => void loadDashboard()}>Retry</button>
        </section>
      ) : summary?.currencies.length === 0 ? (
        <section className="empty-state">
          <strong>No active recovery cases</strong>
          <p>New eligible payment signals will appear here automatically.</p>
        </section>
      ) : (
        <>
          <section className="currency-sections" aria-label="Revenue metrics">
            {summary?.currencies.map((item) => (
              <div className="currency-band" key={item.currency}>
                <div className="currency-title">
                  <span>{item.currency}</span>
                  <small>{item.estimated_cases} of {item.active_cases} estimated</small>
                </div>
                <div className="metric-grid">
                  <article className="metric">
                    <span>Revenue at risk</span>
                    <strong>{formatMoney(item.revenue_at_risk, item.currency)}</strong>
                  </article>
                  <article className="metric metric-positive">
                    <span>Expected recoverable</span>
                    <strong>{formatMoney(item.expected_recoverable, item.currency)}</strong>
                  </article>
                  <article className="metric">
                    <span>Active cases</span>
                    <strong>{item.active_cases.toLocaleString("en-IN")}</strong>
                  </article>
                </div>
              </div>
            ))}
          </section>

          <section className="opportunities" aria-labelledby="opportunity-title">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Recovery queue</p>
                <h2 id="opportunity-title">Top opportunities</h2>
              </div>
              <span>{summary?.top_opportunities.length ?? 0} shown</span>
            </div>

            <div className="table-wrap">
              <table>
                <thead><tr><th>Priority</th><th>Case</th><th>Amount</th><th>Recovery</th><th>Expected</th><th>Window ends</th><th>Status</th></tr></thead>
                <tbody>
                  {summary?.top_opportunities.map((item, index) => (
                    <tr key={item.case_id}>
                      <td><span className="rank">{index + 1}</span></td>
                      <td><strong className="case-source">{formatSource(item.source_type)}</strong><span className="case-id">{item.source_id}</span></td>
                      <td className="money">{formatMoney(item.amount_at_risk, item.currency)}</td>
                      <td>{formatProbability(item.recovery_probability)}</td>
                      <td className="money">{item.expected_recoverable === null ? "Pending" : formatMoney(item.expected_recoverable, item.currency)}</td>
                      <td>{new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" }).format(new Date(item.recovery_window_end))}</td>
                      <td><span className="status-label">{item.status.replaceAll("_", " ")}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
