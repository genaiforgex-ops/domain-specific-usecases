import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Route, Routes, useSearchParams } from "react-router-dom";

import {
  AIAvatar,
  ChatInput,
  SuggestionChips,
  TypingDots,
  UserAvatar,
  groupByDate,
  useTypewriter,
} from "@/components/chat";
import { Icon } from "@/components/Icons";
import { Badge } from "@/components/ui/Badge";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import { classNames, formatDate } from "@/lib/utils";
import type { LegalBotQuery } from "@/types";


const SUGGESTIONS = [
  "What's the standard liability cap in vendor MSAs at JFPSL?",
  "Can we share customer data with a co-lending partner?",
  "What does RBI mandate in a Key Fact Statement (KFS)?",
  "FEMA applicability for cross-border vendor payments?",
];


export function LegalBotPage() {
  return (
    <Routes>
      <Route index element={<Chat />} />
    </Routes>
  );
}


const MSA_STARTER_QUESTIONS = [
  "What does the liability cap mean in simple terms?",
  "Can the vendor terminate without notice?",
  "Summarize the data protection section",
];

function Chat() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const msaContext = useMemo(() => {
    const trackerId = searchParams.get("msa");
    const versionId = searchParams.get("version");
    const label = searchParams.get("label");
    if (!trackerId) return null;
    return {
      context_tracker_id: Number(trackerId),
      context_version_id: versionId ? Number(versionId) : undefined,
      label: label || `MSA #${trackerId}`,
    };
  }, [searchParams]);
  const gmailThreadContext = useMemo(() => {
    const threadId = searchParams.get("gmail_thread");
    const label = searchParams.get("gmail_label");
    if (!threadId) return null;
    return {
      context_gmail_thread_id: threadId,
      label: label || `Gmail thread ${threadId.slice(0, 8)}…`,
    };
  }, [searchParams]);
  const [messages, setMessages] = useState<LegalBotQuery[]>([]);
  const [escalated, setEscalated] = useState<LegalBotQuery[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [optimisticUserMsg, setOptimisticUserMsg] = useState<string | null>(null);
  // Track which message ID is the freshly-generated one (animate typewriter only on this)
  const [streamingId, setStreamingId] = useState<number | null>(null);
  const [focusId, setFocusId] = useState<number | null>(null);
  const scrollEndRef = useRef<HTMLDivElement>(null);
  const focusRef = useRef<HTMLDivElement>(null);

  const canTriage = hasPermission(user, "approve_ai_output");

  const refresh = useCallback(async () => {
    const mine = await api.myQueries();
    // Backend returns newest first; chat needs oldest first.
    setMessages([...mine].reverse());
    if (canTriage) {
      try {
        setEscalated(await api.escalatedQueries());
      } catch {
        /* ignore */
      }
    }
  }, [canTriage]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto-scroll on new messages / typing
  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, optimisticUserMsg, busy]);

  // Smooth-scroll to a clicked history item
  useEffect(() => {
    if (focusId != null) {
      focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focusId]);

  async function send(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setOptimisticUserMsg(trimmed);
    setInput("");
    try {
      const result = await api.askBot(
        trimmed,
        msaContext
          ? {
              context_type: "msa_version",
              context_tracker_id: msaContext.context_tracker_id,
              context_version_id: msaContext.context_version_id,
            }
          : gmailThreadContext
            ? {
                context_type: "gmail_thread",
                context_gmail_thread_id: gmailThreadContext.context_gmail_thread_id,
              }
            : undefined,
      );
      // Make freshly-asked queries flow into the chat at the bottom
      setMessages((prev) => [...prev, result]);
      setStreamingId(result.id);
    } catch (err) {
      console.error(err);
    } finally {
      setOptimisticUserMsg(null);
      setBusy(false);
    }
  }

  return (
    <div className="-mx-8 -my-6 h-[calc(100vh-3rem)] flex bg-bg">
      {/* History sidebar */}
      <aside className="hidden md:flex w-72 flex-col border-r border-separator/40 bg-bg-secondary/70">
        <div className="p-3 border-b border-separator/40">
          <button
            onClick={() => {
              setFocusId(null);
              setInput("");
              scrollEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
            }}
            className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-bg border border-separator/40 hover:border-accent/30 hover:bg-accent/10 text-sm font-medium text-label-secondary transition-colors"
          >
            <Icon.Plus className="w-4 h-4" />
            New question
          </button>
        </div>

        {canTriage && escalated.length > 0 && (
          <details open className="border-b border-separator/40">
            <summary className="px-3 py-2 cursor-pointer flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-amber-700">
              <span className="inline-flex items-center gap-1.5">
                <span className="relative inline-flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-amber-500 opacity-75 animate-ping" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-600" />
                </span>
                Escalated · {escalated.length}
              </span>
              <Icon.ChevronDown className="w-3 h-3" />
            </summary>
            <ul className="pb-2">
              {escalated.slice(0, 5).map((q) => (
                <li key={q.id}>
                  <button
                    onClick={() => setFocusId(q.id)}
                    className="w-full text-left px-3 py-2 hover:bg-bg text-xs text-label-secondary truncate"
                    title={q.question}
                  >
                    {q.question}
                  </button>
                </li>
              ))}
            </ul>
          </details>
        )}

        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {messages.length === 0 ? (
            <div className="p-4 text-xs text-label-tertiary">No chat history yet.</div>
          ) : (
            groupByDate(messages).map((group) => (
              <div key={group.label}>
                <div className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-wider text-label-secondary font-semibold">
                  {group.label}
                </div>
                <ul>
                  {group.items
                    .slice()
                    .reverse()
                    .map((q) => (
                      <li key={q.id}>
                        <button
                          onClick={() => setFocusId(q.id)}
                          className={classNames(
                            "w-full text-left px-3 py-2 text-xs truncate transition-colors",
                            focusId === q.id
                              ? "bg-accent/10 text-accent border-l-2 border-accent"
                              : "text-label-secondary hover:bg-bg",
                          )}
                          title={q.question}
                        >
                          {q.question}
                        </button>
                      </li>
                    ))}
                </ul>
              </div>
            ))
          )}
        </div>

        <div className="p-3 border-t border-separator/40 text-[11px] text-label-secondary">
          <div className="flex items-center gap-1.5">
            <Icon.Shield className="w-3.5 h-3.5" />
            <span>Audit-logged · corpus-bounded</span>
          </div>
        </div>
      </aside>

      {/* Main chat */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="px-4 md:px-8 py-3 border-b border-separator/40 flex items-center justify-between bg-bg/80 backdrop-blur">
          <div className="flex items-center gap-3 min-w-0">
            <AIAvatar />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-label">LegalBot</div>
              <div className="text-[11px] text-label-secondary flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-success" />
                <span>Online · Tier-1 queries answered instantly · escalates Tier-2 to Legal</span>
              </div>
            </div>
          </div>
          <Badge className="bg-bg-secondary text-label-secondary border-separator/40 hidden md:inline-flex">
            knowledge base
          </Badge>
        </header>

        {msaContext && (
          <div className="px-4 md:px-8 py-2 bg-accent/5 border-b border-accent/20 text-sm text-label-secondary flex items-center gap-2">
            <Icon.Documents className="w-4 h-4 text-accent shrink-0" />
            <span>
              Answering about document: <strong className="text-label">{msaContext.label}</strong>
            </span>
          </div>
        )}

        {gmailThreadContext && (
          <div className="px-4 md:px-8 py-2 bg-blue-50 border-b border-blue-200 text-sm text-label-secondary flex items-center gap-2">
            <Icon.Mail className="w-4 h-4 text-blue-600 shrink-0" />
            <span>
              Answering about Gmail thread: <strong className="text-label">{gmailThreadContext.label}</strong>
            </span>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {messages.length === 0 && !optimisticUserMsg && !busy ? (
            <EmptyState
              onPick={(s) => send(s)}
              userName={user?.full_name || "there"}
              msaLabel={msaContext?.label}
            />
          ) : (
            <div className="max-w-3xl mx-auto px-4 md:px-8 py-6 space-y-6">
              {messages.map((q) => (
                <Exchange
                  key={q.id}
                  query={q}
                  userName={user?.full_name || "You"}
                  isStreaming={streamingId === q.id}
                  isFocused={focusId === q.id}
                  focusRef={focusId === q.id ? focusRef : undefined}
                  canTriage={canTriage}
                  onOverridden={refresh}
                />
              ))}
              {optimisticUserMsg && (
                <UserBubble text={optimisticUserMsg} userName={user?.full_name || "You"} />
              )}
              {busy && <AIPending />}
              <div ref={scrollEndRef} />
            </div>
          )}
        </div>

        <ChatInput
          value={input}
          onChange={setInput}
          onSubmit={() => send(input)}
          busy={busy}
          placeholder={
            msaContext
              ? "Ask about this contract in plain language…"
              : "Ask LegalBot anything about JFPSL legal positions, RBI/SEBI/IRDAI/DPDP rules…"
          }
          hint={
            msaContext ? (
              <>
                Answers cite this document version plus the JFPSL knowledge base. AI explanation
                only — not legal advice.
              </>
            ) : (
              <>
                LegalBot is corpus-bounded — answers cite seeded JFPSL knowledge base. For definitive
                legal advice, escalate to the Legal team.
              </>
            )
          }
        />
      </main>
    </div>
  );
}


function EmptyState({
  onPick,
  userName,
  msaLabel,
}: {
  onPick: (s: string) => void;
  userName: string;
  msaLabel?: string;
}) {
  const firstName = userName.split(" ")[0];
  const chips = msaLabel ? MSA_STARTER_QUESTIONS : SUGGESTIONS;
  return (
    <div className="max-w-3xl mx-auto px-4 md:px-8 py-12">
      <div className="text-center animate-slide-up">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent/15 text-accent mb-4">
          <Icon.Sparkles className="w-7 h-7" aria-hidden />
        </div>
        <h2 className="text-2xl font-semibold text-label">
          Hi {firstName}, how can I help today?
        </h2>
        <p className="text-sm text-label-secondary mt-1">
          {msaLabel
            ? `Ask plain-language questions about ${msaLabel}.`
            : "Ask any Tier-1 legal question. Answers come with citations and confidence scores."}
        </p>
      </div>
      <div className="mt-8 animate-slide-up" style={{ animationDelay: "120ms" }}>
        <div className="text-xs uppercase tracking-wider text-label-tertiary font-medium mb-3">
          Try a starter prompt
        </div>
        <SuggestionChips suggestions={chips} onPick={onPick} />
      </div>
    </div>
  );
}


function UserBubble({ text, userName }: { text: string; userName: string }) {
  return (
    <div className="flex gap-3 justify-end animate-fade-in">
      <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-accent text-white px-4 py-2.5 shadow-sm">
        <p className="text-sm whitespace-pre-wrap">{text}</p>
      </div>
      <UserAvatar name={userName} />
    </div>
  );
}


function AIPending() {
  return (
    <div className="flex gap-3 animate-fade-in">
      <AIAvatar />
      <div className="rounded-2xl rounded-tl-md bg-bg-secondary px-3 py-2">
        <TypingDots />
      </div>
    </div>
  );
}


function Exchange({
  query,
  userName,
  isStreaming,
  isFocused,
  focusRef,
  canTriage,
  onOverridden,
}: {
  query: LegalBotQuery;
  userName: string;
  isStreaming: boolean;
  isFocused: boolean;
  focusRef?: React.Ref<HTMLDivElement>;
  canTriage: boolean;
  onOverridden: () => void;
}) {
  return (
    <div ref={focusRef} className="space-y-4">
      <UserBubble text={query.question} userName={userName} />
      <AIBubble
        query={query}
        isStreaming={isStreaming}
        isFocused={isFocused}
        canTriage={canTriage}
        onOverridden={onOverridden}
      />
    </div>
  );
}


function AIBubble({
  query,
  isStreaming,
  isFocused,
  canTriage,
  onOverridden,
}: {
  query: LegalBotQuery;
  isStreaming: boolean;
  isFocused: boolean;
  canTriage: boolean;
  onOverridden: () => void;
}) {
  const text = query.legal_override || query.ai_answer || "";
  const visible = useTypewriter(text, 12, isStreaming);
  const [copied, setCopied] = useState(false);
  const [showOverride, setShowOverride] = useState(false);

  async function copyText() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <div
      className={classNames(
        "flex gap-3 group",
        isFocused && "ring-2 ring-accent/20 ring-offset-4 rounded-2xl",
      )}
    >
      <AIAvatar />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="rounded-2xl rounded-tl-md bg-bg-secondary border border-separator/30 px-4 py-3">
          <p className="text-sm text-label whitespace-pre-wrap leading-relaxed">
            {visible}
            {isStreaming && visible.length < text.length && (
              <span className="inline-block w-2 h-4 bg-label-tertiary ml-0.5 animate-pulse-soft align-middle" />
            )}
          </p>
          {query.legal_override && (
            <div className="mt-2 text-[10px] uppercase tracking-wider text-emerald-700 font-semibold inline-flex items-center gap-1">
              <Icon.Check className="w-3 h-3" />
              Legal override applied
            </div>
          )}
        </div>

        {/* Metadata row */}
        <div className="flex items-center gap-2 flex-wrap text-[11px]">
          <Badge
            className={
              query.tier === 1
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-amber-50 text-amber-700 border-warning/20"
            }
          >
            tier {query.tier}
          </Badge>
          <span className="text-label-secondary">
            confidence {Math.round(query.confidence * 100)}%
          </span>
          <span className="text-label-tertiary">·</span>
          <span className="font-mono text-label-tertiary">{query.model_version}</span>
          <span className="text-label-tertiary">·</span>
          <span className="text-label-tertiary">{formatDate(query.created_at)}</span>
        </div>

        {/* Citations */}
        {query.citations && query.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {query.citations.map((c, i) => {
              const ref = (c as { reference?: string }).reference || "source";
              const reg = (c as { regulator?: string }).regulator || "";
              return (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-bg border border-separator/40 text-[11px] text-label-secondary"
                >
                  <Icon.Documents className="w-2.5 h-2.5" />
                  {reg && <span className="font-semibold text-label-secondary">{reg}</span>}
                  <span>{ref}</span>
                </span>
              );
            })}
          </div>
        )}

        {/* Action row — visible on hover */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={copyText}
            className="inline-flex items-center gap-1 text-[11px] text-label-secondary hover:text-label px-2 py-1 rounded hover:bg-bg-secondary"
            title="Copy answer"
          >
            {copied ? <Icon.Check className="w-3 h-3" /> : <Icon.Copy className="w-3 h-3" />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
          <button
            className="inline-flex items-center gap-1 text-[11px] text-label-secondary hover:text-emerald-700 px-2 py-1 rounded hover:bg-bg-secondary"
            title="Helpful"
            aria-label="Mark as helpful"
          >
            <Icon.ThumbsUp className="w-3 h-3" />
          </button>
          <button
            className="inline-flex items-center gap-1 text-[11px] text-label-secondary hover:text-rose-700 px-2 py-1 rounded hover:bg-bg-secondary"
            title="Not helpful"
            aria-label="Mark as not helpful"
          >
            <Icon.ThumbsDown className="w-3 h-3" />
          </button>
          {canTriage && !query.legal_override && (
            <button
              onClick={() => setShowOverride((s) => !s)}
              className="inline-flex items-center gap-1 text-[11px] text-label-secondary hover:text-accent px-2 py-1 rounded hover:bg-bg-secondary ml-auto"
              title="Provide a Legal override"
            >
              <Icon.Pencil className="w-3 h-3" />
              <span>Override</span>
            </button>
          )}
        </div>

        {showOverride && (
          <OverrideForm
            queryId={query.id}
            onDone={() => {
              setShowOverride(false);
              onOverridden();
            }}
          />
        )}

        <p className="text-[10px] text-label-tertiary italic">{query.disclaimer}</p>
      </div>
    </div>
  );
}


function OverrideForm({ queryId, onDone }: { queryId: number; onDone: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      await api.overrideQuery(queryId, text.trim());
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-accent/30 bg-accent/10 p-3 animate-slide-up space-y-2">
      <div className="text-xs font-semibold text-accent">Legal override</div>
      <textarea
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Provide the corrected legal answer. The AI draft and your correction are both logged."
        className="block w-full text-sm rounded border border-separator/40 px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
      />
      <div className="flex justify-end gap-2">
        <button
          onClick={onDone}
          className="text-xs px-3 py-1.5 rounded text-label-secondary hover:bg-bg"
        >
          Cancel
        </button>
        <button
          onClick={submit}
          disabled={busy || !text.trim()}
          className="text-xs px-3 py-1.5 rounded bg-accent text-white hover:bg-accent disabled:opacity-50"
        >
          {busy ? "Submitting…" : "Submit override"}
        </button>
      </div>
    </div>
  );
}
