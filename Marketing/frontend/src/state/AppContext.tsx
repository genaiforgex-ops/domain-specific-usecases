import { createContext, useContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { RoleId, BriefInboxItem, AppNotification } from '../lib/types';
import { designStatus } from '../lib/design';
import { api, type AuthUser } from '../lib/api';

interface Toast {
  id: number;
  text: string;
  tone: 'default' | 'success' | 'error';
}

interface AppState {
  role: RoleId | null;
  setRole: (r: RoleId | null) => void;
  user: AuthUser | null;
  peopleByRole: Partial<Record<RoleId, AuthUser>>;
  people: AuthUser[];
  authReady: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => void;
  switchRole: (role: RoleId) => Promise<void>;
  setSession: (u: AuthUser) => void;
  bcInbox: BriefInboxItem[];
  cwCopyPending: number;
  approvalPending: number;
  designPending: number;
  refreshBriefs: () => void;
  notifications: AppNotification[];
  notifUnread: number;
  refreshNotifications: () => void;
  markNotificationsSeen: () => void;
  killSwitch: boolean;
  toggleKillSwitch: (on: boolean) => void;
  toasts: Toast[];
  toast: (text: string, tone?: Toast['tone']) => void;
  dismissToast: (id: number) => void;
}

const Ctx = createContext<AppState | null>(null);

let toastSeq = 1;

export function AppProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<RoleId | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [people, setPeople] = useState<AuthUser[]>([]);
  const [authReady, setAuthReady] = useState(false);
  const [bcInbox, setBcInbox] = useState<BriefInboxItem[]>([]);
  const [cwCopyPending, setCwCopyPending] = useState(0);
  const [approvalPending, setApprovalPending] = useState(0);
  const [designPending, setDesignPending] = useState(0);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [notifUnread, setNotifUnread] = useState(0);
  const [killSwitch, setKillSwitch] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const refreshBriefs = useCallback(() => {
    setBcInbox([]);
    setCwCopyPending(0);
    setApprovalPending(0);
    setDesignPending(0);
    if (role === 'PL') {
      api.briefInbox().then(setBcInbox).catch(() => setBcInbox([]));
    }
    if (role === 'CW') {
      api
        .copywritingQueue()
        .then((q) => setCwCopyPending(q.filter((b) => b.creative_count === 0).length))
        .catch(() => setCwCopyPending(0));
    } else if (role === 'ML' || role === 'PL') {
      api.approvalQueue().then((r) => setApprovalPending(r.length)).catch(() => setApprovalPending(0));
    } else if (role === 'DS') {
      api
        .designQueue()
        .then((q) => setDesignPending(q.filter((b) => designStatus(b) !== 'done').length))
        .catch(() => setDesignPending(0));
    }
  }, [role]);

  useEffect(() => { refreshBriefs(); }, [refreshBriefs]);

  const refreshNotifications = useCallback(() => {
    if (!role) {
      setNotifications([]);
      setNotifUnread(0);
      return;
    }
    api
      .notifications()
      .then((feed) => {
        setNotifications(feed.items);
        setNotifUnread(feed.unread_count);
      })
      .catch(() => {
        setNotifications([]);
        setNotifUnread(0);
      });
  }, [role]);

  useEffect(() => { refreshNotifications(); }, [refreshNotifications]);

  const markNotificationsSeen = useCallback(() => {
    if (notifUnread === 0) return;
    setNotifUnread(0);
    setNotifications((ns) => ns.map((n) => ({ ...n, read: true })));
    api.markNotificationsSeen().catch(() => refreshNotifications());
  }, [notifUnread, refreshNotifications]);

  const setSession = useCallback((u: AuthUser) => {
    setUser(u);
    setRole(u.active_role ?? u.role);
  }, []);

  useEffect(() => {
    api
      .me()
      .then((u) => setSession(u))
      .catch(() => {
        setUser(null);
        setRole(null);
      })
      .finally(() => setAuthReady(true));
    const onUnauthorized = () => {
      setUser(null);
      setRole(null);
    };
    window.addEventListener('app:unauthorized', onUnauthorized);
    return () => window.removeEventListener('app:unauthorized', onUnauthorized);
  }, [setSession]);

  useEffect(() => {
    if (!user) {
      setPeople([]);
      return;
    }
    api.listUsers().then(setPeople).catch(() => setPeople([]));
  }, [user]);

  const login = async (email: string, password: string) => {
    const res = await api.login(email, password);
    setSession(res.user);
    return res.user;
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      /* already out */
    }
    setUser(null);
    setRole(null);
  };

  const switchRole = async (next: RoleId) => {
    const updated = await api.switchRole(next);
    setSession(updated);
  };

  const toast = (text: string, tone: Toast['tone'] = 'default') => {
    const id = toastSeq++;
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  };
  const dismissToast = (id: number) => setToasts((t) => t.filter((x) => x.id !== id));

  const peopleByRole = useMemo(() => {
    const map: Partial<Record<RoleId, AuthUser>> = {};
    for (const p of people) {
      const roles = p.roles?.length ? p.roles : [p.role];
      for (const r of roles) if (!map[r]) map[r] = p;
    }
    return map;
  }, [people]);

  const value: AppState = {
    role,
    setRole,
    user,
    peopleByRole,
    people,
    authReady,
    login,
    logout,
    switchRole,
    setSession,
    bcInbox,
    cwCopyPending,
    approvalPending,
    designPending,
    refreshBriefs,
    notifications,
    notifUnread,
    refreshNotifications,
    markNotificationsSeen,
    killSwitch,
    toggleKillSwitch: (on) => {
      setKillSwitch(on);
      toast(on ? 'Global kill-switch engaged — all generation halted' : 'Kill-switch released', on ? 'error' : 'success');
    },
    toasts,
    toast,
    dismissToast,
  };

  const memo = useMemo(
    () => value,
    [role, user, peopleByRole, authReady, bcInbox, cwCopyPending, approvalPending, designPending, notifications, notifUnread, killSwitch, toasts],
  );
  return <Ctx.Provider value={memo}>{children}</Ctx.Provider>;
}

export function useApp() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
