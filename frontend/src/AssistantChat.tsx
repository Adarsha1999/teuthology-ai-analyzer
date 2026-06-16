import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { assistantChat, type ChatMessage } from "./lib/api";

const DOCS_URL =
  "https://docs.ceph.com/projects/teuthology/en/latest/README.html";

const WELCOME =
  "I'm Teuth Assistant — your guide to Ceph Teuthology. I answer from the official documentation: suites, workers, scheduling, archives, and how runs relate to Pulpito and teuthology.log.";

const SUGGESTED_QUESTIONS = [
  "How do I schedule a suite with teuthology-suite?",
  "What does teuthology-worker do?",
  "Where are teuthology logs stored after a run?",
  "What are the main teuthology CLI utilities?",
  "How does teuthology run tests on remote machines?",
  "How is Pulpito related to teuthology archives?",
];

type Props = {
  open: boolean;
  onClose: () => void;
  connected: boolean;
  model?: string;
};

function formatInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

function MessageBody({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div className="assistant-msg-text">
      {lines.map((line, i) => (
        <p key={i}>{line ? formatInline(line) : <br />}</p>
      ))}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="assistant-typing-dots" aria-label="Assistant is typing">
      <span />
      <span />
      <span />
    </div>
  );
}

export default function AssistantChat({ open, onClose, connected, model }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: WELCOME },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const hasUserMessages = messages.some((m) => m.role === "user");
  const showSuggestions = connected && !hasUserMessages && !loading;

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      setTimeout(() => inputRef.current?.focus(), 200);
    }
  }, [open, messages, loading]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || loading) return;
      if (!connected) {
        setError("Connect a model first — pick one in the top bar.");
        return;
      }
      setError(null);
      const userMsg: ChatMessage = { role: "user", content: trimmed };
      const history = [...messages, userMsg]
        .filter(
          (m) =>
            (m.role === "user" || m.role === "assistant") &&
            m.content.trim().length > 0 &&
            !(m.role === "assistant" && m.content === WELCOME)
        )
        .slice(-20);
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setLoading(true);
      try {
        const { reply } = await assistantChat({ messages: history });
        setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    [connected, loading, messages]
  );

  const handleSend = () => void sendMessage(input);

  const resetChat = () => {
    setMessages([{ role: "assistant", content: WELCOME }]);
    setError(null);
    setInput("");
  };

  if (!open) return null;

  return (
    <div className="assistant-overlay" role="presentation" onClick={onClose}>
      <div
        className="assistant-panel"
        role="dialog"
        aria-labelledby="assistant-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="assistant-header">
          <div className="assistant-header-brand">
            <div className="assistant-avatar bot" aria-hidden>
              <svg viewBox="0 0 24 24">
                <path
                  d="M12 2l2.4 7.2H22l-6 4.6 2.3 7.2L12 16.4 5.7 21l2.3-7.2-6-4.6h7.6L12 2z"
                  fill="currentColor"
                />
              </svg>
            </div>
            <div>
              <h2 id="assistant-title">Teuth Assistant</h2>
              <p className="assistant-sub">
                <span className={`assistant-status ${connected ? "on" : "off"}`}>
                  {connected ? "Online" : "Offline"}
                </span>
                {model ? (
                  <>
                    {" · "}
                    <code>{model}</code>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          <div className="assistant-header-actions">
            <button
              type="button"
              className="assistant-icon-btn"
              onClick={resetChat}
              title="New conversation"
              aria-label="New conversation"
            >
              <svg viewBox="0 0 24 24" aria-hidden>
                <path
                  d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <path
                  d="M3 3v5h5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </button>
            <button
              type="button"
              className="assistant-close"
              onClick={onClose}
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </header>

        <div className="assistant-doc-banner">
          <svg viewBox="0 0 24 24" aria-hidden>
            <path
              d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <span>
            Answers grounded in{" "}
            <a href={DOCS_URL} target="_blank" rel="noreferrer">
              Teuthology upstream docs
            </a>
          </span>
        </div>

        <div className="assistant-messages">
          {!connected && (
            <div className="assistant-offline-card">
              <span className="assistant-offline-icon">🦙</span>
              <p>
                <strong>No model connected</strong>
              </p>
              <p>Select a model in the header dropdown to start chatting.</p>
            </div>
          )}

          {messages.map((m, i) => (
            <div
              key={i}
              className={`assistant-row ${m.role === "user" ? "user" : "assistant"}`}
            >
              {m.role === "assistant" && (
                <div className="assistant-avatar bot sm" aria-hidden>
                  <svg viewBox="0 0 24 24">
                    <path
                      d="M12 2l2.4 7.2H22l-6 4.6 2.3 7.2L12 16.4 5.7 21l2.3-7.2-6-4.6h7.6L12 2z"
                      fill="currentColor"
                    />
                  </svg>
                </div>
              )}
              <div className="assistant-bubble-wrap">
                <div className={`assistant-bubble ${m.role}`}>
                  {m.role === "assistant" && i === 0 ? (
                    <>
                      <p className="assistant-welcome-title">Hello!</p>
                      <MessageBody content={m.content} />
                    </>
                  ) : (
                    <MessageBody content={m.content} />
                  )}
                </div>
              </div>
              {m.role === "user" && (
                <div className="assistant-avatar user sm" aria-hidden>
                  You
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="assistant-row assistant">
              <div className="assistant-avatar bot sm" aria-hidden>
                <svg viewBox="0 0 24 24">
                  <path
                    d="M12 2l2.4 7.2H22l-6 4.6 2.3 7.2L12 16.4 5.7 21l2.3-7.2-6-4.6h7.6L12 2z"
                    fill="currentColor"
                  />
                </svg>
              </div>
              <div className="assistant-bubble assistant">
                <TypingIndicator />
              </div>
            </div>
          )}

          {showSuggestions && (
            <div className="assistant-suggestions">
              <p className="assistant-suggestions-label">Suggested questions</p>
              <div className="assistant-chips">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="assistant-chip"
                    onClick={() => void sendMessage(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {error && <div className="assistant-error">{error}</div>}

        <footer className="assistant-footer">
          <div className="assistant-input-wrap">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              placeholder={
                connected
                  ? "Ask about suites, workers, logs…"
                  : "Connect a model to chat"
              }
              disabled={loading || !connected}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            <button
              type="button"
              className="assistant-send"
              disabled={loading || !connected || !input.trim()}
              onClick={handleSend}
              aria-label="Send message"
            >
              <svg viewBox="0 0 24 24" aria-hidden>
                <path
                  d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
          <p className="assistant-footer-hint">Enter to send · Shift+Enter for newline</p>
        </footer>
      </div>
    </div>
  );
}
