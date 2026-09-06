import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { EmailReplyComposer } from "@/components/gmail/EmailReplyComposer";
import { GmailMailbox } from "@/components/gmail/GmailMailbox";
import { GmailLogo, Icon } from "@/components/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { api } from "@/lib/api";
import { classNames, formatDate } from "@/lib/utils";
import type { DailyBrief, EmailDraft, GmailSettings, GmailStatus, Task, TaskPriority, TaskStatus } from "@/types";

const PRIORITY_STYLE: Record<TaskPriority, { chip: string; bar: string; label: string }> = {
  P0: { chip: "bg-error/10 text-error border-error/20", bar: "bg-error", label: "P0" },
  P1: { chip: "bg-warning/10 text-warning border-warning/20", bar: "bg-warning", label: "P1" },
  P2: { chip: "bg-accent/10 text-accent border-accent/20", bar: "bg-accent", label: "P2" },
  P3: { chip: "bg-bg-secondary text-label-secondary border-separator/40", bar: "bg-label-tertiary", label: "P3" },
};

const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
  snoozed: "Snoozed",
};

interface DueGroup {
  key: string;
  label: string;
  tasks: Task[];
}

function groupByDue(tasks: Task[]): DueGroup[] {
  const now = new Date();
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const today = start(now);
  const tomorrow = new Date(today.getTime() + 86400000);
  const weekEnd = new Date(today.getTime() + 7 * 86400000);

  const overdue: Task[] = [];
  const todays: Task[] = [];
  const tmr: Task[] = [];
  const week: Task[] = [];
  const later: Task[] = [];
  const undated: Task[] = [];

  tasks.forEach((t) => {
    if (!t.due_date) {
      undated.push(t);
      return;
    }
    const d = new Date(t.due_date);
    if (d < today && t.status !== "done") overdue.push(t);
    else if (d >= today && d < tomorrow) todays.push(t);
    else if (d >= tomorrow && d < new Date(tomorrow.getTime() + 86400000)) tmr.push(t);
    else if (d < weekEnd) week.push(t);
    else later.push(t);
  });

  const groups: DueGroup[] = [
    { key: "overdue", label: "Overdue", tasks: overdue },
    { key: "today", label: "Today", tasks: todays },
    { key: "tomorrow", label: "Tomorrow", tasks: tmr },
    { key: "week", label: "This week", tasks: week },
    { key: "later", label: "Later", tasks: later },
    { key: "undated", label: "No due date", tasks: undated },
  ];
  return groups.filter((g) => g.tasks.length > 0);
}

