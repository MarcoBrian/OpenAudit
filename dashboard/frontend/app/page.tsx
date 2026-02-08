"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";
import { ConnectKitButton } from "connectkit";

import Loader from "./components/Loader";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const SHOW_NON_CHAT = process.env.NEXT_PUBLIC_SHOW_NON_CHAT === "true";

type ProgressEvent = {
  step: string;
  status: string;
  message?: string;
  timestamp?: string;
};

type JobResponse = {
  job_id: string;
  status: string;
  progress?: ProgressEvent;
  submission?: Record<string, unknown>;
  error?: { error: string };
};

type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

type RunHistory = {
  id: string;
  fileName: string;
  status: string;
  createdAt: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type ChatMeta = {
  action?: string;
  durationMs?: number;
};

type AgentProgressEvent = {
  step: string;
  status: string;
  message?: string;
  timestamp?: string;
};

const severityClass = (value?: string) => {
  if (!value) return "";
  const normalized = value.toLowerCase();
  if (normalized === "critical") return "severity-critical";
  if (normalized === "high") return "severity-high";
  if (normalized === "medium") return "severity-medium";
  if (normalized === "low") return "severity-low";
  return "";
};

const MarkdownInline = ({ value }: { value: string }) => {
  return (
    <span className="markdown-inline">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <span>{children}</span>,
          code: ({ children }) => <code>{children}</code>,
        }}
      >
        {value}
      </ReactMarkdown>
    </span>
  );
};

const renderJson = (value: JsonValue, depth = 0): ReactNode => {
  if (Array.isArray(value)) {
    return (
      <div className="json-indent">
        {value.map((item, idx) => (
          <div className="json-node" key={`${depth}-arr-${idx}`}>
            {renderJson(item, depth + 1)}
          </div>
        ))}
      </div>
    );
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    return (
      <div className="json-indent">
        {entries.map(([key, val]) => (
          <div className="json-node" key={`${depth}-${key}`}>
            <div className="json-key">{key}</div>
            {key.toLowerCase() === "severity" && typeof val === "string" ? (
              <div className={`badge ${severityClass(val)}`}>{val}</div>
            ) : key.toLowerCase() === "confidence" &&
              typeof val === "number" ? (
              <div className="badge">Confidence: {val.toFixed(2)}</div>
            ) : typeof val === "object" && val !== null ? (
              <details>
                <summary className="summary muted">Expand</summary>
                {renderJson(val as JsonValue, depth + 1)}
              </details>
            ) : typeof val === "string" ? (
              <div className="json-value">
                <MarkdownInline value={val} />
              </div>
            ) : (
              <div className="json-value">{String(val)}</div>
            )}
          </div>
        ))}
      </div>
    );
  }
  return <div className="json-value">{String(value)}</div>;
};

const MarkdownBlock = ({ value }: { value?: string }) => {
  if (!value) {
    return <div className="muted">Not provided.</div>;
  }
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
    </div>
  );
};

const parseTimestamp = (value?: string) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.getTime();
};

const parseJsonMessage = (value: string): JsonValue | null => {
  if (!value) return null;
  let cleaned = value.trim();
  if (cleaned.startsWith("```")) {
    cleaned = cleaned.replace(/^```[a-zA-Z]*\n?/, "").replace(/```$/, "").trim();
  }
  if (!(cleaned.startsWith("{") || cleaned.startsWith("["))) {
    return null;
  }
  try {
    return JSON.parse(cleaned) as JsonValue;
  } catch {
    return null;
  }
};

