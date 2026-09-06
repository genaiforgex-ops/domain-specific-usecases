import { type ReactNode, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { cn } from '../../lib/cn';

type Size = 'sm' | 'md' | 'lg' | 'xl';

const WIDTHS: Record<Size, string> = {
  sm: 'max-w-md',
  md: 'max-w-2xl',
  lg: 'max-w-4xl',
  xl: 'max-w-6xl',
};

// A centered modal dialog — dim+blur scrim, rounded card, scrollable body, and an
// optional sticky footer. The same pattern as the image-versioning dialog; use
// this (not Sheet) when the content should sit in the middle of the screen.
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: Size;
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
          className="fixed inset-x-0 bottom-0 top-0 sm:top-16 z-30 flex items-center justify-center p-4 sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <div className="absolute inset-0 bg-black/45 backdrop-blur-sm" onClick={onClose} aria-hidden />
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={{ opacity: 0, scale: 0.98, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 8 }}
            transition={{ type: 'spring', stiffness: 380, damping: 34 }}
            className={cn(
              'relative w-full max-h-[90vh] flex flex-col rounded-2xl bg-bg shadow-elevated overflow-hidden',
              WIDTHS[size],
            )}
          >
            <header className="flex items-center justify-between gap-3 px-5 py-3.5 hairline-b shrink-0">
              <div className="text-headline text-label">{title}</div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="grid place-items-center h-9 w-9 -mr-1.5 rounded-full text-label-secondary hover:bg-fill-quaternary focus-ring shrink-0"
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
