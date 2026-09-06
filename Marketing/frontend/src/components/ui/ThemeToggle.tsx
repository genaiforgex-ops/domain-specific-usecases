import { Moon, Sun } from 'lucide-react';
import { useTheme, toggleTheme } from '../../lib/theme';
import { cn } from '../../lib/cn';

// One-tap light/dark switch. Shows the theme you'll switch *to*.
export function ThemeToggle({ className }: { className?: string }) {
  const dark = useTheme() === 'dark';
  return (
    <button
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      className={cn(
        'grid place-items-center h-10 w-10 rounded-full text-label-secondary hover:bg-[color:var(--color-fill-quaternary)] focus-ring',
        className,
      )}
    >
      {dark ? <Sun size={19} /> : <Moon size={19} />}
    </button>
  );
}
