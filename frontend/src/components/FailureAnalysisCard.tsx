import { useMemo, useState } from "react";
import type { AnalyzeResult } from "../lib/api/types";
import {
  analysisTitle,
  categoryIcon,
  categoryLabel,
  confidenceLevel,
  copyToClipboard,
  formatConfidence,
  generateBugReport,
  inferCategory,
  providerDisplayName,
  type FailureCategory,
} from "../lib/analysisUi";

type FailedItem = AnalyzeResult["failed_analyses"][number];

type Props = {
  item: FailedItem;
  runName: string;
  pulpitoUrl: string;
  provider?: string;
  providerLabel?: string;
};

function ConfidenceBar({ value }: { value: number }) {
  const level = confidenceLevel(value);
  return (
    <div className="analysis-confidence">
      <div className="analysis-confidence-track">
        <div
          className={`analysis-confidence-fill ${level}`}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
      <span className={`analysis-confidence-pct ${level}`}>
        {formatConfidence(value)}
      </span>
    </div>
  );
}

export default function FailureAnalysisCard({
  item,
  runName,
  pulpitoUrl,
  provider,
  providerLabel,
}: Props) {
  const [tab, setTab] = useState<"analysis" | "logs">("analysis");
  const [showEvidence, setShowEvidence] = useState(false);
  const [feedback, setFeedback] = useState<boolean | null>(null);
  const [copied, setCopied] = useState(false);

  const category: FailureCategory = useMemo(
    () =>
      inferCategory(
        item.failure_reason,
        item.analysis.summary,
        item.analysis.likely_root_cause
      ),
    [item]
  );

  const title = useMemo(
    () =>
      analysisTitle(
        item.failure_reason,
        item.analysis.summary,
        item.job.description
      ),
    [item]
  );

  const providerName = providerDisplayName(provider, providerLabel);

  const handleCopy = async () => {
    const report = generateBugReport(
      item,
      runName,
      pulpitoUrl,
      providerName,
      category
    );
    await copyToClipboard(report);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const rootCause =
    item.analysis.likely_root_cause?.trim() || item.analysis.summary;

  return (
    <article className={`analysis-card cat-${category}`}>
      <header className="analysis-card-header">
        <div className="analysis-card-meta">
          <span className={`analysis-category-badge cat-${category}`}>
            {categoryIcon(category)} {categoryLabel(category)}
          </span>
          <span className="analysis-provider">
            ✦ {providerName}
          </span>
        </div>
        <h3 className="analysis-card-title">{title}</h3>
        <p className="analysis-card-sub">
          Job #{item.job.job_id} · {item.job.machine} · {item.job.os_type}{" "}
          {item.job.os_version}
        </p>
      </header>

      <div className="analysis-tabs">
        <button
          type="button"
          className={tab === "analysis" ? "active" : ""}
          onClick={() => setTab("analysis")}
        >
          Analysis
        </button>
        <button
          type="button"
          className={tab === "logs" ? "active" : ""}
          onClick={() => setTab("logs")}
        >
          Logs
        </button>
      </div>

      <div className="analysis-card-body">
        {tab === "analysis" ? (
          <>
            <p className="analysis-summary">{item.analysis.summary}</p>

            {item.analysis.likely_root_cause &&
              item.analysis.likely_root_cause !== item.analysis.summary && (
                <section className="analysis-section">
                  <h4>Root cause</h4>
                  <p>{rootCause}</p>
                </section>
              )}

            <section className="analysis-section">
              <h4>Confidence</h4>
              <ConfidenceBar value={item.analysis.confidence} />
            </section>

            {item.analysis.next_steps.length > 0 && (
              <section className="analysis-section">
                <h4>Recommended actions</h4>
                <ol className="analysis-actions">
                  {item.analysis.next_steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </section>
            )}

            {item.failure_reason && (
              <section className="analysis-section analysis-pulpito">
                <h4>Pulpito</h4>
                <p className="analysis-mono">{item.failure_reason}</p>
              </section>
            )}

            {item.analysis.evidence.length > 0 && (
              <section className="analysis-section">
                <button
                  type="button"
                  className="analysis-evidence-toggle"
                  onClick={() => setShowEvidence(!showEvidence)}
                >
                  {showEvidence ? "▲" : "▼"} Evidence (
                  {item.analysis.evidence.length})
                </button>
                {showEvidence && (
                  <ul className="analysis-evidence-list">
                    {item.analysis.evidence.map((line, i) => (
                      <li key={i}>
                        <code>{line}</code>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}

            {item.log_empty && (
              <p className="analysis-warn">Log missing or empty on archive.</p>
            )}
            {item.log_truncated && !item.log_empty && (
              <p className="analysis-hint">
                Digest built from the last ~1.5 MB of teuthology.log; earlier
                lines are not included.
              </p>
            )}
          </>
        ) : (
          <div className="analysis-logs-panel">
            <p>
              <a href={item.log_url} target="_blank" rel="noreferrer">
                Open teuthology.log ↗
              </a>
              {" · "}
              <a href={pulpitoUrl} target="_blank" rel="noreferrer">
                Pulpito run ↗
              </a>
            </p>
            {item.log_truncated && (
              <p className="analysis-hint">
                Archive fetch uses the log tail only (MAX_LOG_BYTES).
              </p>
            )}
            {item.digest ? (
              <pre className="analysis-digest">{item.digest}</pre>
            ) : (
              <p className="analysis-hint">
                No digest in this response. Enable{" "}
                <strong>Show log digest</strong> and re-run analyze to view the
                excerpt sent to the model.
              </p>
            )}
          </div>
        )}

        <footer className="analysis-card-footer">
          <button
            type="button"
            className={`btn btn-copy-report ${copied ? "copied" : ""}`}
            onClick={() => void handleCopy()}
          >
            {copied ? "✓ Copied" : "📋 Copy Bug Report"}
          </button>
          <div className="analysis-feedback">
            {feedback === null ? (
              <>
                <span>Helpful?</span>
                <button
                  type="button"
                  className="feedback-btn up"
                  title="Helpful"
                  onClick={() => setFeedback(true)}
                >
                  👍
                </button>
                <button
                  type="button"
                  className="feedback-btn down"
                  title="Not helpful"
                  onClick={() => setFeedback(false)}
                >
                  👎
                </button>
              </>
            ) : (
              <span
                className={
                  feedback ? "feedback-done good" : "feedback-done bad"
                }
              >
                {feedback ? "✓ Marked helpful" : "✗ Marked unhelpful"}
              </span>
            )}
          </div>
        </footer>
      </div>
    </article>
  );
}
