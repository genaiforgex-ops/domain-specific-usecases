import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Search, Bell, ChevronDown, Power, CheckCheck, Menu, Check, Repeat, Sparkles } from 'lucide-react';
import { useApp } from '../../state/AppContext';
import { ROLES } from '../../lib/roles';
import { APP_NAME } from '../../lib/brand';
import { timeAgo } from '../../lib/select';
import { Avatar, CountBadge, EmptyState } from '../ui/primitives';
import { ThemeToggle } from '../ui/ThemeToggle';
import { useAutoDismiss } from '../../lib/useAutoDismiss';
import { cn } from '../../lib/cn';

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { role, user, peopleByRole, logout, switchRole, killSwitch,
    notifications, notifUnread, refreshNotifications, markNotificationsSeen } = useApp();
  const nav = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [scrolled, setScrolled] = useState(false);

  // Lift the bar with a hairline shadow once content scrolls beneath it, so the
  // chrome reads as a distinct plane instead of floating flat over the page.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // Both dropdowns auto-close after a spell of inactivity (a UI-fix request);
  // closing the notifications panel also marks everything shown as seen.
  useAutoDismiss(notifOpen, () => { setNotifOpen(false); markNotificationsSeen(); });
  useAutoDismiss(menuOpen, () => setMenuOpen(false));

  if (!role) return null;

  const r = ROLES[role];
  // The signed-in user, with the directory as a graceful fallback before it loads.
  const myName = user?.full_name ?? peopleByRole[role]?.full_name ?? r.title;

  const openNotifs = () => { setNotifOpen(true); refreshNotifications(); };
  // Closing the panel clears the unread badge (everything shown is now "seen").
  const closeNotifs = () => { setNotifOpen(false); markNotificationsSeen(); };
  const openNotification = (briefId: string) => {
    closeNotifs();
    nav(role === 'DS' ? `/assets/${briefId}` : `/briefs/${briefId}`);
  };
  // Route the query into the role-scoped Search page, which does the actual match.
  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    const term = query.trim();
    nav(term ? `/search?q=${encodeURIComponent(term)}` : '/search');
  };

  return (
    <header
      className={cn(
        'sticky top-0 z-40 h-16 bg-bg flex items-center gap-3 px-4 transition-shadow duration-base ease-standard',
        scrolled && 'shadow-card',
      )}
    >
      <button
        onClick={onMenu}
        className="lg:hidden grid place-items-center h-10 w-10 -ml-1 rounded-full text-label-secondary hover:bg-[color:var(--color-fill-quaternary)] focus-ring"
        aria-label="Open menu"
      >
        <Menu size={20} />
      </button>

      {/* Brand — gradient mark + wordmark, echoing the sign-in lockup. */}
      <div className="flex items-center gap-2.5 shrink-0">
        <span
          className="grid h-9 w-9 place-items-center rounded-xl text-white shadow-card ring-1 ring-inset ring-white/25"
          style={{ background: 'linear-gradient(150deg, var(--color-accent) 0%, #3b1e8f 100%)' }}
          aria-hidden
        >
          <Sparkles size={18} />
        </span>
        <p className="hidden md:block text-headline font-extrabold tracking-tight text-label whitespace-nowrap">
          {APP_NAME}
        </p>
      </div>

      {/* Global search — wide and centered, "search for anything". */}
      <form onSubmit={submitSearch} className="flex-1 flex justify-center px-2">
        <div className="relative w-full max-w-2xl">
          <Search size={17} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-label-tertiary pointer-events-none" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for anything…"
            aria-label="Search"
            className="w-full h-10 pl-10 pr-3.5 rounded-lg bg-bg-secondary border border-separator text-subheadline text-label placeholder:text-label-tertiary outline-none focus-ring transition-shadow hover:bg-fill-quaternary"
          />
        </div>
      </form>

      {killSwitch && (
        <span className="hidden sm:inline-flex items-center gap-1.5 h-8 px-3 rounded-full bg-error text-white text-caption font-bold">
          <Power size={13} /> Kill-switch on
        </span>
      )}

      {/* Light / dark theme */}
      <ThemeToggle />

      {/* Notifications */}
      <div className="relative">
        <button
          onClick={() => (notifOpen ? closeNotifs() : openNotifs())}
          className="relative grid place-items-center h-10 w-10 rounded-full text-label-secondary hover:bg-[color:var(--color-fill-quaternary)] focus-ring"
          aria-label={`Notifications${notifUnread > 0 ? `, ${notifUnread} unread` : ''}`}
        >
          <Bell size={19} />
          {notifUnread > 0 && (
            <span className="absolute top-1.5 right-1.5">
              <CountBadge n={notifUnread} tone="error" />
            </span>
          )}
        </button>

        <AnimatePresence>
          {notifOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={closeNotifs} />
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.98 }}
                transition={{ type: 'spring', stiffness: 420, damping: 30 }}
                className="absolute right-0 mt-2 w-[22rem] max-w-[calc(100vw-2rem)] z-50 rounded-xl glass shadow-elevated p-1.5 origin-top-right"
              >
                <div className="flex items-center justify-between px-2.5 pt-2 pb-1.5">
                  <p className="text-caption font-semibold text-label-tertiary uppercase tracking-wide">
                    Notifications
                  </p>
                  {notifUnread > 0 && (
                    <button
                      onClick={markNotificationsSeen}
                      className="inline-flex items-center gap-1 text-caption font-medium text-accent hover:underline focus-ring rounded px-1"
                    >
                      <CheckCheck size={13} /> Mark all read
                    </button>
                  )}
                </div>

                {notifications.length === 0 ? (
                  <EmptyState
                    compact
                    icon={<Bell size={22} />}
                    title="You're all caught up"
                    body="Updates on your briefs will show up here."
                  />
                ) : (
                  <ul className="max-h-[60vh] overflow-y-auto">
                    {notifications.map((n) => (
                      <li key={n.id}>
                        <button
                          onClick={() => openNotification(n.brief_id)}
                          className="w-full text-left flex gap-2.5 px-2.5 py-2 rounded-md hover:bg-[color:var(--color-fill-quaternary)] focus-ring"
                        >
                          <span
                            className={cn(
                              'mt-1.5 h-2 w-2 rounded-full shrink-0',
                              n.read ? 'bg-transparent' : 'bg-accent',
                            )}
                            aria-hidden
                          />
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center justify-between gap-2">
                              <span className="text-footnote font-semibold text-label truncate">{n.title}</span>
                              <span className="text-caption2 text-label-tertiary shrink-0">{timeAgo(n.at)}</span>
                            </span>
                            <span className="block text-caption text-label-secondary truncate">{n.brief_title}</span>
                            <span className="block text-caption text-label-tertiary truncate">
                              {n.body} · {n.actor_name}
                            </span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>

      {/* Identity + sign out */}
      <div className="relative">
        <button
          onClick={() => setMenuOpen((o) => !o)}
          className="flex items-center gap-2 h-10 pl-1 pr-2.5 rounded-full hover:bg-[color:var(--color-fill-quaternary)] focus-ring"
        >
          <Avatar name={myName} ring={r.accent} size={32} />
          <span className="hidden sm:block text-left leading-tight">
            <span className="block text-footnote font-semibold text-label">{myName}</span>
            <span className="block text-caption text-label-tertiary">{r.title}</span>
          </span>
          <ChevronDown size={15} className="text-label-tertiary" />
        </button>

        <AnimatePresence>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.98 }}
                transition={{ type: 'spring', stiffness: 420, damping: 30 }}
                className="absolute right-0 mt-2 w-64 z-50 rounded-xl glass shadow-elevated p-1.5 origin-top-right"
              >
                <div className="flex items-center gap-2.5 px-2.5 py-2">
                  <Avatar name={myName} ring={r.accent} size={28} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-footnote font-semibold text-label truncate">{myName}</span>
                    <span className="block text-caption text-label-tertiary truncate">{r.title}</span>
                  </span>
                </div>

                {(user?.roles?.length ?? 0) > 1 && (
                  <div className="hairline-t mt-1.5 pt-1.5">
                    <p className="flex items-center gap-1.5 px-2.5 pb-1 text-caption font-semibold text-label-tertiary uppercase tracking-wide">
                      <Repeat size={12} /> Switch role
                    </p>
                    {user!.roles.map((rid) => (
                      <button
                        key={rid}
                        onClick={async () => {
                          setMenuOpen(false);
                          if (rid === role) return;
                          try {
                            await switchRole(rid);
                            nav(ROLES[rid].home);
                          } catch {
                            /* stay put; a failed switch keeps the current role */
                          }
                        }}
                        className="w-full text-left flex items-center gap-2 px-2.5 py-2 rounded-md text-footnote text-label font-medium hover:bg-[color:var(--color-fill-quaternary)]"
                      >
                        <Check
                          size={15}
                          className={cn('shrink-0', rid === role ? 'text-accent' : 'text-transparent')}
                        />
                        {ROLES[rid].title}
                      </button>
                    ))}
                  </div>
                )}

                <div className="hairline-t mt-1.5 pt-1.5">
                  <button
                    onClick={async () => {
                      setMenuOpen(false);
                      await logout();
                      nav('/');
                    }}
                    className="w-full text-left px-2.5 py-2 rounded-md text-footnote text-error font-medium hover:bg-[color:var(--color-fill-quaternary)]"
                  >
                    Sign out
                  </button>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>
    </header>
  );
}
