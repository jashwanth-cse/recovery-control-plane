"use client";

import { useEffect, useState } from "react";

type ApiHealth = {
  service: string;
  environment: string;
  status: string;
  version: string;
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${apiBaseUrl}/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        return response.json() as Promise<ApiHealth>;
      })
      .then((payload) => {
        setHealth(payload);
        setError(null);
      })
      .catch((requestError: Error) => {
        if (requestError.name !== "AbortError") {
          setError(requestError.message);
        }
      });

    return () => controller.abort();
  }, []);

  const apiStatus = health?.status === "ok" ? "Connected" : "Checking";

  return (
    <main className="shell">
      <section className="intro" aria-labelledby="page-title">
        <div className="status-strip">
          <span className="status-dot" aria-hidden="true" />
          Phase 0 foundation
        </div>
        <h1 id="page-title">Revenue Recovery Control Plane</h1>
        <p>
          A controlled foundation for revenue-at-risk detection, policy-gated
          recovery execution, and incremental measurement on Razorpay payment
          rails.
        </p>
      </section>

      <section className="runtime-grid" aria-label="Runtime status">
        <article className="panel">
          <span className="label">API</span>
          <strong>{error ? "Unavailable" : apiStatus}</strong>
          <p>{error ?? health?.version ?? "Waiting for backend health."}</p>
        </article>
        <article className="panel">
          <span className="label">Database</span>
          <strong>PostgreSQL</strong>
          <p>Alembic owns schema evolution from the first migration onward.</p>
        </article>
        <article className="panel">
          <span className="label">Queue</span>
          <strong>Redis</strong>
          <p>Configured for later recovery jobs and webhook processing.</p>
        </article>
      </section>

      <section className="flow" aria-label="Safety boundary">
        <div>AI recommendation</div>
        <div>Policy gate</div>
        <div>Razorpay adapter</div>
        <div>Audited execution</div>
      </section>
    </main>
  );
}
