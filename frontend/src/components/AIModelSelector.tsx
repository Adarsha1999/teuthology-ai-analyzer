import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import {
  getBobHealth,
  getOllamaModels,
  type AppConfig,
  type BobHealthResponse,
  type Connection,
  type OllamaModel,
  type ProviderConfig,
} from "../lib/api";

const TAG_LABELS: Record<string, string> = {
  code_analysis: "Code",
  script_tracing: "Scripts",
  failure_analysis: "Failure RCA",
  chat: "Chat",
  summarization: "Summary",
  fast_chat: "Fast",
  quick_summary: "Quick",
  general_reasoning: "General",
};

function RecommendationTags({ tags }: { tags: string[] }) {
  if (!tags.length) return null;
  return (
    <span style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
      {tags.slice(0, 3).map((t) => (
        <span
          key={t}
          style={{
            fontSize: 9,
            fontWeight: 600,
            padding: "1px 5px",
            borderRadius: 3,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            border: "1px solid var(--accent-med)",
            lineHeight: 1.6,
            letterSpacing: "0.02em",
          }}
        >
          {TAG_LABELS[t] ?? t}
        </span>
      ))}
    </span>
  );
}

function GroupHeader({
  label,
  statusDot,
  onRefresh,
}: {
  label: string;
  statusDot?: "green" | "red" | "yellow" | "grey";
  onRefresh?: (e: ReactMouseEvent) => void;
}) {
  const dotColor =
    statusDot === "green"
      ? "var(--success)"
      : statusDot === "red"
        ? "var(--danger)"
        : statusDot === "yellow"
          ? "#f59e0b"
          : "var(--text-muted)";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "7px 12px 5px",
        borderBottom: "1px solid var(--border-soft)",
        background: "var(--bg-card-soft)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        {statusDot && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              flexShrink: 0,
              background: dotColor,
              boxShadow: statusDot === "green" ? `0 0 5px ${dotColor}` : "none",
            }}
          />
        )}
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: "var(--text-secondary)",
            textTransform: "uppercase",
            letterSpacing: "0.07em",
          }}
        >
          {label}
        </span>
      </div>
      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          title="Refresh"
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            padding: "2px 4px",
            borderRadius: 4,
            display: "flex",
            alignItems: "center",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "var(--accent)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--text-muted)";
          }}
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
            <path d="M21 3v5h-5" />
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
            <path d="M3 21v-5h5" />
          </svg>
        </button>
      )}
    </div>
  );
}

function ModelRow({
  name,
  displayName,
  subtitle,
  size,
  tags,
  isSelected,
  isAgent,
  healthStatus,
  disabled,
  onSelect,
}: {
  name: string;
  displayName?: string;
  subtitle?: string;
  size?: string | null;
  tags: string[];
  isSelected: boolean;
  isAgent?: boolean;
  healthStatus?: "healthy" | "error" | "disabled" | "loading";
  disabled?: boolean;
  onSelect: () => void;
}) {
  const statusColor =
    healthStatus === "healthy"
      ? "var(--success)"
      : healthStatus === "error"
        ? "var(--danger)"
        : "var(--text-muted)";

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "flex-start",
        flexDirection: "column",
        gap: 3,
        padding: "9px 12px",
        background: isSelected ? "var(--accent-soft)" : "transparent",
        border: "none",
        borderBottom: "1px solid var(--border-soft)",
        cursor: disabled ? "not-allowed" : "pointer",
        textAlign: "left",
        fontFamily: "inherit",
        transition: "background 0.1s",
        opacity: disabled ? 0.45 : 1,
      }}
      onMouseEnter={(e) => {
        if (!isSelected && !disabled) {
          e.currentTarget.style.background = "var(--bg-card-soft)";
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) e.currentTarget.style.background = "transparent";
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, width: "100%" }}>
        <span
          style={{
            width: 14,
            textAlign: "center",
            fontSize: 11,
            color: "var(--accent)",
            flexShrink: 0,
          }}
        >
          {isSelected ? "✓" : ""}
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: isSelected ? 700 : 500,
            color: isSelected ? "var(--accent)" : "var(--text-primary)",
            fontFamily: isAgent ? "inherit" : "'JetBrains Mono', monospace",
            flex: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {displayName ?? name}
        </span>
        {size && (
          <span style={{ fontSize: 10, color: "var(--text-muted)", flexShrink: 0 }}>
            {size}
          </span>
        )}
        {healthStatus && healthStatus !== "loading" && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              flexShrink: 0,
              background: statusColor,
              boxShadow: healthStatus === "healthy" ? `0 0 4px ${statusColor}` : "none",
            }}
          />
        )}
      </div>
      {subtitle && (
        <div style={{ paddingLeft: 20, marginTop: 1 }}>
          <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{subtitle}</span>
        </div>
      )}
      {tags.length > 0 && (
        <div style={{ paddingLeft: 20 }}>
          <RecommendationTags tags={tags} />
        </div>
      )}
    </button>
  );
}

