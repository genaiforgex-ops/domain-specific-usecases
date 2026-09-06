import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { Markdown, citationLabel, fullCitation } from "@/components/Markdown";
import {
  DocumentViewer,
  type DocumentViewerHandle,
} from "@/components/DocumentViewer";
import { LawGenieMark, Icon } from "@/components/Icons";
import { api, ApiError, streamChat } from "@/lib/api";
import type {
  ChatAttachment,
  ChatContextRef,
  ChatSessionSummary,
  ChatShareEntry,
  ChatShareUser,
  ChatSource,
  ChatThought,
  TemplateLibraryItem,
  TemplateLibraryPreview,
} from "@/types";
import { useAuth } from "@/contexts/AuthContext";

type Mode = "review" | "research" | "draft";

interface Message {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  blocked?: boolean;
  sources?: ChatSource[];
  thoughts?: ChatThought[];
  turnId?: number | null;
  feedback?: "up" | "down" | null;
  feedbackComment?: string | null;
  mode?: Mode | null;
  createdAt?: string | null;
  fileLabels?: string[];
}

const MODES: { id: Mode; label: string; blurb: string }[] = [
  { id: "review", label: "Review", blurb: "Query your documents" },
  {
    id: "research",
    label: "Research",
    blurb:
      "Conversational research with citations (for structured Research Notes use Legal Research)",
  },
  { id: "draft", label: "Draft", blurb: "Draft from JFPSL templates" },
];

const STARTER_PROMPTS = [
  "Summarize the key obligations in this MSA",
  "What liability caps are typical for SaaS vendors?",
  "Draft an NDA mutual confidentiality clause",
];

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function modeLabel(mode: Mode | null | undefined): string {
  if (mode === "research") return "Research";
  if (mode === "draft") return "Draft";
  if (mode === "review") return "Review";
  return "";
}

function fileLabelsFromThoughts(thoughts: ChatThought[] | undefined): string[] {
  if (!thoughts?.length) return [];
  const labels: string[] = [];
  const seen = new Set<string>();
  for (const t of thoughts) {
    if (t.kind !== "documents") continue;
    for (const item of t.items ?? []) {
      const title = (item.title || "").trim();
      if (!title || seen.has(title)) continue;
      seen.add(title);
      labels.push(title);
    }
  }
  return labels;
}

