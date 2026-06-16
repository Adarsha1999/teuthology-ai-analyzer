import { useCallback, useEffect, useState } from "react";
import AIModelSelector from "./components/AIModelSelector";
import AssistantChat from "./AssistantChat";
import FailureAnalysisCard from "./components/FailureAnalysisCard";
import { applyTheme, getStoredTheme, type Theme } from "./theme";
import {
  analyze,
  analyzeLocal,
  connect,
  disconnect,
  getConfig,
  getConnection,
  getCachedAnalysis,
  getHistory,
  getOllamaModels,
  type AnalyzeResult,
  type AppConfig,
  type Connection,
  type HistoryEntry,
  type LLMProvider,
  type ProviderConfig,
} from "./lib/api";
import {
  buildModelOptions,
  formatModelId,
  parseModelId,
  type ModelOption,
} from "./models";

type Page = "dashboard" | "settings";

function statusChip(status: string) {
  const s = status.toLowerCase();
  const cls =
    s === "fail" || s === "pass" || s === "dead" || s === "queued"
      ? s
      : "queued";
  return <span className={`chip ${cls}`}>{status.toUpperCase()}</span>;
}

function historyDot(entry: HistoryEntry) {
  if (entry.fail_count && !entry.pass_count) return "fail";
  if (entry.pass_count && !entry.fail_count) return "pass";
  return "mixed";
}

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("ollama:llama3.2");
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [timeout, setTimeout] = useState(600);

  type AnalyzeSource = "pulpito" | "local";
  const [analyzeSource, setAnalyzeSource] = useState<AnalyzeSource>("pulpito");
  const [runUrl, setRunUrl] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [localReadMode, setLocalReadMode] = useState<"full" | "tail">("full");
  const [includeDead, setIncludeDead] = useState(false);
  const [maxFailures, setMaxFailures] = useState(10);
  const [showDigest, setShowDigest] = useState(false);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [activeRunName, setActiveRunName] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());

  const toggleTheme = () => {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    applyTheme(next);
  };

  const refresh = useCallback(async () => {
    const [cfg, conn, hist, ollama] = await Promise.all([
      getConfig(),
      getConnection(),
      getHistory(),
      getOllamaModels().catch(() => null),
    ]);
    setConfig(cfg);
    setConnection(conn);
    setHistory(hist);
    const ollamaNames = ollama?.healthy ? ollama.models.map((m) => m.name) : undefined;
    const options = buildModelOptions(cfg.providers, ollamaNames);
    setModelOptions(options);
    const baseProv =
      cfg.providers.find((p) => p.requires_base_url) ??
      cfg.providers.find((p) => p.provider === cfg.default_provider);
    setBaseUrl(baseProv?.base_url ?? "http://127.0.0.1:11434");
    if (conn.connected && conn.provider && conn.model) {
      setModelId(formatModelId(conn.provider, conn.model));
      const prov = cfg.providers.find((p) => p.provider === conn.provider);
      setTimeout(prov?.request_timeout ?? 600);
    } else {
      const def = cfg.providers.find((p) => p.provider === cfg.default_provider);
      const defModel = def?.model ?? options[0]?.model ?? "llama3.2";
      setModelId(formatModelId(cfg.default_provider, defModel));
      setTimeout(def?.request_timeout ?? 600);
    }
  }, []);

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, [refresh]);

  const providerConfig = (provider: LLMProvider): ProviderConfig | undefined =>
    config?.providers.find((p) => p.provider === provider);

  const connectModel = async (id: string, opts?: { stayOnPage?: boolean }) => {
    if (!id.trim()) return;
    const { provider, model } = parseModelId(id);
    setError(null);
    setConnecting(true);
    try {
      const prov = providerConfig(provider);
      const conn = await connect({
        provider,
        base_url: prov?.requires_base_url ? baseUrl : "",
        model,
        api_key: prov?.requires_api_key ? apiKey : "",
        request_timeout: timeout,
      });
      setConnection(conn);
      setModelId(id);
      if (prov?.requires_api_key) {
        setApiKey("");
      }
      if (!opts?.stayOnPage) {
        setPage("dashboard");
      }
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setConnecting(false);
    }
  };

  const handleConnect = async () => {
    await connectModel(modelId);
  };

  const handleDisconnect = async () => {
    setError(null);
    try {
      await disconnect();
      setConnection({ connected: false });
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const pulpitoRunUrl = useCallback(
    (runName: string) => {
      const base = (config?.pulpito_base ?? "https://pulpito.ceph.com").replace(
        /\/$/,
        ""
      );
      return `${base}/${runName.replace(/^\//, "")}/`;
    },
    [config?.pulpito_base]
  );

  const runAnalyze = async (url: string) => {
    if (!url.trim()) return;
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const res = await analyze({
        run_url: url,
        include_dead: includeDead,
        max_failures: maxFailures,
        show_digest: showDigest,
      });
      setResult(res);
      setActiveRunName(res.run_name);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const runAnalyzeLocal = async (path: string) => {
    if (!path.trim()) return;
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const res = await analyzeLocal({
        run_path: path,
        include_dead: includeDead,
        max_failures: maxFailures,
        show_digest: showDigest,
        read_mode: localReadMode,
      });
      setResult(res);
      setActiveRunName(res.run_name);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyze = () => {
    if (analyzeSource === "local") {
      void runAnalyzeLocal(localPath);
    } else {
      void runAnalyze(runUrl);
    }
  };

  const { provider: currentProvider, model: currentModel } = parseModelId(modelId);
  const currentProvCfg = providerConfig(currentProvider);
  const isConnected =
    connection?.connected &&
    connection.provider === currentProvider &&
    connection.model === currentModel &&
    !connecting;

  const handleHistoryClick = async (entry: HistoryEntry) => {
    setRunUrl(pulpitoRunUrl(entry.run_name));
    setActiveRunName(entry.run_name);
    setPage("dashboard");
    setError(null);

    if (entry.analyzed) {
      try {
        const cached = await getCachedAnalysis(entry.run_name);
        setResult(cached);
      } catch (e) {
        setError(String(e));
        setResult(null);
      }
      return;
    }

    setResult((prev) => (prev?.run_name === entry.run_name ? prev : null));
  };

  const historyActive = (runName: string) =>
    activeRunName === runName || result?.run_name === runName;

  const apiStatus = connecting
    ? "Connecting…"
    : isConnected
      ? "API Connected"
      : "API Offline";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-logo">T</span>
          Teuthology AI
        </div>
        <nav className="nav">
          <button
            className={page === "dashboard" ? "active" : ""}
            onClick={() => setPage("dashboard")}
          >
            Dashboard
          </button>
          <button
            className={page === "settings" ? "active" : ""}
            onClick={() => setPage("settings")}
          >
            LLM settings
          </button>
        </nav>
        <div className="history-title">Recent runs</div>
        {history.length === 0 ? (
          <p style={{ padding: "0 0.75rem", fontSize: "0.78rem", color: "#9ca3af" }}>
            No runs yet
          </p>
        ) : (
          history.map((h) => {
            const label = h.run_name.split("/").pop() ?? h.run_name;
            const short =
              label.length > 28 ? `${label.slice(0, 28)}…` : label;
            return (
              <button
                type="button"
                key={h.run_name}
                className={`history-item ${historyActive(h.run_name) ? "active" : ""}`}
                onClick={() => handleHistoryClick(h)}
                title={`${h.run_name}\n${h.pass_count} pass · ${h.fail_count} fail · ${h.total} jobs`}
                disabled={loading}
              >
                <span className={`history-dot ${historyDot(h)}`} />
                <span className="history-item-text">
                  <span className="history-item-name">{short}</span>
                  <span className="history-item-meta">
                    {h.pass_count}P / {h.fail_count}F
                    {h.analyzed ? " · analyzed" : ""}
                  </span>
                </span>
              </button>
            );
          })
        )}
      </aside>

      <main className="main">
        <header className="top-header">
          <div className="top-header-brand">
            <span className="top-header-logo">T</span>
            <span className="top-header-title">Teuthology AI Analyzer</span>
          </div>

          <div className="top-header-search">
            <svg className="search-icon" viewBox="0 0 24 24" aria-hidden>
              <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
              <path d="M20 20l-3-3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <input
              type="search"
              placeholder="Search runs, suites, tests…"
              aria-label="Search runs"
            />
            <kbd className="search-kbd">⌘ K</kbd>
          </div>

          <div className="top-header-actions">
            <AIModelSelector
              config={config}
              connection={connection}
              connecting={connecting}
              onSelect={async (provider, model) => {
                await connectModel(formatModelId(provider, model), { stayOnPage: true });
              }}
            />

            <span
              className={`api-badge ${connecting ? "pending" : isConnected ? "on" : "off"}`}
              title={connection?.model ?? undefined}
            >
              <span className="api-badge-dot" />
              {apiStatus}
            </span>

            <button
              type="button"
              className="header-icon-btn"
              onClick={toggleTheme}
              aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
              title={theme === "light" ? "Dark mode" : "Light mode"}
            >
              {theme === "light" ? (
                <svg viewBox="0 0 24 24" aria-hidden>
                  <path
                    d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" aria-hidden>
                  <circle
                    cx="12"
                    cy="12"
                    r="4"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  />
                  <path
                    d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
              )}
            </button>

            <button type="button" className="header-icon-btn" aria-label="Notifications">
              <svg viewBox="0 0 24 24" aria-hidden>
                <path
                  d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>

            <button
              type="button"
              className="assistant-btn"
              onClick={() => setAssistantOpen(true)}
            >
              <svg viewBox="0 0 24 24" aria-hidden>
                <path
                  d="M12 2l2.4 7.2H22l-6 4.6 2.3 7.2L12 16.4 5.7 21l2.3-7.2-6-4.6h7.6L12 2z"
                  fill="currentColor"
                />
              </svg>
              <span>Teuth Assistant</span>
            </button>

            <div className="header-avatar">
              <img
                src="/ceph-logo.svg"
                alt="Ceph"
                className="header-ceph-logo"
                width={36}
                height={36}
              />
            </div>
          </div>
        </header>

        <div className="main-body">
        {error && <div className="error-banner">{error}</div>}

        {page === "settings" && (
          <div className="card">
            <h3>LLM connection</h3>
            {connection?.connected ? (
              <p className="sub-status">
                Connected — {connection.icon} {connection.label} ·{" "}
                <code>{connection.model}</code>
              </p>
            ) : (
              <p className="sub-status off">Not connected</p>
            )}
            <div className="form-grid form">
              <div>
                <div className="field">
                  <label>Model</label>
                  <select
                    value={modelId}
                    onChange={(e) => {
                      const id = e.target.value;
                      setModelId(id);
                      const { provider } = parseModelId(id);
                      const prov = providerConfig(provider);
                      if (prov) setTimeout(prov.request_timeout);
                    }}
                    disabled={connecting}
                  >
                    {(config?.providers ?? []).map((prov) => {
                      const opts = modelOptions.filter(
                        (o) => o.provider === prov.provider
                      );
                      if (opts.length === 0) return null;
                      return (
                        <optgroup key={prov.provider} label={prov.label}>
                          {opts.map((o) => (
                            <option key={o.id} value={o.id}>
                              {o.label}
                            </option>
                          ))}
                        </optgroup>
                      );
                    })}
                  </select>
                </div>
                {currentProvCfg?.requires_base_url && (
                  <div className="field">
                    <label>{currentProvCfg.label} base URL</label>
                    <input
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      placeholder={currentProvCfg.base_url || "http://127.0.0.1:11434"}
                    />
                  </div>
                )}
              </div>
              <div>
                {currentProvCfg?.requires_api_key && (
                  <div className="field">
                    <label>{currentProvCfg.label} API key</label>
                    {currentProvCfg.has_api_key && (
                      <small style={{ color: "#6b7280" }}>
                        Loaded from config (hidden). Paste to override.
                      </small>
                    )}
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder={
                        currentProvCfg.api_key_env
                          ? `From backend/.env (${currentProvCfg.api_key_env})`
                          : "From backend/.env"
                      }
                    />
                  </div>
                )}
                <div className="field">
                  <label>Timeout (seconds)</label>
                  <input
                    type="number"
                    min={30}
                    max={3600}
                    value={timeout}
                    onChange={(e) => setTimeout(Number(e.target.value))}
                  />
                </div>
              </div>
            </div>
            <p style={{ fontSize: "0.8rem", color: "#6b7280" }}>
              {currentProvCfg?.kind === "cursor"
                ? "Cursor uses the cloud agent SDK. Install with pip install -e \".[cursor]\" and set CURSOR_API_KEY."
                : currentProvCfg?.kind === "ollama"
                  ? "Requires a running Ollama server with the model pulled locally."
                  : currentProvCfg?.kind === "bob_cli"
                    ? "IBM Bob Shell runs locally via the `bob` CLI. Set BOBSHELL_API_KEY, install Bob Shell, and trust IBM_BOB_WORKDIR once (see backend/.env.example)."
                    : currentProvCfg?.requires_api_key
                      ? `Set ${currentProvCfg.api_key_env || "the provider API key"} in your .env file.`
                      : "Configure the provider in backend/.env (see backend/.env.example)."}
            </p>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                className="btn btn-primary"
                onClick={handleConnect}
                disabled={connecting}
              >
                {connecting ? "Connecting…" : "Connect"}
              </button>
              <button
                className="btn"
                onClick={handleDisconnect}
                disabled={!connection?.connected}
              >
                Disconnect
              </button>
            </div>
          </div>
        )}

        {page === "dashboard" && (
          <>
            <div className="page-header">
              <div>
                <h1>Dashboard</h1>
                <p>Monitor Pulpito teuthology runs and AI-powered failure analysis.</p>
                {connection?.connected ? (
                  <div className="sub-status">
                    <span className="conn-dot" style={{ background: "#22c55e" }} />
                    {connection.label} connected · <code>{connection.model}</code>
                  </div>
                ) : (
                  <div className="sub-status off">
                    Connect a model in LLM settings
                  </div>
                )}
              </div>
              <a
                className="btn"
                href={config?.pulpito_base ?? "https://pulpito.ceph.com"}
                target="_blank"
                rel="noreferrer"
              >
                Open Pulpito
              </a>
            </div>

            {!isConnected ? (
              <div className="empty">
                <p style={{ fontSize: "2rem" }}>{currentProvCfg?.icon ?? "🦙"}</p>
                <p>
                  <strong>Connect a model</strong> to analyze runs.
                </p>
                <button
                  className="btn btn-primary"
                  onClick={() => setPage("settings")}
                >
                  Go to LLM settings
                </button>
              </div>
            ) : (
              <>
                <div className="card">
                  <h3>Analyze teuthology run</h3>
                  <div className="source-toggle">
                    <button
                      type="button"
                      className={`source-toggle-btn ${analyzeSource === "pulpito" ? "active" : ""}`}
                      onClick={() => setAnalyzeSource("pulpito")}
                    >
                      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden>
                        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="2"/>
                        <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10A15.3 15.3 0 0 1 12 2" fill="none" stroke="currentColor" strokeWidth="2"/>
                      </svg>
                      Pulpito URL
                    </button>
                    <button
                      type="button"
                      className={`source-toggle-btn ${analyzeSource === "local" ? "active" : ""}`}
                      onClick={() => setAnalyzeSource("local")}
                    >
                      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden>
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                      </svg>
                      Local Archive
                    </button>
                  </div>

                  {analyzeSource === "pulpito" ? (
                    <div className="form field">
                      <label>Run URL or name</label>
                      <textarea
                        rows={3}
                        value={runUrl}
                        onChange={(e) => setRunUrl(e.target.value)}
                        placeholder="https://pulpito.ceph.com/user-2026-01-01_12:00:00-suite-branch-distro-mtype/"
                      />
                    </div>
                  ) : (
                    <div className="form field">
                      <label>Archive path</label>
                      <textarea
                        rows={3}
                        value={localPath}
                        onChange={(e) => setLocalPath(e.target.value)}
                        placeholder="/home/ubuntu/archive/user-2026-06-09_12:00:00-fs:basic-branch-distro/"
                      />
                      <div className="options-row" style={{ marginTop: "0.5rem" }}>
                        <label>
                          Read mode:{" "}
                          <select
                            value={localReadMode}
                            onChange={(e) => setLocalReadMode(e.target.value as "full" | "tail")}
                            style={{ fontSize: "0.85rem" }}
                          >
                            <option value="full">Full log (better accuracy)</option>
                            <option value="tail">Tail only (faster)</option>
                          </select>
                        </label>
                      </div>
                    </div>
                  )}
                  <div className="options-row">
                    <label>
                      <input
                        type="checkbox"
                        checked={includeDead}
                        onChange={(e) => setIncludeDead(e.target.checked)}
                      />{" "}
                      Include dead jobs
                    </label>
                    <label>
                      Max failed jobs{" "}
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={maxFailures}
                        onChange={(e) => setMaxFailures(Number(e.target.value))}
                        style={{ width: 60 }}
                      />
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={showDigest}
                        onChange={(e) => setShowDigest(e.target.checked)}
                      />{" "}
                      Show log digest
                    </label>
                  </div>
                  <button
                    className="btn btn-primary"
                    onClick={handleAnalyze}
                    disabled={
                      loading ||
                      (analyzeSource === "pulpito" ? !runUrl.trim() : !localPath.trim())
                    }
                  >
                    {loading ? "Analyzing…" : "Analyze run"}
                  </button>
                  {loading && (
                    <p className="loading">
                      Fetching logs and running AI inference — this may take
                      several minutes…
                    </p>
                  )}
                </div>

                {result && (
                  <>
                    <div className="metrics">
                      <div className="metric-card">
                        <div className="label">Total jobs</div>
                        <div className="value">{result.metrics.total}</div>
                      </div>
                      <div className="metric-card">
                        <div className="label">Failed jobs</div>
                        <div className="value red">{result.metrics.fail_count}</div>
                      </div>
                      <div className="metric-card">
                        <div className="label">Queued</div>
                        <div className="value amber">
                          {result.metrics.queued_count}
                        </div>
                      </div>
                      <div className="metric-card">
                        <div className="label">Pass rate</div>
                        <div
                          className={`value ${
                            result.metrics.pass_rate >= 50 ? "green" : "red"
                          }`}
                        >
                          {result.metrics.pass_rate}%
                        </div>
                      </div>
                    </div>

                    <div className="table-header">
                      <h2 style={{ margin: 0 }}>Run jobs</h2>
                      <span className="live">● LIVE</span>
                    </div>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Job</th>
                            <th>Status</th>
                            <th>OS</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.jobs.map((j) => (
                            <tr key={j.job_id}>
                              <td>
                                <strong>#{j.job_id}</strong>
                              </td>
                              <td>
                                {j.description.slice(0, 70)}
                                {j.description.length > 70 ? "…" : ""}
                                <br />
                                <small style={{ color: "#9ca3af" }}>{j.machine}</small>
                              </td>
                              <td>{statusChip(j.status)}</td>
                              <td>
                                {j.os_type} {j.os_version}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {result.pulpito_url ? (
                      <p style={{ marginTop: "0.5rem" }}>
                        <a href={result.pulpito_url} target="_blank" rel="noreferrer">
                          Open run in Pulpito →
                        </a>
                      </p>
                    ) : (
                      <p style={{ marginTop: "0.5rem", color: "#6b7280", fontSize: "0.85rem" }}>
                        Local archive analysis — no Pulpito link
                      </p>
                    )}

                    {result.failed_analyses.length > 0 && (
                      <>
                        <div className="table-header">
                          <h2 style={{ margin: 0 }}>Failure analysis</h2>
                        </div>
                        <div className="analysis-list">
                          {result.failed_analyses.map((item) => (
                            <FailureAnalysisCard
                              key={item.job.job_id}
                              item={item}
                              runName={result.run_name}
                              pulpitoUrl={result.pulpito_url}
                              provider={connection?.provider}
                              providerLabel={connection?.label}
                            />
                          ))}
                        </div>
                      </>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}
        </div>

        <AssistantChat
          open={assistantOpen}
          onClose={() => setAssistantOpen(false)}
          connected={!!isConnected}
          model={
            connection?.model
              ? `${connection.label ?? connection.provider} · ${connection.model}`
              : currentModel
          }
        />
      </main>
    </div>
  );
}