function CloudProviderRow({ label }: { label: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 12px 8px 32px",
        borderBottom: "1px solid var(--border-soft)",
        opacity: 0.45,
      }}
    >
      <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500 }}>
        {label}
      </span>
      <span
        style={{
          fontSize: 9,
          padding: "1px 5px",
          borderRadius: 3,
          background: "var(--bg-card-soft)",
          color: "var(--text-muted)",
          border: "1px solid var(--border-soft)",
          fontWeight: 600,
        }}
      >
        Not configured
      </span>
    </div>
  );
}

function resolveButtonLabel(
  provider: string | undefined,
  model: string | undefined,
  ollamaHealthy: boolean,
  loading: boolean,
  hasOllamaModels: boolean
): string {
  if (provider === "cursor") return "Cursor Agent";
  if (provider === "bob") return "Bob Shell";
  if (!ollamaHealthy) return "Ollama offline";
  if (loading) return "Loading…";
  if (!hasOllamaModels) return "No models";
  const name = model ?? "";
  if (name.length <= 22) return name;
  const parts = name.split(":");
  if (parts.length >= 2) {
    const tag = parts[parts.length - 1];
    const base = parts[0].split("/").at(-1) ?? parts[0];
    const display = `${base}:${tag}`;
    return display.length <= 22 ? display : `${display.slice(0, 20)}…`;
  }
  return `${name.slice(0, 20)}…`;
}

function agentDisplayName(prov: ProviderConfig): string {
  if (prov.kind === "cursor") return "Cursor Agent";
  if (prov.kind === "bob_cli") return "Bob Shell (IBM)";
  return prov.label;
}

function agentSubtitle(prov: ProviderConfig): string {
  if (prov.kind === "cursor") return "Cloud agent SDK for code and log analysis";
  if (prov.kind === "bob_cli") {
    return "Local Bob Shell — bob --auth-method api-key (see IBM Bob docs)";
  }
  return prov.tag;
}

const AGENT_TAGS = ["failure_analysis", "script_tracing", "code_analysis", "chat"];

/** Brief minimum so every provider shows "Switching…" (Ollama/Gemini are otherwise instant). */
const MIN_SWITCH_MS = 350;

type PendingSelection = { provider: string; model: string };

type AIModelSelectorProps = {
  config: AppConfig | null;
  connection: Connection | null;
  connecting: boolean;
  onSelect: (provider: string, model: string) => Promise<void>;
};