export function LawGenieChatPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [shared, setShared] = useState<ChatSessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [readOnly, setReadOnly] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [uploadingName, setUploadingName] = useState<string | null>(null);
  const [analysingDocs, setAnalysingDocs] = useState(false);
  const [seededContext, setSeededContext] = useState<ChatContextRef[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("review");
  const [modeOpen, setModeOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  // Detailed feedback dialog (opened from the help button)
  const [feedbackModalTurnId, setFeedbackModalTurnId] = useState<number | null>(null);
  const [feedbackText, setFeedbackText] = useState("");

  // Share dialog
  const [shareOpen, setShareOpen] = useState(false);
  const [shareUsers, setShareUsers] = useState<ChatShareUser[]>([]);
  const [shareExisting, setShareExisting] = useState<ChatShareEntry[]>([]);
  const [shareSelected, setShareSelected] = useState<Set<number>>(new Set());
  const [shareFilter, setShareFilter] = useState("");
  const [shareMsg, setShareMsg] = useState<string | null>(null);

  // Draft template picker
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templateItems, setTemplateItems] = useState<TemplateLibraryItem[]>([]);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateFilter, setTemplateFilter] = useState("");
  const [attachingTemplate, setAttachingTemplate] = useState(false);

  // Right-pane JFPSL document viewer (PDF/DOCX via DocumentViewer)
  const [paneSource, setPaneSource] = useState<ChatSource | null>(null);
  const [panePreview, setPanePreview] = useState<TemplateLibraryPreview | null>(null);
  const [paneLoading, setPaneLoading] = useState(false);
  const [paneError, setPaneError] = useState<string | null>(null);
  const [paneJump, setPaneJump] = useState<{
    page?: number;
    snippet?: string;
    token?: number;
  } | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const viewerRef = useRef<DocumentViewerHandle>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const listeningRef = useRef(false);
  const sttRestartedRef = useRef(false);
  const [listening, setListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const sttSupported = useMemo(() => getSpeechRecognitionCtor() != null, []);

  const firstName = useMemo(() => (user?.full_name || "there").split(" ")[0], [user]);
  const activeMode = MODES.find((m) => m.id === mode)!;
  const activeTitle = activeSession
    ? [...sessions, ...shared].find((s) => s.session_id === activeSession)?.title ?? "Chat"
    : "New Chat Session";

  async function refreshSessions() {
    try {
      const [own, sh] = await Promise.all([api.listChatSessions(), api.listSharedChats()]);
      setSessions(own);
      setShared(sh);
    } catch {
      /* non-fatal for the sidebar */
    }
  }

  useEffect(() => {
    void refreshSessions();
  }, []);

  // Deep-link context handoff (from MSA Automation etc.)
  useEffect(() => {
    const refs: ChatContextRef[] = [];
    const msa = searchParams.get("msa");
    if (msa) {
      refs.push({
        kind: "msa_version",
        tracker_id: Number(msa),
        version_id: searchParams.get("version") ? Number(searchParams.get("version")) : undefined,
        label: searchParams.get("label") || `MSA #${msa}`,
      });
    }
    const thread = searchParams.get("gmail_thread");
    if (thread) {
      refs.push({
        kind: "gmail_thread",
        gmail_thread_id: thread,
        label: searchParams.get("gmail_label") || "Email thread",
      });
    }
    if (refs.length) {
      startNewSession();
      setSeededContext(refs);
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  function startNewSession() {
    abortRef.current?.abort();
    stopDictation();
    setActiveSession(null);
    setReadOnly(false);
    setMessages([]);
    setAttachments([]);
    setSeededContext([]);
    setThinking(null);
    setError(null);
    setBusy(false);
    setAnalysingDocs(false);
  }

  function stopGeneration() {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setThinking(null);
    setAnalysingDocs(false);
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant" && last.streaming) {
        last.streaming = false;
        if (!last.text.trim()) {
          last.text = "Response stopped.";
        }
      }
      return next;
    });
  }

  function stopDictation() {
    listeningRef.current = false;
    sttRestartedRef.current = false;
    const rec = recognitionRef.current;
    if (rec) {
      try {
        rec.onresult = null;
        rec.onerror = null;
        rec.onend = null;
        rec.stop();
      } catch {
        /* already stopped */
      }
      recognitionRef.current = null;
    }
    setListening(false);
    setInterimTranscript("");
  }

  function toggleDictation() {
    if (readOnly || busy) return;
    if (listening) {
      stopDictation();
      return;
    }
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      setError("Speech-to-text needs Chrome, Edge, or Safari with microphone access.");
      return;
    }
    setError(null);
    setInterimTranscript("");
    sttRestartedRef.current = false;
    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-IN";
    recognitionRef.current = recognition;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalChunk = "";
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const piece = result[0]?.transcript ?? "";
        if (result.isFinal) {
          finalChunk += piece;
        } else {
          interim += piece;
        }
      }
      setInterimTranscript(interim.trim());
      const spoken = finalChunk.trim();
      if (!spoken) return;
      setInput((prev) => {
        const base = prev.trimEnd();
        return base ? `${base} ${spoken}` : spoken;
      });
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === "aborted" || event.error === "no-speech") {
        // Keep listening flag; onend may restart once.
        return;
      }
      listeningRef.current = false;
      setListening(false);
      setInterimTranscript("");
      recognitionRef.current = null;
      if (event.error === "not-allowed") {
        setError("Microphone permission denied. Allow mic access in the browser and try again.");
      } else {
        setError(`Microphone error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      // Some browsers end after a pause even with continuous=true.
      // If the user still wants listening, restart recognition once.
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
      if (listeningRef.current && !sttRestartedRef.current) {
        sttRestartedRef.current = true;
        const Next = getSpeechRecognitionCtor();
        if (!Next) {
          listeningRef.current = false;
          setListening(false);
          setInterimTranscript("");
          return;
        }
        try {
          const again = new Next();
          again.continuous = true;
          again.interimResults = true;
          again.lang = navigator.language || "en-IN";
          again.onresult = recognition.onresult;
          again.onerror = recognition.onerror;
          again.onend = recognition.onend;
          recognitionRef.current = again;
          again.start();
          return;
        } catch {
          /* fall through to stop */
        }
      }
      listeningRef.current = false;
      setListening(false);
      setInterimTranscript("");
    };

    try {
      recognition.start();
      listeningRef.current = true;
      setListening(true);
    } catch {
      listeningRef.current = false;
      setListening(false);
      recognitionRef.current = null;
      setError("Could not start the microphone. Check browser permissions.");
    }
  }

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      stopDictation();
    };
  }, []);

  useEffect(() => {
    if (!busy) return;
    stopDictation();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        stopGeneration();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy]);

  async function openSession(sessionId: string, ro: boolean) {
    abortRef.current?.abort();
    stopDictation();
    setBusy(false);
    setAnalysingDocs(false);
    setActiveSession(sessionId);
    setReadOnly(ro);
    setAttachments([]);
    setSeededContext([]);
    setThinking(null);
    setError(null);
    try {
      const history = await api.getChatHistory(sessionId);
      const mapped: Message[] = history.map((t) => ({
        role: t.role,
        text: t.text,
        sources: t.sources ?? [],
        thoughts: t.thoughts ?? [],
        turnId: t.turn_id ?? null,
        feedback: t.feedback ?? null,
        feedbackComment: t.feedback_comment ?? null,
        mode: t.mode ?? null,
        createdAt: t.created_at,
        fileLabels: fileLabelsFromThoughts(t.thoughts),
      }));
      setMessages(mapped);
      const lastMode = [...mapped]
        .reverse()
        .find((m) => m.role === "assistant" && m.mode)?.mode;
      if (lastMode) setMode(lastMode);
    } catch {
      setMessages([]);
    }
  }

  async function clearSession() {
    if (!activeSession) {
      startNewSession();
      return;
    }
    if (!window.confirm("Delete this chat permanently? This cannot be undone.")) return;
    try {
      await api.deleteChat(activeSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete chat");
      return;
    }
    startNewSession();
    void refreshSessions();
  }

  function downloadChat() {
    if (!activeSession) return;
    window.open(api.chatExportUrl(activeSession), "_blank");
  }

  /** Thumbs up/down — store like/dislike only (no dialog). */
  function rate(turnId: number, value: "up" | "down", current: "up" | "down" | null) {
    const nextValue: "up" | "down" | null = current === value ? null : value;
    setMessages((prev) =>
      prev.map((m) =>
        m.turnId === turnId
          ? {
              ...m,
              feedback: nextValue,
              feedbackComment: nextValue == null ? null : m.feedbackComment,
            }
          : m,
      ),
    );
    void api.submitChatFeedback(turnId, { value: nextValue }).catch(() => {
      setMessages((prev) =>
        prev.map((m) => (m.turnId === turnId ? { ...m, feedback: current } : m)),
      );
    });
  }

  /** Help button — open detailed feedback dialog. */
  function openDetailedFeedback(turnId: number) {
    const existing = messages.find((m) => m.turnId === turnId);
    setFeedbackText(existing?.feedbackComment ?? "");
    setFeedbackModalTurnId(turnId);
  }

  async function submitDetailedFeedback() {
    if (feedbackModalTurnId == null) return;
    const turnId = feedbackModalTurnId;
    const comment = feedbackText.trim();
    setMessages((prev) =>
      prev.map((m) =>
        m.turnId === turnId ? { ...m, feedbackComment: comment || null } : m,
      ),
    );
    setFeedbackModalTurnId(null);
    setFeedbackText("");
    try {
      await api.submitChatFeedback(turnId, { comment });
    } catch {
      /* keep optimistic state; a later reload reflects the server */
    }
  }

  async function openShare() {
    setShareMsg(null);
    setShareSelected(new Set());
    setShareFilter("");
    setShareExisting([]);
    setShareOpen(true);
    try {
      const [users, existing] = await Promise.all([
        api.listShareableUsers(),
        activeSession
          ? api.listChatShares(activeSession).catch(() => [] as ChatShareEntry[])
          : Promise.resolve([] as ChatShareEntry[]),
      ]);
      setShareUsers(users);
      setShareExisting(existing);
    } catch {
      setShareUsers([]);
      setShareExisting([]);
    }
  }

  function toggleShareUser(id: number) {
    setShareSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function submitShare() {
    if (!activeSession || shareSelected.size === 0) return;
    const emails = shareUsers.filter((u) => shareSelected.has(u.id)).map((u) => u.email);
    try {
      const res = await api.shareChat(activeSession, emails);
      setShareMsg(
        res.shared_with.length ? `Shared with ${res.shared_with.length} user(s).` : "Nothing to share.",
      );
      setShareSelected(new Set());
      try {
        setShareExisting(await api.listChatShares(activeSession));
      } catch {
        /* keep prior list */
      }
      void refreshSessions();
    } catch (err) {
      setShareMsg(err instanceof Error ? err.message : "Share failed");
    }
  }

  async function revokeShare(userId: number) {
    if (!activeSession) return;
    try {
      await api.revokeChatShare(activeSession, userId);
      setShareExisting((prev) => prev.filter((s) => s.user_id !== userId));
      setShareMsg("Share revoked.");
      void refreshSessions();
    } catch (err) {
      setShareMsg(err instanceof Error ? err.message : "Could not revoke share");
    }
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    setError(null);
    for (const file of files) {
      setUploadingName(file.name);
      try {
        const att = await api.uploadChatAttachment(file);
        setAttachments((prev) => [...prev, att]);
      } catch (err) {
        setError(err instanceof Error ? err.message : `Upload failed: ${file.name}`);
        break;
      }
    }
    setUploadingName(null);
  }

  async function openTemplatePicker() {
    if (readOnly || busy || attachingTemplate) return;
    setTemplateOpen(true);
    setTemplateFilter("");
    setTemplateLoading(true);
    setError(null);
    try {
      let items: TemplateLibraryItem[];
      try {
        items = await api.listTemplateLibrary({ doc_kind: "template" });
      } catch (err) {
        if (err instanceof ApiError && err.status === 403) {
          items = await api.listChatTemplates();
        } else {
          throw err;
        }
      }
      setTemplateItems(items);
    } catch (err) {
      setTemplateItems([]);
      setError(err instanceof Error ? err.message : "Could not load templates");
      setTemplateOpen(false);
    } finally {
      setTemplateLoading(false);
    }
  }

  async function pickTemplate(item: TemplateLibraryItem) {
    setAttachingTemplate(true);
    setError(null);
    try {
      const att = await api.attachChatTemplate(item.storage_key);
      setAttachments((prev) => [
        ...prev,
        { ...att, filename: att.filename || item.name || item.filename },
      ]);
      setTemplateOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not attach template");
    } finally {
      setAttachingTemplate(false);
    }
  }

  async function send(overrideText?: string) {
    const text = (overrideText ?? input).trim();
    if (!text || busy || readOnly) return;

    const context: ChatContextRef[] = [
      ...seededContext,
      ...attachments.map((a) => ({
        kind: "attachment" as const,
        attachment_id: a.attachment_id,
        label: a.filename,
      })),
    ];

    setInput("");
    setError(null);
    setBusy(true);
    setAnalysingDocs(context.some((c) => c.kind === "attachment"));
    setThinking(context.some((c) => c.kind === "attachment") ? "Analysing document…" : "Thinking…");
    const fileLabels = context
      .map((c) => (c.label || "").trim())
      .filter(Boolean);
    const startedAt = new Date().toISOString();
    setMessages((prev) => [
      ...prev,
      { role: "user", text, createdAt: startedAt },
      {
        role: "assistant",
        text: "",
        streaming: true,
        thoughts: [],
        mode,
        createdAt: startedAt,
        fileLabels,
      },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    await streamChat(
      { text, session_id: activeSession, context, mode, generate_headline: !activeSession },
      {
        onThinking: (t) => setThinking(t),
        onThought: (thought) => {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              const existing = last.thoughts ?? [];
              if (existing.some((x) => x.id === thought.id)) return prev;
              last.thoughts = [...existing, thought];
            }
            return next;
          });
        },
        onPartial: (chunk, sid) => {
          if (sid && !activeSession) setActiveSession(sid);
          setThinking(null);
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") last.text += chunk;
            return next;
          });
        },
        onFinal: (full, sid, opts) => {
          if (sid && !activeSession) setActiveSession(sid);
          setThinking(null);
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              last.text = full;
              last.streaming = false;
              last.blocked = opts.blocked;
              last.sources = opts.sources ?? [];
              if (opts.thoughts?.length) last.thoughts = opts.thoughts;
              last.turnId = opts.turnId ?? null;
              last.mode = mode;
            }
            return next;
          });
        },
        onError: (msg) => {
          setThinking(null);
          setAnalysingDocs(false);
          setError(msg);
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant" && !last.text) next.pop();
            else if (last?.role === "assistant") last.streaming = false;
            return next;
          });
        },
      },
      controller.signal,
    );

    // If the user stopped mid-stream, keep any partial answer and clear streaming.
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant" && last.streaming) {
        last.streaming = false;
      }
      return next;
    });
    setBusy(false);
    setThinking(null);
    setAnalysingDocs(false);
    setAttachments([]);
    setSeededContext([]);
    void refreshSessions();
  }

  const empty = messages.length === 0;
  const filteredSessions = sessions.filter((s) =>
    s.title.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const contextChips = [
    ...seededContext.map((c, i) => ({ label: c.label ?? c.kind, key: `seed-${i}` })),
    ...attachments.map((a) => ({ label: a.filename, key: a.attachment_id })),
  ];

  function closeSourcePane() {
    setPaneSource(null);
    setPanePreview(null);
    setPaneError(null);
    setPaneLoading(false);
    setPaneJump(null);
  }

  /**
   * Cite / References click: take the reader to the passage the answer came from.
   *
   * Web sources open their page; document-backed sources open the viewer at the
   * cited page with the retrieved chunk highlighted. Showing the chunk in the
   * document itself — in its surrounding context — is what lets the reader judge
   * whether the right passage was retrieved.
   */
  function openCitation(message: Message, index: number) {
    const sources = message.sources ?? [];
    const s = sources[index];
    if (!s) return;

    const httpUrl = (s.url || "").trim();
    const key =
      (s.storage_key || "").trim() ||
      (/^gs:\/\/legalos\//i.test(httpUrl)
        ? httpUrl.replace(/^gs:\/\/legalos\//i, "")
        : "");
    const needle = (s.chunk_text || s.snippet || "").trim();

    // A stored document wins over a link: opening the actual page of the actual PDF
    // is stronger evidence than the regulator's landing page. Only when there is no
    // stored file do we fall back to the source URL.
    if (!key) {
      const externalUrl = /^https?:\/\//i.test(httpUrl)
        ? httpUrl
        : /^https?:\/\//i.test((s.canonical_url || "").trim())
          ? (s.canonical_url || "").trim()
          : "";
      if (externalUrl) {
        window.open(externalUrl, "_blank", "noopener,noreferrer");
        return;
      }
      if (s.kind === "web") return;
    }

    // Same library doc already open → just re-jump (page + highlight).
    if (
      key &&
      paneSource?.storage_key === key &&
      panePreview &&
      !paneLoading
    ) {
      const page =
        (s.page && s.page > 0 ? s.page : null) ||
        estimatePageFromText(panePreview.text, needle) ||
        undefined;
      setPaneSource((prev) => (prev ? { ...prev, page: page ?? prev.page } : prev));
      setPaneJump({
        page,
        snippet: needle || undefined,
        // bump so effect re-runs even for the same page
        token: Date.now(),
      });
      return;
    }

    // Open (or switch) the document pane for library / GCS sources.
    if (key) {
      void openSourceFromList(sources, index);
      return;
    }

    // No storage_key yet — still try open (title→library resolve for JFPSL/docs).
    if (s.kind === "template" || s.kind === "executed" || s.kind === "attachment") {
      void openSourceFromList(sources, index);
      return;
    }

    // Attachment / text-only cite while a viewer is already open: jump by page + needle.
    if (panePreview && !paneLoading && (s.page || needle)) {
      const page =
        (s.page && s.page > 0 ? s.page : null) ||
        estimatePageFromText(panePreview.text, needle) ||
        undefined;
      if (page || needle) {
        setPaneJump({
          page,
          snippet: needle || undefined,
          token: Date.now(),
        });
      }
    }
  }

  async function openSourceFromList(sources: ChatSource[], index: number) {
    const s = sources[index];
    if (!s) return;

    const httpUrl = (s.url || "").trim();
    let key = (s.storage_key || "").trim() || null;

    // Prefer the stored document; only link out when there is no file to show.
    // (A regulation source carries the regulator URL *and* the ingested PDF.)
    if (!key && (s.kind === "web" || /^https?:\/\//i.test(httpUrl))) {
      const externalUrl = /^https?:\/\//i.test(httpUrl)
        ? httpUrl
        : /^https?:\/\//i.test((s.canonical_url || "").trim())
          ? (s.canonical_url || "").trim()
          : "";
      if (externalUrl) {
        window.open(externalUrl, "_blank", "noopener,noreferrer");
        return;
      }
    }
    if (!key && /^gs:\/\/legalos\//i.test(httpUrl)) {
      key = httpUrl.replace(/^gs:\/\/legalos\//i, "");
    }
    // JFPSL hits sometimes lack storage_key — resolve via library filename match.
    if (!key && (s.kind === "template" || s.kind === "executed" || s.kind === "attachment")) {
      key = await resolveLibraryKeyByTitle(s.title || s.label || "");
      if (key) {
        setMessages((prev) =>
          prev.map((m) => {
            if (!m.sources?.length) return m;
            const next = m.sources.map((src, i) =>
              i === index ? { ...src, storage_key: key } : src,
            );
            return { ...m, sources: next };
          }),
        );
      }
    }
    if (!key) {
      // No previewable file: the pane still shows the retrieved excerpt itself, so
      // the reader can always see the text the answer was grounded in.
      setPaneSource(s);
      setPanePreview(null);
      setPaneJump(null);
      setPaneError(
        s.kind === "attachment"
          ? "This upload has no stored file to preview — showing the retrieved excerpt."
          : "This source has no linked document to preview — showing the retrieved excerpt.",
      );
      setPaneLoading(false);
      return;
    }

    setPaneSource({ ...s, storage_key: key });
    setPaneLoading(true);
    setPaneError(null);
    setPanePreview(null);
    setPaneJump(null);
    try {
      const preview = await api.previewTemplateLibrary(key);
      setPanePreview(preview);
      const needle = s.chunk_text || s.snippet;
      const estimated =
        s.page && s.page > 0
          ? s.page
          : estimatePageFromText(preview.text, needle);
      setPaneSource((prev) =>
        prev ? { ...prev, page: estimated ?? prev.page ?? null } : prev,
      );
      if (estimated) {
        // Persist page onto the message sources so chips render as "Page N".
        setMessages((prev) =>
          prev.map((m) => {
            if (!m.sources?.length) return m;
            let changed = false;
            const next = m.sources.map((src, i) => {
              if (
                i === index &&
                (src.storage_key === key || src.title === s.title) &&
                !src.page
              ) {
                changed = true;
                return { ...src, page: estimated, storage_key: key };
              }
              return src;
            });
            return changed ? { ...m, sources: next } : m;
          }),
        );
      }
      setPaneJump({
        page: estimated ?? undefined,
        snippet: needle || undefined,
        token: Date.now(),
      });
    } catch (err: unknown) {
      setPaneError(err instanceof ApiError ? err.detail : "Could not load document preview");
    } finally {
      setPaneLoading(false);
    }
  }

  // Jump the document viewer: page first, then text highlight from chunk.
  useEffect(() => {
    if (!paneJump || !panePreview || paneLoading) return;
    const t = window.setTimeout(() => {
      if (paneJump.page && paneJump.page > 0) {
        viewerRef.current?.scrollToPage(paneJump.page);
      }
      if (paneJump.snippet) {
        // After page scroll, still run text highlight / extracted-text mark.
        window.setTimeout(() => {
          viewerRef.current?.scrollToText(paneJump.snippet!);
        }, paneJump.page ? 280 : 0);
      }
    }, 450);
    return () => window.clearTimeout(t);
  }, [paneJump, panePreview, paneLoading]);

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden animate-fade-in">
      {/* Sessions sidebar */}
      {!collapsed && (
        <aside className="w-64 shrink-0 border-r border-separator bg-paper flex flex-col animate-genie-rise">
          <div className="flex items-center justify-between px-4 h-12 border-b border-separator">
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-label tracking-tight">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/10 text-accent">
                <LawGenieMark className="w-4 h-4" />
              </span>
              LawGenie
            </span>
            <button
              onClick={() => setCollapsed(true)}
              title="Collapse sidebar"
              className="rounded-md px-1.5 py-1 text-label-tertiary hover:text-label hover:bg-bg-accent text-sm transition"
            >
              ⟨
            </button>
          </div>
          <div className="p-3 space-y-1 border-b border-separator">
            <button
              onClick={startNewSession}
              className="btn-primary w-full flex items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold transition shadow-atelier-soft"
            >
              <span className="text-base leading-none" aria-hidden>
                +
              </span>
              New chat
            </button>
            <button
              onClick={() => setShowSearch((v) => !v)}
              className="w-full flex items-center gap-2 rounded-xl px-2.5 py-2 text-sm text-label-secondary hover:bg-bg-accent transition"
            >
              Search chats
            </button>
            {showSearch && (
              <input
                autoFocus
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter sessions…"
                className="w-full mt-1 rounded-lg border border-separator bg-bg px-3 py-1.5 text-sm text-label focus:outline-none focus:ring-2 focus:ring-accent/20"
              />
            )}
          </div>
          <div className="flex-1 overflow-y-auto scrollbar-thin p-2">
            <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-label-tertiary">
              My Sessions
            </div>
            {filteredSessions.length === 0 && (
              <div className="px-2 py-3 text-sm text-label-tertiary">No sessions yet</div>
            )}
            {filteredSessions.map((s) => (
              <button
                key={s.session_id}
                onClick={() => void openSession(s.session_id, false)}
                className={`w-full text-left rounded-lg px-3 py-2 mb-0.5 transition ${
                  activeSession === s.session_id && !readOnly
                    ? "bg-bg-accent text-label shadow-subtle"
                    : "text-label-secondary hover:bg-bg-accent/60"
                }`}
              >
                <div className="text-sm font-medium truncate">{s.title}</div>
                <div className="text-xs text-label-tertiary">{formatDate(s.updated_at)}</div>
              </button>
            ))}

            {shared.length > 0 && (
              <>
                <div className="px-2 pt-4 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-label-tertiary">
                  Shared with me
                </div>
                {shared.map((s) => (
                  <button
                    key={s.session_id}
                    onClick={() => void openSession(s.session_id, true)}
                    className={`w-full text-left rounded-lg px-3 py-2 mb-0.5 transition ${
                      activeSession === s.session_id && readOnly
                        ? "bg-bg-accent text-label shadow-subtle"
                        : "text-label-secondary hover:bg-bg-accent/60"
                    }`}
                  >
                    <div className="text-sm font-medium truncate">{s.title}</div>
                    <div className="text-xs text-label-tertiary truncate">
                      from {s.shared_by ?? "a colleague"}
                    </div>
                  </button>
                ))}
              </>
            )}
          </div>
        </aside>
      )}

      {/* Chat + optional source preview pane */}
      <div className="flex-1 flex min-w-0 bg-bg">
      <section className="flex-1 flex flex-col min-w-0">
        <header className="h-12 shrink-0 flex items-center gap-3 px-4 border-b border-separator bg-paper/90 backdrop-blur-md">
          {collapsed && (
            <button
              onClick={() => setCollapsed(false)}
              title="Expand sidebar"
              className="rounded-md px-1.5 py-1 text-label-tertiary hover:text-label hover:bg-bg-accent text-sm transition"
            >
              ⟩
            </button>
          )}
          <h1 className="text-[15px] font-semibold text-label truncate flex-1 tracking-tight">
            {activeTitle}
            {readOnly && <span className="ml-2 text-xs font-normal text-label-tertiary">(shared · read-only)</span>}
          </h1>
          {activeSession && (
            <div className="flex items-center gap-1">
              {!readOnly && (
                <button
                  onClick={() => void openShare()}
                  className="rounded-lg px-2.5 py-1.5 text-xs text-label-secondary hover:bg-bg-accent transition"
                  title="Share with users"
                >
                  Share
                </button>
              )}
              <button
                onClick={downloadChat}
                className="rounded-lg px-2.5 py-1.5 text-xs text-label-secondary hover:bg-bg-accent transition"
                title="Download as .docx"
              >
                Download
              </button>
              {!readOnly && (
                <button
                  onClick={() => void clearSession()}
                  className="rounded-lg px-2.5 py-1.5 text-xs text-red-500 hover:bg-red-500/10 transition"
                  title="Delete this chat"
                >
                  Clear
                </button>
              )}
            </div>
          )}
        </header>

        <div ref={scrollRef} className={`flex-1 overflow-y-auto scrollbar-thin px-3 sm:px-5 flex flex-col ${empty ? "lawgenie-stage" : ""}`}>
          {empty ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center gap-5 px-4 sm:px-8 py-14">
              <div className="lawgenie-mark-halo animate-genie-breathe animate-genie-rise">
                <LawGenieMark className="h-10 w-10" />
              </div>
              <div className="space-y-2.5 max-w-3xl w-full">
                <p
                  className="text-xs font-semibold uppercase tracking-[0.14em] text-accent animate-genie-rise"
                  style={{ animationDelay: "40ms" }}
                >
                  LawGenie
                </p>
                <h2
                  className="text-3xl sm:text-4xl font-semibold tracking-tight text-label animate-genie-rise"
                  style={{ animationDelay: "90ms" }}
                >
                  Hi {firstName}. How can I help?
                </h2>
                <p
                  className="text-[15px] text-label-secondary max-w-2xl mx-auto leading-relaxed animate-genie-rise"
                  style={{ animationDelay: "160ms" }}
                >
                  Review contracts, research with citations, or draft from JFPSL templates.
                  Attach files for grounded answers.
                </p>
              </div>
              <div
                className="flex flex-wrap items-center justify-center gap-2 max-w-4xl w-full animate-genie-rise"
                style={{ animationDelay: "240ms" }}
              >
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setInput(prompt)}
                    className="lawgenie-prompt rounded-xl px-3.5 py-2 text-sm"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="w-full py-4 space-y-4">
              {messages.map((m, i) => {
                // Hide the empty answer shell while tools/status are running —
                // the analysing strip below covers that state.
                if (m.role === "assistant" && m.streaming && !m.text.trim() && !(m.thoughts?.length)) {
                  return null;
                }
                return (
                <MessageBubble
                  key={i}
                  message={m}
                  onRate={rate}
                  onDetailedFeedback={openDetailedFeedback}
                  onOpenSource={(idx) => openCitation(m, idx)}
                  onFollowUp={(q) => void send(q)}
                  followUpsDisabled={busy || readOnly}
                />
                );
              })}
              {thinking && (
                <div className="lawgenie-analysing w-full max-w-none animate-fade-in">
                  <div className="flex items-center gap-2.5">
                    <LawGenieMark className="h-5 w-5 text-accent animate-genie-breathe" />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-label truncate">
                        {analysingDocs ? "Analysing your document" : "Working on your question"}
                      </div>
                      <div className="text-xs text-label-secondary truncate">{thinking}</div>
                    </div>
                  </div>
                  <div className="attach-snail" aria-hidden>
                    <span className="attach-snail-fill" />
                  </div>
                  <div className="lawgenie-thinking-dots inline-flex gap-1" aria-hidden>
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="shrink-0 px-3 sm:px-5 py-3 sm:py-4 bg-gradient-to-t from-bg via-bg to-transparent">
          <div className="w-full">
            {error && <div className="mb-2 text-sm text-red-500">{error}</div>}
            {readOnly ? (
              <div className="rounded-2xl border border-separator bg-bg-secondary px-4 py-3 text-center text-sm text-label-tertiary">
                This is a shared chat — you can read and download it, but not add messages.
              </div>
            ) : (
              <>
                {(contextChips.length > 0 || uploadingName) && (
                  <div className="mb-2 flex flex-wrap gap-2">
                    {seededContext.map((c, i) => (
                      <span
                        key={`seed-${i}`}
                        className="attach-chip attach-chip-ready"
                      >
                        <span className="flex items-center justify-between gap-2 text-xs font-medium text-label truncate">
                          <span className="truncate">{c.label ?? c.kind}</span>
                          <button
                            type="button"
                            className="text-label-tertiary hover:text-label shrink-0"
                            onClick={() =>
                              setSeededContext((prev) => prev.filter((_, idx) => idx !== i))
                            }
                            aria-label="Remove"
                          >
                            ×
                          </button>
                        </span>
                      </span>
                    ))}
                    {attachments.map((a) => (
                      <span key={a.attachment_id} className="attach-chip attach-chip-ready">
                        <span className="flex items-center justify-between gap-2 text-xs font-medium text-label truncate">
                          <span className="truncate" title={a.filename}>
                            {a.filename}
                          </span>
                          <button
                            type="button"
                            className="text-label-tertiary hover:text-label shrink-0"
                            onClick={() =>
                              setAttachments((prev) =>
                                prev.filter((x) => x.attachment_id !== a.attachment_id),
                              )
                            }
                            aria-label="Remove attachment"
                          >
                            ×
                          </button>
                        </span>
                        <span className="text-[10px] text-success">Ready</span>
                      </span>
                    ))}
                    {uploadingName && (
                      <span className="attach-chip" aria-live="polite">
                        <span className="text-xs font-medium text-label truncate" title={uploadingName}>
                          {uploadingName}
                        </span>
                        <span className="text-[10px] text-accent">Attaching…</span>
                        <span className="attach-snail" aria-hidden>
                          <i />
                        </span>
                      </span>
                    )}
                  </div>
                )}
                <div className={`lawgenie-composer rounded-2xl ${empty ? "animate-composer-pulse" : ""}`}>
                  <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void send();
                      }
                    }}
                    rows={1}
                    placeholder="Ask LawGenie anything — review, research, or draft…"
                    className="w-full resize-none bg-transparent px-4 pt-3.5 pb-1.5 text-[15px] text-label placeholder:text-label-tertiary focus:outline-none max-h-40"
                  />
                  {listening && interimTranscript && (
                    <div className="px-4 pb-1 text-xs italic text-label-tertiary truncate" title={interimTranscript}>
                      Listening: {interimTranscript}
                    </div>
                  )}
                  <div className="flex items-center gap-2 px-3 pb-3 flex-wrap">
                    <button
                      type="button"
                      onClick={() => fileRef.current?.click()}
                      title="Attach documents (PDF, DOCX, TXT)"
                      disabled={!!uploadingName || busy}
                      className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-accent/30 bg-accent/10 px-3 text-sm font-semibold text-accent hover:bg-accent/15 hover:border-accent/50 transition disabled:opacity-40"
                    >
                      <Icon.Paperclip className="h-4 w-4 shrink-0" aria-hidden />
                      Attach
                    </button>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => void openTemplatePicker()}
                        title="Attach a JFPSL template"
                        disabled={!!uploadingName || busy || attachingTemplate}
                        className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-accent/30 bg-accent/10 px-3 text-sm font-semibold text-accent hover:bg-accent/15 hover:border-accent/50 transition disabled:opacity-40"
                      >
                        Template
                      </button>
                      {templateOpen && (
                        <>
                          <div
                            className="fixed inset-0 z-10"
                            onClick={() => setTemplateOpen(false)}
                          />
                          <div className="absolute bottom-full left-0 z-20 mb-2 w-80 max-h-72 overflow-hidden rounded-xl border border-separator bg-bg shadow-atelier animate-scale-in flex flex-col">
                            <div className="px-3 py-2 border-b border-separator">
                              <div className="text-xs font-semibold text-label">JFPSL templates</div>
                              <input
                                value={templateFilter}
                                onChange={(e) => setTemplateFilter(e.target.value)}
                                placeholder="Filter…"
                                className="mt-1.5 w-full rounded-lg border border-separator bg-bg-secondary px-2.5 py-1.5 text-xs text-label focus:outline-none"
                              />
                            </div>
                            <div className="overflow-y-auto scrollbar-thin flex-1">
                              {templateLoading && (
                                <div className="px-3 py-4 text-sm text-label-tertiary">Loading…</div>
                              )}
                              {!templateLoading && templateItems.length === 0 && (
                                <div className="px-3 py-4 text-sm text-label-tertiary">No templates found.</div>
                              )}
                              {!templateLoading &&
                                templateItems
                                  .filter((it) => {
                                    const q = templateFilter.trim().toLowerCase();
                                    if (!q) return true;
                                    return (
                                      (it.name || "").toLowerCase().includes(q) ||
                                      (it.filename || "").toLowerCase().includes(q) ||
                                      (it.contract_type || "").toLowerCase().includes(q)
                                    );
                                  })
                                  .slice(0, 80)
                                  .map((it) => (
                                    <button
                                      key={it.storage_key}
                                      type="button"
                                      disabled={attachingTemplate}
                                      onClick={() => void pickTemplate(it)}
                                      className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left hover:bg-bg-accent border-b border-separator/40 last:border-b-0 disabled:opacity-50"
                                    >
                                      <span className="text-sm text-label truncate w-full">
                                        {it.name || it.filename}
                                      </span>
                                      <span className="text-[11px] text-label-tertiary truncate w-full">
                                        {[it.contract_type, it.doc_kind].filter(Boolean).join(" · ")}
                                      </span>
                                    </button>
                                  ))}
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={toggleDictation}
                      disabled={readOnly || busy || !sttSupported}
                      title={
                        !sttSupported
                          ? "Speech-to-text needs Chrome, Edge, or Safari"
                          : listening
                            ? "Stop listening"
                            : "Speak with your microphone (speech-to-text)"
                      }
                      aria-pressed={listening}
                      className={`inline-flex h-9 items-center gap-1.5 rounded-xl border px-3 text-sm font-semibold transition disabled:opacity-40 ${
                        listening
                          ? "border-error/50 bg-error/15 text-error animate-pulse"
                          : "border-accent/30 bg-accent/10 text-accent hover:bg-accent/15 hover:border-accent/50"
                      }`}
                    >
                      <Icon.Mic className="h-4 w-4 shrink-0" aria-hidden />
                      {listening ? "Listening…" : "Mic"}
                    </button>
                    <input
                      ref={fileRef}
                      type="file"
                      multiple
                      accept=".pdf,.docx,.doc,.txt,.md"
                      className="hidden"
                      onChange={onPickFile}
                    />

                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setModeOpen((v) => !v)}
                        className="flex items-center gap-1.5 rounded-xl border border-separator bg-bg px-3 py-2 text-sm text-label-secondary hover:bg-bg-accent transition"
                      >
                        <span className="font-medium text-label">{activeMode.label}</span>
                        <span className="text-label-tertiary text-xs">▾</span>
                      </button>
                      {modeOpen && (
                        <>
                          <div className="fixed inset-0 z-10" onClick={() => setModeOpen(false)} />
                          <div className="absolute bottom-full left-0 z-20 mb-2 w-72 rounded-xl border border-separator bg-bg p-1.5 shadow-atelier animate-scale-in">
                            {MODES.map((m) => (
                              <button
                                key={m.id}
                                onClick={() => {
                                  setMode(m.id);
                                  setModeOpen(false);
                                }}
                                className={`flex w-full items-start gap-2 rounded-lg px-3 py-2.5 text-left transition ${
                                  mode === m.id ? "bg-bg-accent" : "hover:bg-bg-accent/60"
                                }`}
                              >
                                <span>
                                  <span className="block text-sm font-medium text-label">{m.label}</span>
                                  <span className="block text-xs text-label-tertiary">{m.blurb}</span>
                                </span>
                              </button>
                            ))}
                          </div>
                        </>
                      )}
                    </div>

                    <div className="flex-1" />
                    {busy ? (
                      <button
                        type="button"
                        onClick={stopGeneration}
                        title="Stop generating (Esc)"
                        className="inline-flex items-center gap-1.5 rounded-xl border border-error/40 bg-error/10 px-4 py-2 text-sm font-semibold text-error hover:bg-error/15 transition"
                      >
                        <Icon.Stop className="h-4 w-4" aria-hidden />
                        Stop
                      </button>
                    ) : (
                      <button
                        onClick={() => void send()}
                        disabled={!input.trim()}
                        className="btn-primary rounded-xl px-5 py-2 text-sm font-semibold transition shadow-atelier-soft disabled:opacity-40"
                      >
                        Send
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
            <p className="mt-2 text-center text-[11px] text-label-tertiary tracking-wide">
              Decision-support only — not a substitute for qualified legal advice.
            </p>
          </div>
        </div>
      </section>

      {paneSource && (
        <>
          <div
            className="fixed inset-0 z-20 bg-black/30 md:hidden"
            onClick={closeSourcePane}
            aria-hidden
          />
          <aside
            className={
              "z-30 flex w-full flex-col border-l border-separator bg-bg-secondary " +
              "fixed inset-y-0 right-0 max-w-full shadow-xl md:static md:z-auto " +
              "md:w-[42%] md:min-w-[320px] md:max-w-2xl md:shadow-none"
            }
            aria-label="Source document viewer"
          >
            <div className="flex min-h-12 shrink-0 items-start gap-2 border-b border-separator bg-bg px-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-label">
                  {panePreview?.name || paneSource.title}
                </div>
                <div className="truncate text-[11px] text-label-tertiary">
                  {paneSource.kind === "executed"
                    ? "Executed contract"
                    : paneSource.kind === "template"
                      ? "JFPSL template"
                      : paneSource.kind === "attachment"
                        ? "Attached document"
                        : paneSource.kind === "regulation"
                          ? "Regulation"
                          : "Source"}
                  {paneSource.page ? ` · Page ${paneSource.page}` : ""}
                </div>
                {/* Provenance the citation carried: which provision, whose rule, and
                    which version — so the highlighted passage can be judged. */}
                {paneSource.section_label ? (
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-label-tertiary">
                    <span className="rounded bg-accent/10 px-1.5 py-0.5 font-medium text-accent">
                      {paneSource.section_label}
                    </span>
                    {paneSource.issuer ? <span>{paneSource.issuer}</span> : null}
                    {paneSource.effective_date ? (
                      <span>effective {paneSource.effective_date}</span>
                    ) : null}
                    {paneSource.superseded_by ? (
                      <span className="text-warning">
                        superseded by {paneSource.superseded_by}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {(() => {
                  const external = /^https?:\/\//i.test((paneSource.url || "").trim())
                    ? (paneSource.url || "").trim()
                    : /^https?:\/\//i.test((paneSource.canonical_url || "").trim())
                      ? (paneSource.canonical_url || "").trim()
                      : "";
                  return external ? (
                    <a
                      href={external}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-lg px-2.5 py-1.5 text-xs text-accent hover:bg-bg-accent"
                    >
                      Official source ↗
                    </a>
                  ) : null;
                })()}
                <button
                  type="button"
                  onClick={closeSourcePane}
                  className="rounded-lg px-2.5 py-1.5 text-xs text-label-secondary hover:bg-bg-accent"
                >
                  Close
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {paneLoading && (
                <p className="p-4 text-sm text-label-tertiary">Loading document…</p>
              )}
              {!paneLoading && paneError && (
                <div className="space-y-3 p-2">
                  <p className="text-sm text-amber-600 dark:text-amber-400">{paneError}</p>
                  {(paneSource.chunk_text || paneSource.snippet) && (
                    <div>
                      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-label-tertiary">
                        Retrieved excerpt
                      </div>
                      <div className="rounded-lg border border-separator bg-bg px-3 py-2.5 text-sm leading-relaxed text-label whitespace-pre-wrap">
                        {paneSource.chunk_text || paneSource.snippet}
                      </div>
                    </div>
                  )}
                </div>
              )}
              {!paneLoading && !paneError && panePreview && paneSource.storage_key && (
                <DocumentViewer
                  ref={viewerRef}
                  storageKey={paneSource.storage_key}
                  fileUrl={api.libraryFileUrl(paneSource.storage_key)}
                  mimeType={panePreview.content_type}
                  filename={panePreview.filename}
                  extractedText={panePreview.text}
                  title={panePreview.name || paneSource.title}
                />
              )}
            </div>
          </aside>
        </>
      )}
      </div>

      {/* Detailed feedback dialog (help button) */}
      {feedbackModalTurnId != null && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/30"
          onClick={() => setFeedbackModalTurnId(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-separator bg-bg p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-label">We Value Your Feedback</h3>
            <p className="mt-1 text-sm text-label-tertiary">
              Your input helps us improve our product. Please share your thoughts or issues you
              encountered while using the platform.
            </p>
            <label className="mt-4 block text-sm font-medium text-label">Your Feedback</label>
            <textarea
              autoFocus
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              rows={5}
              placeholder="Share your thoughts, issues, or suggestions…"
              className="mt-1.5 w-full resize-none rounded-xl border border-separator bg-bg-secondary px-3 py-2 text-sm text-label focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                onClick={() => setFeedbackModalTurnId(null)}
                className="rounded-full border border-separator px-4 py-1.5 text-sm text-label-secondary hover:bg-bg-accent"
              >
                Cancel
              </button>
              <button
                onClick={() => void submitDetailedFeedback()}
                className="rounded-full bg-accent px-5 py-1.5 text-sm font-medium text-white hover:opacity-90"
              >
                Submit
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Share dialog */}
      {shareOpen && (
        <div
          className="fixed inset-0 z-30 flex items-center justify-center bg-black/30"
          onClick={() => setShareOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-separator bg-bg p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold text-label">Share this chat</h3>
            <p className="mt-1 text-sm text-label-tertiary">
              Select users to give read-only access.
            </p>

            {shareExisting.length > 0 && (
              <div className="mt-3 rounded-lg border border-separator overflow-hidden">
                <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-label-tertiary bg-bg-secondary">
                  Currently shared
                </div>
                <ul className="max-h-32 overflow-y-auto scrollbar-thin">
                  {shareExisting.map((s) => (
                    <li
                      key={s.user_id}
                      className="flex items-center justify-between gap-2 px-3 py-2 border-t border-separator/50"
                    >
                      <span className="min-w-0">
                        <span className="block text-sm text-label truncate">{s.full_name}</span>
                        <span className="block text-xs text-label-tertiary truncate">{s.email}</span>
                      </span>
                      <button
                        type="button"
                        onClick={() => void revokeShare(s.user_id)}
                        className="shrink-0 rounded-lg px-2 py-1 text-xs text-red-500 hover:bg-red-500/10"
                      >
                        Revoke
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <input
              value={shareFilter}
              onChange={(e) => setShareFilter(e.target.value)}
              placeholder="Search users…"
              className="mt-3 w-full rounded-lg border border-separator bg-bg-secondary px-3 py-2 text-sm text-label focus:outline-none"
            />
            <div className="mt-2 max-h-64 overflow-y-auto scrollbar-thin rounded-lg border border-separator">
              {shareUsers.length === 0 && (
                <div className="px-3 py-4 text-sm text-label-tertiary">No users available.</div>
              )}
              {shareUsers
                .filter((u) => {
                  const q = shareFilter.trim().toLowerCase();
                  return (
                    !q ||
                    u.full_name.toLowerCase().includes(q) ||
                    u.email.toLowerCase().includes(q)
                  );
                })
                .map((u) => (
                  <label
                    key={u.id}
                    className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-bg-accent/60 border-b border-separator/50 last:border-b-0"
                  >
                    <input
                      type="checkbox"
                      checked={shareSelected.has(u.id)}
                      onChange={() => toggleShareUser(u.id)}
                      className="accent-accent h-4 w-4"
                    />
                    <span className="min-w-0">
                      <span className="block text-sm text-label truncate">{u.full_name}</span>
                      <span className="block text-xs text-label-tertiary truncate">
                        {u.email} · {u.role.replace(/_/g, " ")}
                      </span>
                    </span>
                  </label>
                ))}
            </div>
            {shareMsg && <div className="mt-2 text-sm text-label-secondary">{shareMsg}</div>}
            <div className="mt-4 flex items-center justify-between gap-2">
              <span className="text-xs text-label-tertiary">{shareSelected.size} selected</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setShareOpen(false)}
                  className="rounded-lg px-3 py-1.5 text-sm text-label-secondary hover:bg-bg-accent"
                >
                  Close
                </button>
                <button
                  onClick={() => void submitShare()}
                  disabled={shareSelected.size === 0}
                  className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40"
                >
                  Share
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Rough page estimate from extracted text + RAG snippet (50 lines ≈ 1 page). */
function estimatePageFromText(
  fullText: string,
  snippet: string | null | undefined,
): number | null {
  if (!fullText || !snippet) return null;
  const probe = snippet.trim().slice(0, 80).toLowerCase();
  if (probe.length < 12) return null;
  const off = fullText.toLowerCase().indexOf(probe);
  if (off < 0) {
    const short = probe.slice(0, 48);
    if (short.length < 12) return null;
    const off2 = fullText.toLowerCase().indexOf(short);
    if (off2 < 0) return null;
    const lineNumber = fullText.slice(0, off2).split("\n").length;
    return Math.max(1, Math.ceil(lineNumber / 50));
  }
  const lineNumber = fullText.slice(0, off).split("\n").length;
  return Math.max(1, Math.ceil(lineNumber / 50));
}

/** Fuzzy-match a source title to a JFPSL library file when storage_key is missing. */
async function resolveLibraryKeyByTitle(title: string): Promise<string | null> {
  const raw = (title || "").trim();
  if (!raw || raw.length < 4) return null;
  const needle = raw
    .replace(/^executed:\s*/i, "")
    .replace(/\.[a-z0-9]+$/i, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  if (needle.length < 4) return null;
  try {
    const items = await api.listTemplateLibrary();
    let best: { key: string; score: number } | null = null;
    for (const it of items) {
      const name = (it.name || it.filename || it.storage_key || "")
        .replace(/\.[a-z0-9]+$/i, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ")
        .trim();
      if (!name) continue;
      let score = 0;
      if (name === needle) score = 100;
      else if (name.includes(needle) || needle.includes(name)) score = Math.min(name.length, needle.length);
      else {
        const parts = needle.split(" ").filter((w) => w.length > 3);
        const hits = parts.filter((w) => name.includes(w)).length;
        if (hits >= 2) score = hits * 10;
      }
      if (score > 0 && (!best || score > best.score)) {
        best = { key: it.storage_key, score };
      }
    }
    return best && best.score >= 20 ? best.key : null;
  } catch {
    return null;
  }
}

/** Prefer a quote from the claim; else a distinctive slice of the chunk. */
function highlightNeedle(chunk: string, claim: string): string {
  const quoted =
    claim.match(/[“"]([^”"]{12,160})[”"]/) ||
    claim.match(/'([^']{12,160})'/);
  if (quoted?.[1] && chunk.toLowerCase().includes(quoted[1].toLowerCase().slice(0, 40))) {
    return quoted[1].trim().slice(0, 120);
  }
  // Shared run: walk chunk windows looking for presence in claim.
  const c = chunk.replace(/\s+/g, " ").trim();
  const claimNorm = claim.replace(/\s+/g, " ").toLowerCase();
  for (let len = 80; len >= 24; len -= 8) {
    for (let i = 0; i + len <= Math.min(c.length, 400); i += 12) {
      const window = c.slice(i, i + len);
      if (claimNorm.includes(window.toLowerCase())) return window;
    }
  }
  return c.slice(0, 100);
}

/** Strip Markdown/bare links and "Source:" lines for a link-free copy. */
function stripLinks(md: string): string {
  return md
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/<https?:\/\/[^>]+>/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/^\s*Source:.*$/gim, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Browser SpeechRecognition constructor (Chrome/Edge/Safari). */
function getSpeechRecognitionCtor(): (new () => SpeechRecognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as Window &
    typeof globalThis & {
      SpeechRecognition?: new () => SpeechRecognition;
      webkitSpeechRecognition?: new () => SpeechRecognition;
    };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Pull "Suggested follow-up questions" into clickable chips; strip that section
 * from the markdown body so it isn't duplicated.
 */
function extractFollowUps(text: string): { body: string; followUps: string[] } {
  if (!text) return { body: text, followUps: [] };
  const headingRe =
    /(?:^|\n)#{1,4}\s*Suggested follow-up questions?\s*\n([\s\S]*?)(?=\n#{1,4}\s|\s*$)/i;
  const match = text.match(headingRe);
  if (!match || match.index == null) return { body: text, followUps: [] };

  const section = match[1] || "";
  const followUps = section
    .split("\n")
    .map((line) =>
      line
        .replace(/^\s*(?:[-*+]|\d+[.)])\s+/, "")
        .replace(/^\s*\[[ xX]\]\s+/, "")
        .replace(/\*\*/g, "")
        .trim(),
    )
    .filter((q) => q.length > 8 && !/^#{1,4}\s/.test(q))
    .slice(0, 3);

  const body = (text.slice(0, match.index) + text.slice(match.index + match[0].length))
    .replace(/\n{3,}/g, "\n\n")
    .trimEnd();

  return { body, followUps };
}

type ChecklistItem = { id: string; label: string; done: boolean };

/** Parse draft Structure checklist / [[PLACEHOLDER: …]] markers for a simple panel. */
function parseStructureChecklist(text: string): ChecklistItem[] {
  if (!text) return [];
  const items: ChecklistItem[] = [];
  const seen = new Set<string>();

  for (const line of text.split("\n")) {
    const task = line.match(/^\s*[-*+]\s+\[([ xX])\]\s+(.+?)\s*$/);
    if (task) {
      const label = task[2].replace(/\*\*/g, "").trim();
      if (label && !seen.has(label.toLowerCase())) {
        seen.add(label.toLowerCase());
        items.push({ id: `t-${items.length}`, label, done: /x/i.test(task[1]) });
      }
      continue;
    }
  }

  const phRe = /\[\[PLACEHOLDER:\s*([^\]]+)\]\]/gi;
  let m: RegExpExecArray | null;
  while ((m = phRe.exec(text)) !== null) {
    const label = m[1].trim();
    if (!label) continue;
    const key = `ph:${label.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({ id: `p-${items.length}`, label: `Placeholder: ${label}`, done: false });
  }

  return items;
}

function shouldShowStructurePanel(mode: Mode | null | undefined, text: string): boolean {
  if (mode !== "draft" || !text) return false;
  return /Structure checklist/i.test(text) || /\[\[PLACEHOLDER:/i.test(text);
}

function StructureChecklistPanel({ items }: { items: ChecklistItem[] }) {
  const [open, setOpen] = useState(true);
  if (!items.length) return null;
  const done = items.filter((i) => i.done).length;
  return (
    <div className="mt-3 rounded-xl border border-separator bg-bg-secondary/60 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-bg-accent/40"
        aria-expanded={open}
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-label-secondary">
          Structure checklist
        </span>
        <span className="text-[11px] text-label-tertiary">
          {done}/{items.length} · {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <ul className="border-t border-separator px-3 py-2 space-y-1.5">
          {items.map((item) => (
            <li key={item.id} className="flex items-start gap-2 text-sm text-label-secondary">
              <span
                className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] ${
                  item.done
                    ? "border-success/40 bg-success/15 text-success"
                    : "border-separator text-label-tertiary"
                }`}
                aria-hidden
              >
                {item.done ? "✓" : ""}
              </span>
              <span className={item.done ? "line-through text-label-tertiary" : ""}>
                {item.label}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function downloadMarkdown(text: string) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `lawgenie-answer-${new Date().toISOString().slice(0, 10)}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function SourceBadge({ site, kind }: { site?: string | null; kind: ChatSource["kind"] }) {
  const label = (
    site ||
    (kind === "executed"
      ? "Executed"
      : kind === "template"
        ? "JFPSL"
        : kind === "attachment"
          ? "Attachment"
          : kind === "regulation"
            ? "Regulation"
            : "web")
  ).slice(0, 14);
  const glyph =
    kind === "web" ? "◍" : kind === "attachment" ? "▤" : kind === "regulation" ? "§" : "▣";
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-bg-accent px-1.5 py-0.5 text-[10px] font-medium text-label-secondary ring-1 ring-separator">
      <span className="text-accent">{glyph}</span>
      {label}
    </span>
  );
}

function References({
  sources,
  onOpenSource,
}: {
  sources: ChatSource[];
  onOpenSource?: (index: number) => void;
}) {
  if (!sources.length) return null;

  function isWeb(s: ChatSource): boolean {
    const url = (s.url || "").trim();
    return s.kind === "web" || /^https?:\/\//i.test(url);
  }

  return (
    <div className="mt-4 border-t border-separator pt-3">
      <div className="text-sm font-semibold text-label mb-2">References</div>
      <ul className="space-y-1.5">
        {sources.map((s, i) => {
          const n = i + 1;
          const chip = (
            <span className="inline-flex shrink-0 cursor-pointer items-center rounded bg-accent/10 px-1.5 py-0.5 text-[11px] font-medium text-accent ring-1 ring-accent/25">
              {citationLabel(s, n)}
            </span>
          );
          const snippetLine = (s.snippet || "").trim().slice(0, 120);
          // For a clause, the provenance line matters more than the excerpt: it
          // tells the reader which instrument and which version they are relying on.
          const provenance = [
            s.section_label,
            s.effective_date ? `effective ${s.effective_date}` : null,
          ]
            .filter(Boolean)
            .join(" · ");
          return (
            <li key={s.chunk_id || i} className="flex items-start gap-2 text-[13px] text-label-secondary">
              {chip}
              <SourceBadge site={s.site} kind={s.kind} />
              <button
                type="button"
                onClick={() => onOpenSource?.(i)}
                className="min-w-0 flex-1 text-left hover:text-accent"
                title={s.kind === "regulation" ? fullCitation(s) : snippetLine || s.title}
              >
                <span className={isWeb(s) ? "text-accent truncate block" : "truncate block"}>
                  {s.title}
                </span>
                {provenance ? (
                  <span className="mt-0.5 block truncate text-[11px] text-label-tertiary">
                    {provenance}
                    {s.superseded_by ? (
                      <span className="ml-1 text-warning">· superseded by {s.superseded_by}</span>
                    ) : null}
                  </span>
                ) : snippetLine ? (
                  <span className="mt-0.5 block truncate text-[11px] text-label-tertiary">
                    {snippetLine}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ThoughtsList({ thoughts }: { thoughts: ChatThought[] }) {
  if (!thoughts.length) return null;

  return (
    <ol className="lawgenie-thoughts-list">
      {thoughts.map((t, idx) => (
        <li key={t.id} className="lawgenie-thought-step">
          <div className="lawgenie-thought-index" aria-hidden>
            {idx + 1}
          </div>
          <div className="lawgenie-thought-card">
            <div className="lawgenie-thought-label">{t.title || "Thinking"}</div>
            {t.detail && (
              <div className="lawgenie-thought-detail">
                <Markdown text={t.detail} />
              </div>
            )}
            {!!t.items?.length && (
              <div className="lawgenie-thought-chips">
                {t.items.map((item, i) =>
                  item.url && /^https?:\/\//i.test(item.url) ? (
                    <a
                      key={`${t.id}-${i}`}
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="lawgenie-thought-chip"
                      title={item.url}
                    >
                      {item.title}
                    </a>
                  ) : (
                    <span key={`${t.id}-${i}`} className="lawgenie-thought-chip" title={item.title}>
                      {item.title}
                    </span>
                  ),
                )}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function MessageBubble({
  message,
  onRate,
  onDetailedFeedback,
  onOpenSource,
  onFollowUp,
  followUpsDisabled,
}: {
  message: Message;
  onRate: (turnId: number, value: "up" | "down", current: "up" | "down" | null) => void;
  onDetailedFeedback: (turnId: number) => void;
  onOpenSource?: (index: number) => void;
  onFollowUp?: (question: string) => void;
  followUpsDisabled?: boolean;
}) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState<"" | "text" | "clean">("");
  const [msaBusy, setMsaBusy] = useState(false);
  const [msaMsg, setMsaMsg] = useState<string | null>(null);
  // Start collapsed while tools run; Research expands once the answer lands.
  const [thoughtsOpen, setThoughtsOpen] = useState(false);
  const { body, followUps } = useMemo(
    () => (isUser ? { body: message.text, followUps: [] as string[] } : extractFollowUps(message.text)),
    [isUser, message.text],
  );
  const checklistItems = useMemo(
    () =>
      !isUser && shouldShowStructurePanel(message.mode, message.text)
        ? parseStructureChecklist(message.text)
        : [],
    [isUser, message.mode, message.text],
  );

  useEffect(() => {
    if (
      !isUser &&
      !message.streaming &&
      message.mode === "research" &&
      (message.thoughts?.length ?? 0) > 0
    ) {
      setThoughtsOpen(true);
    }
  }, [isUser, message.streaming, message.mode, message.thoughts?.length]);

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed bg-accent text-white max-w-[min(92%,48rem)] shadow-atelier-soft">
          {message.text}
        </div>
      </div>
    );
  }

  async function copy(kind: "text" | "clean") {
    try {
      await navigator.clipboard.writeText(
        kind === "clean" ? stripLinks(message.text) : message.text,
      );
      setCopied(kind);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      /* ignore */
    }
  }

  async function sendToMsa() {
    if (message.turnId == null || msaBusy) return;
    setMsaBusy(true);
    setMsaMsg(null);
    try {
      const res = await api.sendChatTurnToMsa(message.turnId);
      setMsaMsg(
        res.tracker_id != null
          ? `Sent to MSA #${res.tracker_id}`
          : res.detail || "Sent to MSA",
      );
    } catch (err) {
      setMsaMsg(err instanceof Error ? err.message : "Could not send to MSA");
    } finally {
      setMsaBusy(false);
    }
  }

  const showActions = !message.streaming && !!message.text;
  const sources = message.sources ?? [];
  const thoughts = message.thoughts ?? [];
  const showFollowUps = !message.streaming && followUps.length > 0 && !!onFollowUp;
  const mLabel = modeLabel(message.mode);
  const timeLabel = formatTime(message.createdAt);
  const files = message.fileLabels ?? [];
  const metaBits = [
    timeLabel,
    mLabel,
    files.length ? `${files.length} file${files.length === 1 ? "" : "s"}` : "",
  ].filter(Boolean);

  return (
    <div className="flex justify-start animate-slide-up">
      <div className="w-full">
        {(metaBits.length > 0 || thoughts.length > 0) && (
          <div className="lawgenie-turn-meta">
            {metaBits.length > 0 && (
              <span className="lawgenie-turn-meta-bits">
                {metaBits.map((bit, i) => (
                  <span key={`${bit}-${i}`}>
                    {i > 0 && <span className="lawgenie-turn-meta-dot">·</span>}
                    {bit}
                  </span>
                ))}
              </span>
            )}
            {thoughts.length > 0 && (
              <button
                type="button"
                className="lawgenie-thoughts-toggle"
                aria-expanded={thoughtsOpen}
                onClick={() => setThoughtsOpen((v) => !v)}
              >
                <span className="lawgenie-thoughts-chevron" aria-hidden>
                  {thoughtsOpen ? "▾" : "▸"}
                </span>
                <span>
                  {thoughts.length} Thought{thoughts.length === 1 ? "" : "s"}
                </span>
              </button>
            )}
          </div>
        )}

        {thoughts.length > 0 && thoughtsOpen && (
          <div className="lawgenie-thoughts mb-3">
            <ThoughtsList thoughts={thoughts} />
          </div>
        )}

        {/* Don't flash an empty answer card while tools run — analysing strip covers it. */}
        {(!!message.text.trim() || !message.streaming) && (
        <div
          className={`lawgenie-answer ${
            message.streaming ? "lawgenie-answer-streaming" : ""
          } ${
            message.blocked
              ? "bg-amber-500/10 border border-amber-500/30"
              : ""
          }`}
        >
          <div className="px-4 pt-3.5 pb-2.5">
            {body ? (
              <Markdown text={body} sources={sources} onOpenSource={onOpenSource} />
            ) : (
              <span className="text-sm text-label-tertiary">{message.streaming ? "…" : ""}</span>
            )}
            {!message.streaming && checklistItems.length > 0 && (
              <StructureChecklistPanel items={checklistItems} />
            )}
            {message.text && (
              <References sources={sources} onOpenSource={onOpenSource} />
            )}
            {showFollowUps && (
              <div className="mt-3 pt-3 border-t border-separator/40">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-label-tertiary mb-2">
                  Suggested follow-up questions
                </div>
                <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                  {followUps.map((q) => (
                    <button
                      key={q}
                      type="button"
                      disabled={followUpsDisabled}
                      onClick={() => onFollowUp?.(q)}
                      title="Send this question"
                      className={
                        "text-left text-sm px-3 py-2 rounded-xl border border-accent/25 " +
                        "bg-accent/5 text-accent hover:bg-accent/10 hover:border-accent/40 " +
                        "transition disabled:opacity-50 disabled:cursor-not-allowed"
                      }
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {showActions && (
            <div className="flex flex-col gap-1 border-t border-separator px-3 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center text-label-tertiary flex-wrap">
                  <ActionButton
                    onClick={() => copy("text")}
                    label={copied === "text" ? "Copied" : "Copy"}
                    icon="⧉"
                  />
                  <Divider />
                  <ActionButton
                    onClick={() => copy("clean")}
                    label={copied === "clean" ? "Copied" : "Copy Without Links"}
                    icon="⧉"
                  />
                  <Divider />
                  <ActionButton
                    onClick={() =>
                      message.turnId != null
                        ? window.open(api.chatTurnExportUrl(message.turnId), "_blank")
                        : downloadMarkdown(message.text)
                    }
                    label="Export DOCX"
                    icon="⬇"
                  />
                  {message.turnId != null && (
                    <>
                      <Divider />
                      <ActionButton
                        onClick={() => void sendToMsa()}
                        label={msaBusy ? "Sending…" : "Send to MSA"}
                        icon="↗"
                      />
                    </>
                  )}
                </div>

                {message.turnId != null && (
                  <div className="flex items-center gap-1">
                    <FeedbackButton
                      active={message.feedback === "up"}
                      tone="up"
                      onClick={() => onRate(message.turnId!, "up", message.feedback ?? null)}
                    />
                    <FeedbackButton
                      active={message.feedback === "down"}
                      tone="down"
                      onClick={() => onRate(message.turnId!, "down", message.feedback ?? null)}
                    />
                    <button
                      type="button"
                      title={
                        message.feedbackComment
                          ? "Edit detailed feedback"
                          : "Share detailed feedback"
                      }
                      onClick={() => onDetailedFeedback(message.turnId!)}
                      className={`ml-0.5 rounded-full px-1.5 py-1 text-xs transition-all ${
                        message.feedbackComment
                          ? "bg-accent/15 text-accent ring-1 ring-accent/40"
                          : "text-label-tertiary hover:bg-bg-accent hover:text-label"
                      }`}
                    >
                      ⓘ
                    </button>
                  </div>
                )}
              </div>
              {msaMsg && (
                <div className="text-[11px] text-label-tertiary px-1 pb-0.5">{msaMsg}</div>
              )}
            </div>
          )}
        </div>
        )}
      </div>
    </div>
  );
}

function ActionButton({
  onClick,
  label,
  icon,
}: {
  onClick: () => void;
  label: string;
  icon: string;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium hover:bg-bg-accent hover:text-label transition-colors"
    >
      <span aria-hidden>{icon}</span>
      {label}
    </button>
  );
}

function Divider() {
  return <span className="mx-0.5 h-4 w-px bg-separator" aria-hidden />;
}

function FeedbackButton({
  active,
  tone,
  onClick,
}: {
  active: boolean;
  tone: "up" | "down";
  onClick: () => void;
}) {
  const up = tone === "up";
  const activeCls = up
    ? "bg-accent/15 text-accent ring-1 ring-accent/40"
    : "bg-red-500/15 text-red-500 ring-1 ring-red-500/40";
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      title={up ? "Helpful" : "Not helpful"}
      className={`rounded-full px-2 py-1 text-sm transition-all ${
        active ? `${activeCls} scale-105` : "text-label-tertiary hover:bg-bg-accent hover:text-label"
      }`}
    >
      {up ? "👍" : "👎"}
    </button>
  );
}
