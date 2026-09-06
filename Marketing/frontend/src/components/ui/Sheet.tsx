import { type ReactNode, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { cn } from '../../lib/cn';

// Slides up from the bottom-right as a side sheet on desktop, bottom sheet on
// mobile. Rounded top corners, grabber, dim+blur scrim — per HIG sheet pattern.
export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    if (open) document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-x-0 bottom-0 top-0 sm:top-16 z-30 flex items-end sm:items-stretch sm:justify-end"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div
            className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={{ y: '100%', x: 0 }}
            animate={{ y: 0, x: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', stiffness: 380, damping: 38 }}
            className={cn(
              'relative w-full sm:h-full bg-bg flex flex-col',
              'rounded-t-2xl sm:rounded-t-none sm:rounded-l-2xl shadow-elevated',
              'max-h-[92vh] sm:max-h-none',
              wide ? 'sm:w-[560px]' : 'sm:w-[460px]',
            )}
          >
            <div className="sm:hidden mx-auto mt-2 mb-1 h-1 w-9 rounded-full bg-label-tertiary" />
            <header className="flex items-center justify-between px-5 py-3.5 hairline-b shrink-0">
              <div className="text-headline text-label">{title}</div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="grid place-items-center h-9 w-9 -mr-2 rounded-full text-label-secondary hover:bg-[color:var(--color-fill-quaternary)] focus-ring"
              >
                <X size={18} />
              </button>
            </header>
            <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
            {footer && <footer className="px-5 py-3.5 hairline-t shrink-0 bg-bg-secondary">{footer}</footer>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