export default function AIModelSelector({
  config,
  connection,
  connecting,
  onSelect,
}: AIModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [pending, setPending] = useState<PendingSelection | null>(null);
  const [loading, setLoading] = useState(false);
  const [ollamaHealthy, setOllamaHealthy] = useState(true);
  const [availableModels, setAvailableModels] = useState<OllamaModel[]>([]);
  const [bobHealth, setBobHealth] = useState<BobHealthResponse | null>(null);
  const [bobHealthLoading, setBobHealthLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const providers = config?.providers ?? [];
  const agentProviders = providers.filter(
    (p) => p.kind === "cursor" || p.kind === "bob_cli"
  );
  const cloudProviders = providers.filter((p) =>
    ["openai", "gemini"].includes(p.kind)
  );

  const activeProvider = connection?.connected ? connection.provider : undefined;
  const activeModel = connection?.connected ? connection.model : undefined;
  const displayProvider =
    switching && pending ? pending.provider : activeProvider;
  const displayModel = switching && pending ? pending.model : activeModel;
  const isAgentActive =
    displayProvider === "cursor" || displayProvider === "bob";

  const refreshModels = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getOllamaModels();
      setAvailableModels(data.models);
      setOllamaHealthy(data.healthy);
    } catch {
      setAvailableModels([]);
      setOllamaHealthy(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshModels();
  }, [refreshModels]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setBobHealthLoading(true);
    getBobHealth()
      .then((h) => {
        if (!cancelled) {
          setBobHealth(h);
          setBobHealthLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBobHealth(null);
          setBobHealthLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const handleSelect = useCallback(
    async (provider: string, model: string) => {
      if (
        connection?.connected &&
        connection.provider === provider &&
        connection.model === model
      ) {
        setOpen(false);
        return;
      }
      setPending({ provider, model });
      setSwitching(true);
      setOpen(false);
      const started = Date.now();
      try {
        await onSelect(provider, model);
      } finally {
        const wait = MIN_SWITCH_MS - (Date.now() - started);
        if (wait > 0) {
          await new Promise((r) => setTimeout(r, wait));
        }
        setSwitching(false);
        setPending(null);
      }
    },
    [connection, onSelect]
  );

  const handleRefresh = useCallback(
    async (e: ReactMouseEvent) => {
      e.stopPropagation();
      await refreshModels();
    },
    [refreshModels]
  );

  const hasOllamaModels = availableModels.length > 0;
  const isOffline = !ollamaHealthy;
  const isConnected = !!connection?.connected;

  const buttonLabel = resolveButtonLabel(
    displayProvider,
    displayModel,
    ollamaHealthy,
    loading,
    hasOllamaModels
  );

  const switchingLabel = (() => {
    if (!pending) return "Switching…";
    if (pending.provider === "cursor") return "Switching to Cursor…";
    if (pending.provider === "bob") return "Switching to Bob…";
    if (pending.provider === "gemini") return "Switching to Gemini…";
    if (pending.provider === "openai") return "Switching to OpenAI…";
    const short =
      pending.model.length <= 18
        ? pending.model
        : `${pending.model.slice(0, 16)}…`;
    return `Switching to ${short}…`;
  })();

  const buttonStatusColor = isAgentActive
    ? isConnected
      ? "var(--success)"
      : "var(--danger)"
    : isOffline
      ? "var(--danger)"
      : isConnected
        ? "var(--success)"
        : "var(--text-muted)";

  const busy = switching || connecting;

  return (
    <div ref={ref} style={{ position: "relative", flexShrink: 0 }}>
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        disabled={busy}
        title={
          displayProvider === "cursor"
            ? "AI provider: Cursor Agent"
            : isOffline && displayProvider === "ollama"
              ? "Ollama is offline — run: ollama serve"
              : `AI model: ${displayModel ?? "none"}`
        }
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "5px 10px",
          height: 34,
          borderRadius: 8,
          background: open ? "var(--accent-soft)" : "var(--bg-card-soft)",
          border: `1px solid ${open ? "var(--accent-med)" : "var(--border-soft)"}`,
          color: "var(--text-primary)",
          fontSize: 12,
          fontWeight: 600,
          cursor: busy ? "wait" : "pointer",
          fontFamily: "inherit",
          transition: "all 0.15s",
          whiteSpace: "nowrap",
          opacity: busy ? 0.7 : 1,
        }}
        onMouseEnter={(e) => {
          if (!open) {
            e.currentTarget.style.background = "var(--accent-soft)";
            e.currentTarget.style.borderColor = "var(--accent-med)";
          }
        }}
        onMouseLeave={(e) => {
          if (!open) {
            e.currentTarget.style.background = "var(--bg-card-soft)";
            e.currentTarget.style.borderColor = "var(--border-soft)";
          }
        }}
      >
        <span style={{ fontSize: 13, lineHeight: 1, flexShrink: 0 }}>🧠</span>
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            flexShrink: 0,
            background: buttonStatusColor,
            boxShadow:
              isConnected && !isOffline ? `0 0 5px ${buttonStatusColor}` : "none",
          }}
        />
        {busy ? (
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              color: "var(--text-muted)",
            }}
          >
            <span className="ai-model-spin" />
            {switchingLabel}
          </span>
        ) : displayProvider === "cursor" ? (
          <span style={{ color: "var(--accent)", fontWeight: 700 }}>Cursor Agent</span>
        ) : displayProvider === "bob" ? (
          <span style={{ color: "var(--accent)", fontWeight: 700 }}>Bob Shell</span>
        ) : isOffline && !isAgentActive ? (
          <span style={{ color: "var(--danger)", fontWeight: 600 }}>Ollama offline</span>
        ) : (
          <span style={{ color: "var(--text-primary)" }}>{buttonLabel}</span>
        )}
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform 0.15s",
            color: "var(--text-muted)",
          }}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            minWidth: 280,
            maxWidth: 340,
            background: "var(--bg-card)",
            border: "1px solid var(--border-med)",
            borderRadius: 10,
            boxShadow: "var(--shadow-md)",
            zIndex: 200,
            overflow: "hidden",
          }}
        >
          <GroupHeader
            label="Local Ollama"
            statusDot={isOffline ? "red" : hasOllamaModels ? "green" : "yellow"}
            onRefresh={handleRefresh}
          />

          {isOffline && (
            <div
              style={{
                padding: "8px 12px 8px 32px",
                background: "var(--danger-bg)",
                borderBottom: "1px solid var(--danger-border)",
              }}
            >
              <p style={{ margin: 0, fontSize: 11, color: "var(--danger)", fontWeight: 600 }}>
                ⚠ Ollama not running
              </p>
              <p
                style={{
                  margin: "2px 0 0",
                  fontSize: 10,
                  color: "var(--text-muted)",
                  fontFamily: "monospace",
                }}
              >
                ollama serve
              </p>
            </div>
          )}

          {!isOffline && !hasOllamaModels && !loading && (
            <div style={{ padding: "8px 12px 8px 32px" }}>
              <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)" }}>
                No Ollama models found
              </p>
              <p
                style={{
                  margin: "2px 0 0",
                  fontSize: 10,
                  color: "var(--text-muted)",
                  fontFamily: "monospace",
                }}
              >
                ollama pull llama3.2:latest
              </p>
            </div>
          )}

          {loading && (
            <div
              style={{ padding: "10px 12px 10px 32px", color: "var(--text-muted)", fontSize: 11 }}
            >
              Loading Ollama models…
            </div>
          )}

          <div style={{ maxHeight: 200, overflowY: "auto" }}>
            {availableModels.map((m) => (
              <ModelRow
                key={m.name}
                name={m.name}
                size={m.size}
                tags={m.recommended_for}
                isSelected={
                  !isAgentActive &&
                  displayProvider === "ollama" &&
                  displayModel === m.name
                }
                onSelect={() => void handleSelect("ollama", m.name)}
              />
            ))}
          </div>

          {agentProviders.length > 0 && (
            <>
              <GroupHeader
                label="Local Agents"
                statusDot={
                  agentProviders.some((p) => p.has_api_key) ? "green" : "grey"
                }
              />
              {agentProviders.map((prov) => {
                const isBob = prov.kind === "bob_cli";
                const bobStatus = isBob
                  ? bobHealthLoading
                    ? "loading"
                    : bobHealth?.healthy
                      ? "healthy"
                      : bobHealth
                        ? "error"
                        : "disabled"
                  : prov.has_api_key
                    ? "healthy"
                    : "disabled";
                return (
                  <ModelRow
                    key={prov.provider}
                    name={prov.model}
                    displayName={agentDisplayName(prov)}
                    subtitle={agentSubtitle(prov)}
                    tags={AGENT_TAGS}
                    isSelected={displayProvider === prov.provider}
                    isAgent
                    healthStatus={bobStatus}
                    disabled={isBob ? !prov.has_api_key : !prov.has_api_key}
                    onSelect={() => void handleSelect(prov.provider, prov.model)}
                  />
                );
              })}
              {bobHealth && !bobHealth.healthy && bobHealth.error && (
                <div
                  style={{
                    padding: "7px 12px 7px 32px",
                    background: "var(--danger-bg)",
                    borderBottom: "1px solid var(--danger-border)",
                  }}
                >
                  <p style={{ margin: 0, fontSize: 10, color: "var(--danger)" }}>
                    {bobHealth.error.includes("folder trust")
                      ? "⚠ Folder trust required — run `bob` in IBM_BOB_WORKDIR once"
                      : bobHealth.error.includes("not found")
                        ? "⚠ `bob` not found — install Bob Shell"
                        : `⚠ ${bobHealth.error.slice(0, 100)}`}
                  </p>
                </div>
              )}
            </>
          )}

          {cloudProviders.length > 0 && (
            <>
              <GroupHeader
                label="Cloud Providers"
                statusDot={
                  cloudProviders.some((p) => p.has_api_key) ? "green" : "grey"
                }
              />
              {cloudProviders.flatMap((prov) =>
                prov.has_api_key
                  ? prov.models.map((model) => (
                      <ModelRow
                        key={`${prov.provider}:${model}`}
                        name={model}
                        displayName={`${prov.label} · ${model}`}
                        tags={["failure_analysis", "chat", "summarization"]}
                        isSelected={
                          displayProvider === prov.provider &&
                          displayModel === model
                        }
                        isAgent
                        healthStatus="healthy"
                        onSelect={() => void handleSelect(prov.provider, model)}
                      />
                    ))
                  : [
                      <CloudProviderRow
                        key={prov.provider}
                        label={`${prov.label} · ${prov.tag}`}
                      />,
                    ]
              )}
            </>
          )}

          <div
            style={{ padding: "6px 12px", borderTop: "1px solid var(--border-soft)" }}
          >
            <p style={{ margin: 0, fontSize: 10, color: "var(--text-muted)" }}>
              Selected provider applies globally.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}