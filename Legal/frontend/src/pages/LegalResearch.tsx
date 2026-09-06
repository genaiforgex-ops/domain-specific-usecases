import { useCallback, useEffect, useRef, useState } from "react";
import { Route, Routes } from "react-router-dom";

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
import type { ResearchNote, ResearchSummary } from "@/types";


const SUGGESTIONS = [
  "Co-lending governance requirements under RBI guidelines",
  "DPDP Act consent framework for fintech onboarding flows",
  "KYC refresh obligations under PMLA Master Directions",
  "SEBI rules for advising on mutual fund distribution",
];


export function LegalResearchPage() {
  return (
    <Routes>
      <Route index element={<Research />} />
    </Routes>
  );
}


function Research() {
  const { user } = useAuth();
  const [summaries, setSummaries] = useState<ResearchSummary[]>([]);
  const [notes, setNotes] = useState<ResearchNote[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [optimistic, setOptimistic] = useState<string | null>(null);
  const [streamingId, setStreamingId] = useState<number | null>(null);
  const [focusId, setFocusId] = useState<number | null>(null);
  const scrollEndRef = useRef<HTMLDivElement>(null);
  const focusRef = useRef<HTMLDivElement>(null);

  const canApprove = hasPermission(user, "approve_ai_output");

  const refresh = useCallback(async () => {
    const list = await api.listResearch();
    // newest first → reverse for chat
    const sorted = [...list].reverse();
    setSummaries(sorted);
    // Load full notes for the chat thread (limit to last 20 for perf)
    const fulls = await Promise.all(
      sorted.slice(-20).map((s) => api.getResearch(s.id).catch(() => null)),
    );
    setNotes(fulls.filter((n): n is ResearchNote => n !== null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [notes.length, optimistic, busy]);

  useEffect(() => {
    if (focusId != null) {
      focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focusId]);

  async function send(query: string) {
    const trimmed = query.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setOptimistic(trimmed);
    setInput("");
    try {
      const note = await api.createResearch(trimmed);
      setNotes((prev) => [...prev, note]);
      setStreamingId(note.id);
      refresh();
    } finally {
      setOptimistic(null);
      setBusy(false);
    }
  }

  async function finalize(noteId: number) {
    await api.updateResearch(noteId, { status: "finalized" });
    refresh();
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
            New research
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {summaries.length === 0 ? (
            <div className="p-4 text-xs text-label-tertiary">No research yet.</div>
          ) : (
            groupByDate(summaries).map((group) => (
              <div key={group.label}>
                <div className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-wider text-label-secondary font-semibold">
                  {group.label}
                </div>
                <ul>
                  {group.items
                    .slice()
                    .reverse()
                    .map((s) => (
                      <li key={s.id}>
                        <button
                          onClick={() => setFocusId(s.id)}
                          className={classNames(
                            "w-full text-left px-3 py-2 text-xs transition-colors",
                            focusId === s.id
                              ? "bg-amber-50 text-amber-900 border-l-2 border-amber-600"
                              : "text-label-secondary hover:bg-bg",
                          )}
                          title={s.query}
                        >
                          <div className="truncate">{s.query}</div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <Badge
                              className={
                                s.status === "finalized"
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200 text-[9px]"
                                  : "bg-bg-secondary text-label-secondary border-separator/40 text-[9px]"
                              }
                            >
                              {s.status}
                            </Badge>
                            <span className="text-[10px] text-label-tertiary">
                              {Math.round(s.confidence * 100)}%
                            </span>
                          </div>
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
            <span>RAG over JFPSL corpus · audit-logged</span>
          </div>
        </div>
      </aside>

      {/* Main chat */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="px-4 md:px-8 py-3 border-b border-separator/40 flex items-center justify-between bg-bg/80 backdrop-blur">
          <div className="flex items-center gap-3 min-w-0">
            <AIAvatar />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-label">Legal Research</div>
              <div className="text-[11px] text-label-secondary flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-success" />
                <span>RAG over RBI · SEBI · IRDAI · DPDP · PMLA · Companies Act · FEMA</span>
              </div>
            </div>
          </div>
          <Badge className="bg-amber-50 text-amber-700 border-warning/20 hidden md:inline-flex">
            corpus-bounded
          </Badge>
        </header>

        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {notes.length === 0 && !optimistic && !busy ? (
            <EmptyState onPick={(s) => send(s)} userName={user?.full_name || "there"} />
          ) : (
            <div className="max-w-4xl mx-auto px-4 md:px-8 py-6 space-y-6">
              {notes.map((n) => (
                <ResearchExchange
                  key={n.id}
                  note={n}
                  userName={user?.full_name || "You"}
                  isStreaming={streamingId === n.id}
                  isFocused={focusId === n.id}
                  focusRef={focusId === n.id ? focusRef : undefined}
                  canApprove={canApprove}
                  onFinalize={() => finalize(n.id)}
                />
              ))}
              {optimistic && <UserBubble text={optimistic} userName={user?.full_name || "You"} />}
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
          placeholder="Research any regulatory question — RAG over RBI / SEBI / IRDAI / DPDP / PMLA…"
          hint={
            <>
              Research is grounded in the indexed JFPSL corpus only. Citations are real document
              references; hallucination guard blocks invented sources.
            </>
          }
        />
      </main>
    </div>
  );
}


function EmptyState({ onPick, userName }: { onPick: (s: string) => void; userName: string }) {
  const firstName = userName.split(" ")[0];
  return (
    <div className="max-w-3xl mx-auto px-4 md:px-8 py-12">
      <div className="text-center animate-slide-up">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent/15 text-accent mb-4">
          <Icon.Research className="w-7 h-7" aria-hidden />
        </div>
        <h2 className="text-2xl font-semibold text-label">
          Hi {firstName}, what should we research?
        </h2>
        <p className="text-sm text-label-secondary mt-1">
          I'll search the JFPSL regulatory corpus and draft a structured research note.
        </p>
      </div>
      <div className="mt-8 animate-slide-up" style={{ animationDelay: "120ms" }}>
        <div className="text-xs uppercase tracking-wider text-label-tertiary font-medium mb-3">
          Try a research topic
        </div>
        <SuggestionChips suggestions={SUGGESTIONS} onPick={onPick} />
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


function ResearchExchange({
  note,
  userName,
  isStreaming,
  isFocused,
  focusRef,
  canApprove,
  onFinalize,
}: {
  note: ResearchNote;
  userName: string;
  isStreaming: boolean;
  isFocused: boolean;
  focusRef?: React.Ref<HTMLDivElement>;
  canApprove: boolean;
  onFinalize: () => void;
}) {
  return (
    <div ref={focusRef} className="space-y-4">
      <UserBubble text={note.query} userName={userName} />
      <ResearchCard
        note={note}
        isStreaming={isStreaming}
        isFocused={isFocused}
        canApprove={canApprove}
        onFinalize={onFinalize}
      />
    </div>
  );
}


function ResearchCard({
  note,
  isStreaming,
  isFocused,
  canApprove,
  onFinalize,
}: {
  note: ResearchNote;
  isStreaming: boolean;
  isFocused: boolean;
  canApprove: boolean;
  onFinalize: () => void;
}) {
  const summaryShown = useTypewriter(note.summary, 10, isStreaming);
  const [copied, setCopied] = useState(false);
  const [showRegulations, setShowRegulations] = useState(true);
  const [showProvisions, setShowProvisions] = useState(true);

  async function copyAll() {
    const text = [
      `Research: ${note.query}`,
      "",
      "Summary:",
      note.summary,
      "",
      "Implications for JFPSL:",
      note.implications,
      "",
      "Recommended next steps:",
      ...note.recommended_next_steps.map((s, i) => `  ${i + 1}. ${s}`),
      "",
      "Citations:",
      ...note.citations.map(
        (c) =>
          `  · ${(c as { regulator: string }).regulator}: ${(c as { reference: string }).reference}`,
      ),
    ].join("\n");
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
        isFocused && "ring-2 ring-amber-200 ring-offset-4 rounded-2xl",
      )}
    >
      <AIAvatar />
      <div className="min-w-0 flex-1">
        <div className="rounded-2xl rounded-tl-md bg-bg-secondary border border-separator/30 overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-separator/30 flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge
                className={
                  note.status === "finalized"
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                    : "bg-bg-secondary text-label-secondary border-separator/40"
                }
              >
                {note.status}
              </Badge>
              <span className="text-[11px] text-label-secondary">
                confidence {Math.round(note.confidence * 100)}%
              </span>
              <span className="text-label-tertiary text-[11px]">·</span>
              <span className="text-[10px] font-mono text-label-tertiary">{note.model_version}</span>
            </div>
            <span className="text-[11px] text-label-tertiary">{formatDate(note.created_at)}</span>
          </div>

          {/* Summary */}
          <div className="px-4 py-3">
            <Section title="Summary" icon={<Icon.Sparkles className="w-3.5 h-3.5" />}>
              <p className="text-sm text-label leading-relaxed whitespace-pre-wrap">
                {summaryShown}
                {isStreaming && summaryShown.length < note.summary.length && (
                  <span className="inline-block w-2 h-4 bg-label-tertiary ml-0.5 animate-pulse-soft align-middle" />
                )}
              </p>
            </Section>
          </div>

          {/* Applicable regulations */}
          {note.applicable_regulations.length > 0 && (
            <CollapsibleSection
              title="Applicable regulations"
              icon={<Icon.Shield className="w-3.5 h-3.5" />}
              count={note.applicable_regulations.length}
              open={showRegulations}
              onToggle={() => setShowRegulations((o) => !o)}
            >
              <ul className="space-y-1.5">
                {note.applicable_regulations.map((r, i) => (
                  <li key={i} className="text-sm text-label-secondary flex items-start gap-2">
                    <Badge className="bg-amber-50 text-amber-700 border-warning/20 shrink-0">
                      {(r as { regulator: string }).regulator}
                    </Badge>
                    <span>{(r as { reference: string }).reference}</span>
                  </li>
                ))}
              </ul>
            </CollapsibleSection>
          )}

          {/* Key provisions */}
          {note.key_provisions.length > 0 && (
            <CollapsibleSection
              title="Key provisions"
              icon={<Icon.Documents className="w-3.5 h-3.5" />}
              count={note.key_provisions.length}
              open={showProvisions}
              onToggle={() => setShowProvisions((o) => !o)}
            >
              <ul className="space-y-2">
                {note.key_provisions.map((p, i) => (
                  <li
                    key={i}
                    className="rounded-lg bg-bg border border-separator/30 px-3 py-2 text-sm"
                  >
                    <div className="text-[11px] font-semibold text-label-secondary mb-1">
                      {(p as { reference: string }).reference}
                    </div>
                    <div className="text-label-secondary leading-relaxed">
                      {(p as { excerpt: string }).excerpt}
                    </div>
                  </li>
                ))}
              </ul>
            </CollapsibleSection>
          )}

          {/* Implications */}
          <div className="px-4 py-3 border-t border-separator/30">
            <Section
              title="Implications for JFPSL"
              icon={<Icon.Bolt className="w-3.5 h-3.5" />}
            >
              <p className="text-sm text-label leading-relaxed bg-amber-50/50 border border-amber-100 rounded-lg px-3 py-2">
                {note.implications}
              </p>
            </Section>
          </div>

          {/* Next steps */}
          {note.recommended_next_steps.length > 0 && (
            <div className="px-4 py-3 border-t border-separator/30">
              <Section
                title="Recommended next steps"
                icon={<Icon.ArrowRight className="w-3.5 h-3.5" />}
              >
                <ol className="space-y-1.5">
                  {note.recommended_next_steps.map((s, i) => (
                    <li key={i} className="text-sm text-label-secondary flex items-start gap-2">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-semibold flex items-center justify-center">
                        {i + 1}
                      </span>
                      <span>{s}</span>
                    </li>
                  ))}
                </ol>
              </Section>
            </div>
          )}

          {/* Citations */}
          {note.citations.length > 0 && (
            <div className="px-4 py-3 border-t border-separator/30 bg-bg-secondary">
              <div className="text-[10px] uppercase tracking-wider text-label-secondary font-semibold mb-1.5">
                Citations
              </div>
              <div className="flex flex-wrap gap-1.5">
                {note.citations.map((c, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-bg border border-separator/40 text-[11px] text-label-secondary"
                  >
                    <Icon.Documents className="w-2.5 h-2.5" />
                    <span className="font-semibold text-label-secondary">
                      {(c as { regulator: string }).regulator}
                    </span>
                    <span>{(c as { reference: string }).reference}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Reviewer notes */}
          {note.reviewer_notes && (
            <div className="px-4 py-3 border-t border-separator/30 bg-emerald-50/40">
              <div className="text-[10px] uppercase tracking-wider text-emerald-700 font-semibold mb-1">
                Reviewer notes
              </div>
              <p className="text-sm text-label whitespace-pre-wrap">{note.reviewer_notes}</p>
            </div>
          )}
        </div>

        {/* Action row */}
        <div className="mt-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={copyAll}
            className="inline-flex items-center gap-1 text-[11px] text-label-secondary hover:text-label px-2 py-1 rounded hover:bg-bg-secondary"
            title="Copy note"
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
          {canApprove && note.status !== "finalized" && (
            <button
              onClick={onFinalize}
              className="ml-auto inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 hover:text-emerald-800 px-2 py-1 rounded hover:bg-emerald-50"
              title="Mark as finalized"
              aria-label="Mark research note as finalized"
            >
              <Icon.Check className="w-3 h-3" />
              <span>Finalize</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-label-secondary font-semibold mb-2">
        {icon}
        <span>{title}</span>
      </div>
      {children}
    </div>
  );
}


function CollapsibleSection({
  title,
  icon,
  count,
  open,
  onToggle,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  count: number;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="px-4 py-3 border-t border-separator/30">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between mb-2 group"
      >
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-label-secondary font-semibold group-hover:text-label-secondary">
          {icon}
          <span>{title}</span>
          <span className="text-label-tertiary">· {count}</span>
        </div>
        <Icon.ChevronDown
          className={classNames(
            "w-3.5 h-3.5 text-label-tertiary transition-transform",
            !open && "-rotate-90",
          )}
        />
      </button>
      {open && <div className="animate-fade-in">{children}</div>}
    </div>
  );
}