export function TaskManagerPage() {
  const [brief, setBrief] = useState<DailyBrief | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [gmailSettings, setGmailSettings] = useState<GmailSettings | null>(null);
  const [filter, setFilter] = useState<"all" | "today" | "overdue" | "week">("all");
  const [showCompleted, setShowCompleted] = useState(false);
  const [showEmail, setShowEmail] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [replyTarget, setReplyTarget] = useState<{ threadId: string; messageId: string; draftId?: number } | null>(null);
  const [draftsByTask, setDraftsByTask] = useState<Record<number, EmailDraft>>({});
  const [focus, setFocus] = useState<{ task: Task; secondsLeft: number } | null>(null);

  const refresh = useCallback(async () => {
    const [b, t, gs, gset, drafts] = await Promise.all([
      api.dailyBrief(),
      api.listTasks({ sources: ["email", "manual"], gmailOnly: true }),
      api.gmailStatus().catch(() => null),
      api.gmailSettings().catch(() => null),
      api.listEmailDrafts().catch(() => [] as EmailDraft[]),
    ]);
    setBrief(b);
    setTasks(t);
    setGmailStatus(gs);
    setGmailSettings(gset);
    // Map pending auto-generated drafts to their task so the row can surface "review & approve".
    const byTask: Record<number, EmailDraft> = {};
    for (const d of drafts) {
      if (d.auto_generated && d.task_id != null && d.status !== "sent" && d.status !== "dismissed") {
        byTask[d.task_id] = d;
      }
    }
    setDraftsByTask(byTask);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Focus session timer
  useEffect(() => {
    if (!focus) return;
    if (focus.secondsLeft <= 0) return;
    const id = setTimeout(() => {
      setFocus((f) => (f ? { ...f, secondsLeft: f.secondsLeft - 1 } : f));
    }, 1000);
    return () => clearTimeout(id);
  }, [focus]);

  const visibleTasks = useMemo(() => {
    const now = new Date();
    return tasks.filter((t) => {
      if (!showCompleted && t.status === "done") return false;
      if (filter === "today") {
        if (!t.due_date) return false;
        const d = new Date(t.due_date);
        return d.toDateString() === now.toDateString();
      }
      if (filter === "overdue") {
        if (!t.due_date) return false;
        return new Date(t.due_date) < now && t.status !== "done";
      }
      if (filter === "week") {
        if (!t.due_date) return false;
        const week = new Date(now.getTime() + 7 * 86400000);
        return new Date(t.due_date) <= week;
      }
      return true;
    });
  }, [tasks, filter, showCompleted]);

  const groups = useMemo(() => groupByDue(visibleTasks), [visibleTasks]);

  async function toggleStatus(t: Task) {
    const next = t.status === "done" ? "todo" : "done";
    await api.updateTask(t.id, { status: next });
    refresh();
  }

  async function snooze(t: Task, hours: number) {
    const d = new Date();
    d.setHours(d.getHours() + hours);
    await api.snoozeTask(t.id, d.toISOString());
    refresh();
  }

  async function removeTask(t: Task) {
    await api.deleteTask(t.id);
    refresh();
  }

  async function setPriority(t: Task, p: TaskPriority) {
    await api.updateTask(t.id, { priority: p });
    refresh();
  }

  function openReply(task: Task, draftId?: number) {
    if (task.gmail_thread_id && task.gmail_message_id) {
      setReplyTarget({ threadId: task.gmail_thread_id, messageId: task.gmail_message_id, draftId });
    }
  }

  return (
    <div className="space-y-6 pb-10">
      {/* Hero / brief */}
      <BriefHero
        brief={brief}
        gmailStatus={gmailStatus}
        onAddTask={() => setShowAdd((s) => !s)}
        onIngest={() => setShowEmail((s) => !s)}
      />

      {/* Stat row */}
      <StatRow brief={brief} />

      {/* Focus session */}
      {focus && (
        <FocusSession
          task={focus.task}
          secondsLeft={focus.secondsLeft}
          onCancel={() => setFocus(null)}
          onDone={async () => {
            await api.updateTask(focus.task.id, { status: "done" });
            setFocus(null);
            refresh();
          }}
        />
      )}

      {showAdd && <AddTaskForm onDone={() => { setShowAdd(false); refresh(); }} />}
      {showEmail && (
        <GmailMailbox
          status={gmailStatus}
          settings={gmailSettings}
          onSettingsUpdated={refresh}
          onTasksUpdated={refresh}
          onReply={(threadId, messageId) => setReplyTarget({ threadId, messageId })}
          onClose={() => setShowEmail(false)}
        />
      )}

      {replyTarget && (
        <EmailReplyComposer
          threadId={replyTarget.threadId}
          messageId={replyTarget.messageId}
          draftId={replyTarget.draftId}
          onClose={() => setReplyTarget(null)}
          onSent={refresh}
        />
      )}

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        {(["all", "today", "overdue", "week"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={classNames(
              "px-3 py-1.5 rounded-full text-xs font-medium transition-all",
              filter === f
                ? "bg-accent text-white shadow-sm"
                : "bg-bg text-label-secondary border border-separator/40 hover:border-accent/30 hover:text-accent",
            )}
          >
            {f === "all" ? "All" : f === "today" ? "Today" : f === "overdue" ? "Overdue" : "This week"}
          </button>
        ))}
        <label className="flex items-center gap-2 text-xs text-label-secondary ml-3">
          <input
            type="checkbox"
            checked={showCompleted}
            onChange={(e) => setShowCompleted(e.target.checked)}
            className="rounded"
          />
          Show completed
        </label>
      </div>

      {/* Task groups */}
      <div className="space-y-6">
        {groups.length === 0 && (
          <Card>
            <div className="py-12 text-center">
              <Icon.Sparkles className="w-10 h-10 mx-auto text-accent/40 mb-3" />
              <p className="text-label-secondary font-medium">Nothing here. Inbox zero.</p>
              <p className="text-sm text-label-tertiary mt-1">
                Open Gmail inbox to ingest mail, or add a task manually.
              </p>
            </div>
          </Card>
        )}
        {groups.map((g, gi) => (
          <section key={g.key} className="space-y-2 animate-slide-up" style={{ animationDelay: `${gi * 80}ms` }}>
            <div className="flex items-center gap-2">
              <h2
                className={classNames(
                  "text-sm font-semibold uppercase tracking-wider",
                  g.key === "overdue" ? "text-error" : "text-label-secondary",
                )}
              >
                {g.label}
              </h2>
              <span className="text-xs text-label-tertiary">{g.tasks.length}</span>
            </div>
            <div className="space-y-2">
              {g.tasks.map((t) => (
                <TaskRow
                  key={t.id}
                  task={t}
                  pendingDraft={draftsByTask[t.id] ?? null}
                  onToggle={() => toggleStatus(t)}
                  onSnooze={(hours) => snooze(t, hours)}
                  onDelete={() => removeTask(t)}
                  onPriority={(p) => setPriority(t, p)}
                  onStartFocus={() => setFocus({ task: t, secondsLeft: 25 * 60 })}
                  onReply={() => openReply(t)}
                  onReviewDraft={() => openReply(t, draftsByTask[t.id]?.id)}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function BriefHero({
  brief,
  gmailStatus,
  onAddTask,
  onIngest,
}: {
  brief: DailyBrief | null;
  gmailStatus: GmailStatus | null;
  onAddTask: () => void;
  onIngest: () => void;
}) {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const gmailLine = gmailStatus?.connected
    ? `Gmail connected · ${gmailStatus.email}`
    : gmailStatus?.configured
      ? "Gmail not connected — connect to auto-ingest labelled mail"
      : "Gmail OAuth not configured on server";
  return (
    <PageHeader
      eyebrow={
        <span className="inline-flex items-center gap-2">
          <Icon.Sparkles className="w-4 h-4" aria-hidden />
          Daily brief · {today}
        </span>
      }
      title="Your task manager"
      subtitle={
        <>
          {brief ? brief.summary : "Loading your day…"}
          <span className="mt-2 block text-footnote text-label-tertiary">
            <GmailLogo className="w-3.5 h-3.5 inline mr-1.5 align-text-bottom" aria-hidden />
            {gmailLine}
          </span>
        </>
      }
      actions={
        <div className="flex gap-2 shrink-0 flex-wrap">
          <Link to="/settings?connector=gmail">
            <Button variant="secondary" type="button">
              <GmailLogo className="w-4 h-4 mr-1.5" aria-hidden />
              Gmail settings
            </Button>
          </Link>
          <Button variant="secondary" onClick={onIngest}>
            <GmailLogo className="w-4 h-4 mr-1.5" aria-hidden />
            Gmail inbox
          </Button>
          <Button onClick={onAddTask}>
            <Icon.Plus className="w-4 h-4 mr-1.5" aria-hidden />
            New task
          </Button>
        </div>
      }
    />
  );
}

function StatRow({ brief }: { brief: DailyBrief | null }) {
  const stats = [
    {
      label: "P0 + P1 active",
      value: brief ? brief.counts.P0 + brief.counts.P1 : null,
      icon: Icon.Flag,
      accent: "text-error bg-red-50",
    },
    {
      label: "Overdue",
      value: brief?.overdue ?? null,
      icon: Icon.Clock,
      accent: "text-amber-700 bg-amber-50",
    },
    {
      label: "Gmail (24h)",
      value: brief?.new_gmail_tasks_count ?? null,
      icon: GmailLogo,
      accent: "text-blue-700 bg-blue-50",
    },
    {
      label: "Email drafts",
      value: brief?.pending_email_drafts ?? null,
      icon: Icon.Mail,
      accent: "text-violet-700 bg-violet-50",
    },
    {
      label: "Done today",
      value: brief?.completed_today ?? null,
      icon: Icon.Check,
      accent: "text-emerald-700 bg-emerald-50",
    },
    {
      label: "Streak",
      value: brief ? `${brief.streak_days}d` : null,
      icon: Icon.Flame,
      accent: "text-rose-700 bg-rose-50",
    },
  ];
  return (
    <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {stats.map((s, i) => {
        const I = s.icon;
        return (
          <div
            key={s.label}
            className="rounded-lg bg-bg border border-separator/40 shadow-card p-4 transition-shadow duration-base animate-slide-up"
            style={{ animationDelay: `${60 + i * 60}ms` }}
          >
            <div className="flex items-start justify-between">
              <span className="text-xs font-medium text-label-secondary">{s.label}</span>
              <div className={classNames("rounded-md p-1.5", s.accent)}>
                <I className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3 text-2xl font-semibold text-label tabular-nums">
              {s.value === null ? "—" : s.value}
            </div>
          </div>
        );
      })}
    </section>
  );
}

function FocusSession({
  task,
  secondsLeft,
  onCancel,
  onDone,
}: {
  task: Task;
  secondsLeft: number;
  onCancel: () => void;
  onDone: () => void;
}) {
  const min = Math.floor(secondsLeft / 60);
  const sec = secondsLeft % 60;
  const total = 25 * 60;
  const pct = Math.max(0, Math.min(100, ((total - secondsLeft) / total) * 100));
  return (
    <Card className="border-success/30 bg-success/5 animate-scale-in">
      <div className="flex items-center gap-4">
        <div className="rounded-full p-3 bg-emerald-100 text-emerald-700 animate-pulse-soft">
          <Icon.Focus className="w-6 h-6" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs uppercase tracking-wider text-emerald-700 font-semibold">
            Focus session
          </div>
          <div className="text-sm font-medium text-label truncate">{task.title}</div>
          <div className="mt-2 h-1.5 bg-emerald-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-success transition-all duration-1000"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
        <div className="text-3xl font-semibold tabular-nums text-label">
          {String(min).padStart(2, "0")}:{String(sec).padStart(2, "0")}
        </div>
        <div className="flex flex-col gap-2">
          <Button size="sm" onClick={onDone}>
            <Icon.Check className="w-3.5 h-3.5 mr-1" />
            Done
          </Button>
          <Button size="sm" variant="secondary" onClick={onCancel}>
            End
          </Button>
        </div>
      </div>
    </Card>
  );
}

function TaskRow({
  task,
  pendingDraft,
  onToggle,
  onSnooze,
  onDelete,
  onPriority,
  onStartFocus,
  onReply,
  onReviewDraft,
}: {
  task: Task;
  pendingDraft?: EmailDraft | null;
  onToggle: () => void;
  onSnooze: (hours: number) => void;
  onDelete: () => void;
  onPriority: (p: TaskPriority) => void;
  onStartFocus: () => void;
  onReply: () => void;
  onReviewDraft: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const done = task.status === "done";
  return (
    <div
      className={classNames(
        "group relative rounded-xl bg-bg border border-separator/40 shadow-card transition-all duration-200 animate-fade-in",
        done && "opacity-60",
      )}
    >
      <div className={classNames("absolute left-0 top-0 bottom-0 w-1 rounded-l-xl", PRIORITY_STYLE[task.priority].bar)} />
      <div className="pl-4 pr-3 py-3 flex items-start gap-3">
        <button
          onClick={onToggle}
          className={classNames(
            "shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all hover:scale-110",
            done
              ? "bg-success border-success text-white"
              : "border-separator/60 hover:border-accent",
          )}
          title={done ? "Mark as todo" : "Mark as done"}
        >
          {done && <Icon.Check className="w-3 h-3" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2 flex-wrap">
            <button
              onClick={() => setExpanded((e) => !e)}
              className={classNames(
                "text-sm font-medium text-left text-label hover:text-accent transition-colors",
                done && "line-through text-label-secondary",
              )}
            >
              {task.title}
            </button>
            <Badge className={PRIORITY_STYLE[task.priority].chip}>{task.priority}</Badge>
            {task.tags.map((t) => (
              <Badge key={t} className="bg-bg-secondary text-label-secondary border-separator/40 text-[10px]">
                {t}
              </Badge>
            ))}
            {task.gmail_message_id && (
              <Badge className="bg-bg text-label-secondary border-separator/40 text-[10px] inline-flex items-center gap-1">
                <GmailLogo className="w-3 h-3" />
                <span>Gmail</span>
              </Badge>
            )}
            {pendingDraft && (
              <button
                onClick={onReviewDraft}
                className="inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent hover:bg-accent/20 transition-colors"
                title="An AI reply has been drafted — review and approve before sending"
              >
                <Icon.Sparkles className="w-3 h-3" />
                {pendingDraft.status === "approved" ? "AI reply approved — send" : "AI reply ready — review & approve"}
              </button>
            )}
          </div>
          <div className="text-xs text-label-secondary mt-1 flex items-center gap-2 flex-wrap">
            {task.due_date && (
              <span className="inline-flex items-center gap-1">
                <Icon.Calendar className="w-3 h-3" />
                {formatDate(task.due_date)}
              </span>
            )}
            {task.estimated_minutes != null && (
              <span className="inline-flex items-center gap-1">
                <Icon.Clock className="w-3 h-3" />
                ~{task.estimated_minutes} min
              </span>
            )}
            {task.email_sender && (
              <span className="truncate max-w-xs">from {task.email_sender}</span>
            )}
          </div>
          {expanded && (
            <div className="mt-3 space-y-2 text-sm text-label-secondary animate-fade-in">
              {task.description && <p className="whitespace-pre-wrap">{task.description}</p>}
              {task.ai_rationale && (
                <div className="rounded bg-bg-secondary border border-separator/30 px-3 py-2 text-xs text-label-secondary">
                  <span className="font-semibold text-label-secondary">AI rationale:</span>{" "}
                  {task.ai_rationale}
                </div>
              )}
              {task.email_body && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-accent hover:underline">
                    View source email
                  </summary>
                  <pre className="mt-2 whitespace-pre-wrap font-sans bg-bg-secondary border border-separator/30 rounded p-3">
                    Subject: {task.email_subject}
                    {"\n"}From: {task.email_sender}
                    {"\n\n"}
                    {task.email_body}
                  </pre>
                </details>
              )}
              {task.gmail_thread_id && task.gmail_message_id && (
                <Button size="sm" variant="secondary" onClick={onReply}>
                  <Icon.Mail className="w-3.5 h-3.5 mr-1" />
                  Reply in Gmail
                </Button>
              )}
              <div className="flex flex-wrap gap-1 pt-1">
                {(["P0", "P1", "P2", "P3"] as TaskPriority[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => onPriority(p)}
                    className={classNames(
                      "px-2 py-0.5 rounded text-[10px] font-medium border transition-colors",
                      task.priority === p ? PRIORITY_STYLE[p].chip : "bg-bg border-separator/40 text-label-secondary hover:border-separator/60",
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {!done && (
            <button
              type="button"
              onClick={onStartFocus}
              className="min-w-tap min-h-tap p-2 rounded-md text-label-secondary hover:bg-success/10 hover:text-success transition-colors"
              title="Start 25-min focus session"
              aria-label="Start 25-min focus session"
            >
              <Icon.Focus className="w-4 h-4" />
            </button>
          )}
          {!done && (
            <div className="relative group/menu">
              <button
                type="button"
                className="min-w-tap min-h-tap p-2 rounded-md text-label-secondary hover:bg-warning/10 hover:text-warning transition-colors"
                title="Snooze"
                aria-label="Snooze task"
              >
                <Icon.Pause className="w-4 h-4" />
              </button>
              <div className="absolute right-0 top-full mt-1 bg-bg border border-separator/40 rounded-md shadow-lg py-1 z-10 hidden group-hover/menu:block whitespace-nowrap">
                <button onClick={() => onSnooze(1)} className="block w-full text-left px-3 py-1 text-xs text-label-secondary hover:bg-bg-secondary">
                  Snooze 1h
                </button>
                <button onClick={() => onSnooze(4)} className="block w-full text-left px-3 py-1 text-xs text-label-secondary hover:bg-bg-secondary">
                  Snooze 4h
                </button>
                <button onClick={() => onSnooze(24)} className="block w-full text-left px-3 py-1 text-xs text-label-secondary hover:bg-bg-secondary">
                  Snooze 1d
                </button>
                <button onClick={() => onSnooze(72)} className="block w-full text-left px-3 py-1 text-xs text-label-secondary hover:bg-bg-secondary">
                  Snooze 3d
                </button>
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={onDelete}
            className="min-w-tap min-h-tap p-2 rounded-md text-label-tertiary hover:bg-error/10 hover:text-error transition-colors"
            title="Delete"
            aria-label="Delete task"
          >
            <Icon.Trash className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function AddTaskForm({ onDone }: { onDone: () => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [due, setDue] = useState("");
  const [estimate, setEstimate] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createTask({
        title,
        description: description || undefined,
        due_date: due ? new Date(due).toISOString() : null,
        estimated_minutes: estimate ? Number(estimate) : null,
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Quick add" className="animate-slide-up">
      <form className="space-y-3" onSubmit={submit}>
        <Input
          label="What needs to happen?"
          placeholder="e.g. Send revised MSA to Acme by Thursday"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          autoFocus
        />
        <Textarea
          label="Details (optional)"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Due"
            type="datetime-local"
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
          <Input
            label="Estimate (minutes)"
            type="number"
            min={5}
            step={5}
            value={estimate}
            onChange={(e) => setEstimate(e.target.value)}
          />
        </div>
        <p className="text-xs text-label-secondary">
          Priority is auto-scored from the wording, due date, and signals. You can override it after creation.
        </p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || !title.trim()}>
            {busy ? "Saving…" : "Add task"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
