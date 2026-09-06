import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { Toasts } from './Toasts';

export function AppShell() {
  const [drawer, setDrawer] = useState(false);

  return (
    <div className="relative min-h-screen flex flex-col bg-bg-secondary">
      {/* Full-width top bar — owns the brand and global search. */}
      <Topbar onMenu={() => setDrawer(true)} />

      {/* Hairline under the top bar — starts after the slim icon rail (68px) so
          only that leftmost rail fuses with the navbar; the content keeps the
          divider across its top. */}
      <div
        aria-hidden
        className="pointer-events-none fixed top-16 right-0 left-0 z-40 h-px bg-separator lg:left-[68px]"
      />

      <div className="flex flex-1 min-w-0">
        {/* Desktop: the slim icon rail, pinned below the bar. */}
        <div className="hidden lg:flex fixed left-0 top-16 bottom-0 z-30">
          <Sidebar />
        </div>

        {/* Mobile drawer */}
        <AnimatePresence>
          {drawer && (
            <div className="lg:hidden fixed inset-0 z-50">
              <motion.div
                className="absolute inset-0 bg-black/30"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setDrawer(false)}
              />
              <motion.aside
                initial={{ x: '-100%' }}
                animate={{ x: 0 }}
                exit={{ x: '-100%' }}
                transition={{ type: 'spring', stiffness: 380, damping: 38 }}
                className="absolute left-0 top-0 h-full"
              >
                <Sidebar drawer onNavigate={() => setDrawer(false)} />
              </motion.aside>
            </div>
          )}
        </AnimatePresence>

        {/* Reserve the rail's footprint on desktop so content never sits under it. */}
        <main className="relative z-10 flex-1 min-w-0 lg:pl-[68px]">
          <Outlet />
        </main>
      </div>

      <Toasts />
    </div>
  );
}
