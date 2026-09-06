import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { useApp } from '../../state/AppContext';

const tone = {
  default: { icon: Info, color: 'var(--color-accent)' },
  success: { icon: CheckCircle2, color: 'var(--color-success)' },
  error: { icon: AlertCircle, color: 'var(--color-error)' },
};

export function Toasts() {
  const { toasts, dismissToast } = useApp();
  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[60] flex flex-col items-center gap-2 w-[calc(100%-2rem)] max-w-sm">
      <AnimatePresence>
        {toasts.map((t) => {
          const T = tone[t.tone];
          const I = T.icon;
          return (
            <motion.button
              key={t.id}
              layout
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 12, scale: 0.96 }}
              transition={{ type: 'spring', stiffness: 400, damping: 32 }}
              onClick={() => dismissToast(t.id)}
              className="w-full flex items-center gap-2 px-4 py-3 rounded-full glass shadow-elevated text-left focus-ring"
            >
              <I size={18} style={{ color: T.color }} className="shrink-0" />
              <span className="text-subheadline font-semibold text-label">{t.text}</span>
            </motion.button>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
