import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/cn';

type Variant = 'filled' | 'tinted' | 'plain' | 'destructive' | 'glass';
type Size = 'sm' | 'md' | 'lg';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

// Monday buttons are rectangular (small radius), medium weight, flat fills.
const base =
  'inline-flex items-center justify-center gap-2 font-sans font-semibold rounded-md select-none focus-ring transition-colors duration-fast ease-standard disabled:opacity-40 disabled:pointer-events-none';

const variants: Record<Variant, string> = {
  filled: 'bg-[#6366f1] text-white hover:opacity-90',
  tinted: 'bg-[color:var(--color-accent-soft)] text-accent hover:brightness-105',
  plain: 'text-accent hover:bg-[color:var(--color-fill-quaternary)]',
  destructive: 'bg-error text-[color:var(--color-on-accent)] hover:opacity-90',
  // Secondary/outline button — white/dark button with a grey border.
  glass: 'bg-bg border border-separator text-label hover:bg-fill-quaternary',
};

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-footnote',
  md: 'h-9 px-4 text-subheadline',
  lg: 'h-11 px-5 text-callout',
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant = 'filled', size = 'md', className, children, ...rest }, ref) => (
    <motion.button
      ref={ref}
      whileTap={{ scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      className={cn(base, variants[variant], sizes[size], className)}
      {...(rest as any)}
    >
      {children}
    </motion.button>
  ),
);
Button.displayName = 'Button';