const formatDuration = (ms: number | null) => {
  if (!ms || ms < 0) return "—";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${minutes}m ${rem}s`;
};

const steps = [
  { key: "scan", label: "Scan" },
  { key: "extract", label: "Extract" },
  { key: "triage", label: "Triage" },
  { key: "logic", label: "Logic" },
  { key: "finalize", label: "Finalize" },
];

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [contractText, setContractText] = useState<string>("");
  const [tools, setTools] = useState("aderyn");
  const [maxIssues, setMaxIssues] = useState(2);
  const [useLlm, setUseLlm] = useState(true);
  const [useGraph, setUseGraph] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [submission, setSubmission] = useState<Record<string, unknown> | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [artifacts, setArtifacts] = useState<string[]>([]);
  const [history, setHistory] = useState<RunHistory[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatHint, setChatHint] = useState<string | null>(null);
  const [chatMeta, setChatMeta] = useState<ChatMeta | null>(null);
  const [chatEvents, setChatEvents] = useState<AgentProgressEvent[]>([]);

  useEffect(() => {
    const stored = localStorage.getItem("openaudit.history");
    if (stored) {
      try {
        setHistory(JSON.parse(stored) as RunHistory[]);
      } catch {
        setHistory([]);
      }
    }
    const storedSession = localStorage.getItem("openaudit.agent.session_id");
    if (storedSession) {
      setChatSessionId(storedSession);
    }
    const storedChat = localStorage.getItem("openaudit.agent.history");
    if (storedChat) {
      try {
        setChatMessages(JSON.parse(storedChat) as ChatMessage[]);
      } catch {
        setChatMessages([]);
      }
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("openaudit.history", JSON.stringify(history));
  }, [history]);

  useEffect(() => {
    if (chatSessionId) {
      localStorage.setItem("openaudit.agent.session_id", chatSessionId);
    }
  }, [chatSessionId]);

  useEffect(() => {
    localStorage.setItem("openaudit.agent.history", JSON.stringify(chatMessages));
  }, [chatMessages]);

  useEffect(() => {
    if (!chatLoading || !chatSessionId) return;
    let active = true;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/agent/sessions/${chatSessionId}/events`);
        if (!res.ok) return;
        const payload = await res.json();
        if (!active) return;
        setChatEvents(payload.events ?? []);
      } catch {
        // Ignore polling errors while loading
      }
    }, 1000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [chatLoading, chatSessionId]);

  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
        const job: JobResponse = await res.json();
        if (!active) return;
        setStatus(job.status ?? "unknown");
        setSubmission(job.submission ?? null);
        setError(job.error?.error ?? null);
        setIsRunning(job.status !== "completed" && job.status !== "failed");

        const eventsRes = await fetch(`${API_BASE}/api/jobs/${jobId}/events`);
        const eventPayload = await eventsRes.json();
        if (!active) return;
        setEvents(eventPayload.events ?? []);

        if (job.status === "completed" || job.status === "failed") {
          clearInterval(interval);
          const artifactsRes = await fetch(
            `${API_BASE}/api/jobs/${jobId}/artifacts`,
          );
          const artifactsPayload = await artifactsRes.json();
          if (active) {
            setArtifacts(artifactsPayload.artifacts ?? []);
          }
        }
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    }, 1000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [jobId]);

  const handleSubmit = async () => {
    if (!file) return;
    setStatus("starting");
    setEvents([]);
    setSubmission(null);
    setError(null);
    setIsRunning(true);
    setArtifacts([]);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("tools", tools);
    formData.append("max_issues", String(maxIssues));
    formData.append("use_llm", String(useLlm));
    formData.append("use_graph", String(useGraph));

    const res = await fetch(`${API_BASE}/api/jobs`, {
      method: "POST",
      body: formData,
    });
    const payload = await res.json();
    setJobId(payload.job_id);
    setStatus("queued");
    setHistory((prev) =>
      [
        {
          id: payload.job_id,
          fileName: file.name,
          status: "running",
          createdAt: new Date().toISOString(),
        },
        ...prev,
      ].slice(0, 10),
    );
  };

  const handleChatSend = async () => {
    const trimmed = chatInput.trim();
    if (!trimmed || chatLoading) return;
    setChatLoading(true);
    setChatError(null);
    setChatMeta(null);
    setChatEvents([]);

    const longRunning =
      /analy(?:ze|se)\s+bounty|analyze_bounty|run_audit|audit|slither|aderyn/i.test(trimmed);
    if (longRunning) {
      setChatHint("This can take a few minutes. The agent is running static analysis + LLM triage.");
    } else {
      setChatHint("Thinking…");
    }

    let activeSessionId = chatSessionId;
    if (!activeSessionId) {
      activeSessionId = crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setChatSessionId(activeSessionId);
    }

    const userMessage: ChatMessage = {
      id: `${Date.now()}-user`,
      role: "user",
      content: trimmed
    };
    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput("");

    try {
      const res = await fetch(`${API_BASE}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          session_id: activeSessionId ?? undefined
        })
      });
      const payload = await res.json();
      if (!res.ok) {
        throw new Error(payload?.error || "Chat request failed");
      }
      if (payload.session_id) {
        setChatSessionId(payload.session_id);
      }
      if (Array.isArray(payload.history)) {
        const mapped = payload.history
          .filter((item: { role?: string; content?: string }) =>
            item?.role === "user" || item?.role === "assistant"
          )
          .map((item: { role?: string; content?: string }, idx: number) => ({
            id: `${payload.session_id || "session"}-${idx}`,
            role: item.role as "user" | "assistant",
            content: item.content || ""
          }));
        setChatMessages(mapped);
      } else if (payload.response) {
        const assistantMessage: ChatMessage = {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: String(payload.response)
        };
        setChatMessages((prev) => [...prev, assistantMessage]);
      }
      if (payload.duration_ms || payload.action) {
        setChatMeta({
          action: payload.action,
          durationMs: typeof payload.duration_ms === "number" ? payload.duration_ms : undefined
        });
      }
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setChatLoading(false);
      setChatHint(null);
    }
  };

  const handleChatKey = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleChatSend();
    }
  };

  useEffect(() => {
    if (!jobId) return;
    setHistory((prev) =>
      prev.map((run) => (run.id === jobId ? { ...run, status } : run)),
    );
  }, [jobId, status]);

  const handleFileChange = (selected: File | null) => {
    setFile(selected);
    if (!selected) {
      setFileName("");
      setContractText("");
      return;
    }
    setFileName(selected.name);
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result : "";
      setContractText(text);
    };
    reader.readAsText(selected);
  };

  const downloadArtifact = async (name: string) => {
    if (!jobId) return;
    const res = await fetch(`${API_BASE}/api/jobs/${jobId}/artifact/${name}`);
    if (!res.ok) return;
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    window.URL.revokeObjectURL(url);
  };

  const statusLabel = status.toUpperCase();

  const latestEvent = events[events.length - 1];
  const submissionSeverity =
    typeof submission?.severity === "string" ? submission.severity : undefined;
  const submissionConfidence =
    typeof submission?.confidence === "number"
      ? submission.confidence
      : undefined;
  const submissionTitle =
    typeof submission?.title === "string" ? submission.title : undefined;
  const submissionImpact =
    typeof submission?.impact === "string" ? submission.impact : undefined;
  const submissionDescription =
    typeof submission?.description === "string"
      ? submission.description
      : undefined;
  const submissionRemediation =
    typeof submission?.remediation === "string"
      ? submission.remediation
      : undefined;
  const submissionRepro =
    typeof submission?.repro === "string" ? submission.repro : undefined;

  const elapsed = useMemo(() => {
    if (!events.length) return null;
    const start = parseTimestamp(events[0].timestamp);
    const end =
      parseTimestamp(events[events.length - 1].timestamp) ?? Date.now();
    if (!start) return null;
    return end - start;
  }, [events]);

  const stepStatus = (key: string) => {
    const relevant = events.filter((event) =>
      key === "scan" ? event.step.startsWith("scan") : event.step === key,
    );
    if (relevant.some((event) => event.status === "failed")) return "failed";
    if (relevant.some((event) => event.status === "running")) return "running";
    if (relevant.some((event) => event.status === "completed"))
      return "completed";
    return "pending";
  };

  const stepDuration = (key: string) => {
    const relevant = events.filter((event) =>
      key === "scan" ? event.step.startsWith("scan") : event.step === key,
    );
    const startEvent = relevant.find((event) => event.status === "running");
    const endEvent = [...relevant]
      .reverse()
      .find((event) => event.status === "completed");
    const start = parseTimestamp(startEvent?.timestamp);
    const end = parseTimestamp(endEvent?.timestamp);
    if (!start || !end) return null;
    return end - start;
  };

  const hasLaterTerminal = (index: number, step: string) => {
    for (let i = index + 1; i < events.length; i += 1) {
      if (
        events[i].step === step &&
        (events[i].status === "completed" || events[i].status === "failed")
      ) {
        return true;
      }
    }
    return false;
  };

  return (
    <div className="container">
      <header>
        <div className="brand">
          <div>
            <div className="title">OpenAudit</div>
            <div className="muted">
              Autonomous smart‑contract security agent
            </div>
          </div>
        </div>
        <div
          className="header-right"
          style={{ display: "flex", alignItems: "center", gap: "1rem" }}
        >
          <Link
            href="/bounties"
            className="btn-link"
            style={{
              color: "#6877ed",
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            Bounty Dashboard &rarr;
          </Link>
          <ConnectKitButton />
        </div>
      </header>

      <div className="hero">
        <div className="title">Chat with OpenAudit agent</div>
        <div className="muted">
          Chat with the on-chain agent to list, analyze, and submit bounties.
        </div>
        {isRunning && <div className="shimmer" />}
      </div>

      <div className="card chat-card">
        <div className="section-title">Agent chat</div>
        <div className="muted" style={{ marginBottom: 12 }}>
          Talk to the on-chain agent to list, analyze, pin, and submit bounties.
        </div>
        <div className="chat-shell">
          <div className="chat-log">
            {chatMessages.length ? (
              chatMessages.map((msg) => (
                <div key={msg.id} className={`chat-message ${msg.role}`}>
                  <div className="chat-role">{msg.role}</div>
                  {msg.role === "assistant" ? (
                    (() => {
                      const parsed = parseJsonMessage(msg.content);
                      if (parsed) {
                        return (
                          <div className="chat-content chat-json">
                            <div className="chat-json-title">Structured result</div>
                            <div className="json-viewer">{renderJson(parsed)}</div>
                          </div>
                        );
                      }
                      return (
                        <div className="chat-content markdown">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                        </div>
                      );
                    })()
                  ) : (
                    <div className="chat-content">{msg.content}</div>
                  )}
                </div>
              ))
            ) : (
              <div className="chat-empty">
                <div className="muted">No messages yet.</div>
                <div className="chat-hints">
                  <span>Try:</span>
                  <code>list_bounties limit=5</code>
                  <code>analyze_bounty bounty_id=1</code>
                  <code>pin_submission submission_path=submission.json</code>
                </div>
              </div>
            )}
            {chatLoading && (
              <div className="chat-message assistant chat-loading">
                <div className="chat-role">assistant</div>
                <div className="chat-content">
                  <span className="typing">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </span>
                  <span className="typing-label">Thinking…</span>
                  {chatEvents.length > 0 && (
                    <div className="chat-status">
                      <span className={`progress-dot ${chatEvents[chatEvents.length - 1].status}`} />
                      <span className="muted">
                        {chatEvents[chatEvents.length - 1].step} · {chatEvents[chatEvents.length - 1].status}
                        {chatEvents[chatEvents.length - 1].message
                          ? ` · ${chatEvents[chatEvents.length - 1].message}`
                          : ""}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
          <div className="chat-input-row">
            <textarea
              placeholder="Message the agent... (Enter to send, Shift+Enter for newline)"
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              onKeyDown={handleChatKey}
              rows={2}
            />
            <button onClick={handleChatSend} disabled={chatLoading || !chatInput.trim()}>
              {chatLoading ? "Sending..." : "Send"}
            </button>
          </div>
          {chatError && <div className="chat-error">{chatError}</div>}
          {chatHint && <div className="chat-hint">{chatHint}</div>}
          {chatSessionId && (
            <div className="chat-meta muted">
              Session: {chatSessionId}
              {chatMeta?.durationMs !== undefined && (
                <>
                  {" "}
                  · Last response: {(chatMeta.durationMs / 1000).toFixed(1)}s
                </>
              )}
              {chatMeta?.action && <> · Action: {chatMeta.action}</>}
            </div>
          )}
        </div>
      </div>

      {SHOW_NON_CHAT && (
        <>
          <div className="grid">
            <div className="card">
              <div className="section-title">Input</div>
              <div className="row">
                <div style={{ flex: 1 }}>
                  <label>Solidity File</label>
                  <div className="file-input">
                    <input
                      id="solidity-file"
                      type="file"
                      accept=".sol"
                      onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
                    />
                    <label htmlFor="solidity-file" className="file-button">
                      Choose file
                    </label>
                    <span className="file-name">{fileName || "No file selected"}</span>
                  </div>
                </div>
              </div>
              <div style={{ marginTop: 16 }}>
                <button onClick={handleSubmit} disabled={!file || isRunning}>
                  {isRunning ? "Running..." : "Run Agent"}
                </button>
              </div>
              <div className="badge-group" style={{ marginTop: 16 }}>
                <div className="badge">{useGraph ? "Graph: ON" : "Graph: OFF"}</div>
                <div className="badge">Max issues: {maxIssues}</div>
              </div>
              <details className="drawer">
                <summary className="summary">Advanced settings</summary>
                <div className="drawer-body">
                  <div className="row" style={{ marginTop: 12 }}>
                    <div style={{ flex: 1 }}>
                      <label>Tools</label>
                      <input
                        type="text"
                        value={tools}
                        onChange={(event) => setTools(event.target.value)}
                      />
                    </div>
                  </div>
                  <div className="row" style={{ marginTop: 12 }}>
                    <div style={{ flex: 1 }}>
                      <label>Max issues</label>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={maxIssues}
                        onChange={(event) => setMaxIssues(Number(event.target.value))}
                      />
                    </div>
                  </div>
                  <div className="row" style={{ marginTop: 12 }}>
                    <label>
                      <input
                        type="checkbox"
                        checked={useLlm}
                        onChange={(event) => setUseLlm(event.target.checked)}
                      />
                      <span style={{ marginLeft: 8 }}>LLM triage + logic review</span>
                    </label>
                  </div>
                  <div className="row">
                    <label>
                      <input
                        type="checkbox"
                        checked={useGraph}
                        onChange={(event) => setUseGraph(event.target.checked)}
                      />
                      <span style={{ marginLeft: 8 }}>LangGraph workflow</span>
                    </label>
                  </div>
                </div>
              </details>
              <div className="footer">
                {jobId ? `Job ${jobId}` : "Upload a Solidity file to start."}
              </div>
            </div>

            <div className="card">
              <div className="section-title">Live progress</div>
              <div className="muted" style={{ marginBottom: 12 }}>
                {latestEvent?.message ?? "Waiting for updates."} · Elapsed{" "}
                {formatDuration(elapsed)}
              </div>
              <div className="stepper">
                {steps.map((step) => (
                  <div className="stepper-item" key={step.key}>
                    <div className={`stepper-dot ${stepStatus(step.key)}`} />
                    <div>
                      <div className="stepper-label">{step.label}</div>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {stepStatus(step.key)} · {formatDuration(stepDuration(step.key))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <ul className="progress-list">
                {events.map((event, index) => (
                  <li key={`${event.step}-${event.timestamp}`} className="entered">
                    <div className="progress-step">
                      <span className={`progress-dot ${event.status}`} />
                      {event.status === "running" &&
                        event.step !== "queued" &&
                        !hasLaterTerminal(index, event.step) && (
                        <span className="spinner" />
                      )}
                      <div>
                        <strong>{event.step}</strong>
                        <div className="muted" style={{ fontSize: 13 }}>
                          {event.status}
                          {event.message ? ` · ${event.message}` : ""}
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="card">
            <div className="section-title">Top finding</div>
            {submissionTitle ? (
              <div className="top-finding">
                <div className="badge-group" style={{ marginBottom: 12 }}>
                  {submissionSeverity && (
                    <div className={`badge ${severityClass(submissionSeverity)}`}>
                      {submissionSeverity}
                    </div>
                  )}
                  {typeof submissionConfidence === "number" && (
                    <div className="badge">Confidence: {submissionConfidence.toFixed(2)}</div>
                  )}
                </div>
                <div className="top-title">{submissionTitle}</div>
                <div className="section-title" style={{ marginTop: 12 }}>
                  Impact
                </div>
                <MarkdownBlock value={submissionImpact} />
                <div className="section-title" style={{ marginTop: 12 }}>
                  Description
                </div>
                <MarkdownBlock value={submissionDescription} />
                <div className="section-title" style={{ marginTop: 12 }}>
                  Remediation
                </div>
                <MarkdownBlock value={submissionRemediation} />
                <div className="section-title" style={{ marginTop: 12 }}>
                  Repro
                </div>
                <MarkdownBlock value={submissionRepro} />
              </div>
            ) : (
              <div className="muted">No top finding yet.</div>
            )}
          </div>

          <div className="grid">
            <div className="card">
              <div className="section-title">Submission JSON</div>
            <div className="badge-group" style={{ marginBottom: 12 }}>
              {submissionSeverity && (
                <div className={`badge ${severityClass(submissionSeverity)}`}>
                  Severity: {submissionSeverity}
                </div>
              )}
              {typeof submissionConfidence === "number" && (
                <div className="badge">
                  Confidence: {submissionConfidence.toFixed(2)}
                </div>
              )}
            </div>
            {submission ? (
              <div className="json-viewer">{renderJson(submission as JsonValue)}</div>
            ) : (
              <div className="callout">
                <div className="callout-title">No submission yet</div>
                <div className="muted">
                  Run the agent to generate a structured security report.
                </div>
              </div>
            )}
            {error && (
              <>
                <div className="badge" style={{ marginTop: 12 }}>
                  Error
                </div>
                <pre>{error}</pre>
              </>
            )}
            </div>

            <div className="card">
              <div className="section-title">Artifacts</div>
              {artifacts.length ? (
                <div className="artifact-list">
                  {artifacts.map((name) => (
                    <button
                      key={name}
                      className="secondary"
                      onClick={() => downloadArtifact(name)}
                    >
                      Download {name}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="muted">Artifacts appear after a run completes.</div>
              )}
              <div className="section-title" style={{ marginTop: 18 }}>
                Run history
              </div>
              {history.length ? (
                <div className="history-list">
                  {history.map((run) => (
                    <div key={run.id} className="history-item">
                      <div>
                        <div className="history-title">{run.fileName}</div>
                        <div className="muted" style={{ fontSize: 12 }}>
                          {new Date(run.createdAt).toLocaleString()}
                        </div>
                      </div>
                      <div className="badge">{run.status}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="muted">No runs yet.</div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="section-title">Contract preview</div>
            {contractText ? (
              <div className="code-viewer">
                <div className="code-header">{fileName}</div>
                <div className="code-body">
                  {contractText.split("\n").map((line, index) => (
                    <div key={`${index}-${line}`} className="code-line">
                      <span className="code-line-number">{index + 1}</span>
                      <span className="code-line-text">{line || " "}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="muted">Upload a file to preview the contract.</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
