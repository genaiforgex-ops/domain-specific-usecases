import { useSyncExternalStore } from 'react';

// Light/dark theming. The choice is persisted in localStorage; until the user
// picks one, we follow the OS `prefers-color-scheme` (and keep following it live).
// The effective theme is applied as `data-theme` on <html>, which drives the
// CSS variables in index.css. The initial paint is handled by an inline script
// in index.html so there's no flash of the wrong theme.

export type Theme = 'light' | 'dark';
const KEY = 'os.theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

function systemTheme(): Theme {
  return window.matchMedia?.(DARK_QUERY).matches ? 'dark' : 'light';
}

function stored(): Theme | null {
  const v = localStorage.getItem(KEY);
  return v === 'light' || v === 'dark' ? v : null;
}

export function currentTheme(): Theme {
  return stored() ?? systemTheme();
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'dark' ? '#181b34' : '#f6f7fb');
}

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function setTheme(theme: Theme) {
  localStorage.setItem(KEY, theme);
  applyTheme(theme);
  emit();
}

export function toggleTheme() {
  setTheme(currentTheme() === 'dark' ? 'light' : 'dark');
}

// While the user hasn't chosen explicitly, track the OS preference live.
window.matchMedia?.(DARK_QUERY).addEventListener('change', () => {
  if (!stored()) {
    applyTheme(systemTheme());
    emit();
  }
});

export function useTheme(): Theme {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    currentTheme,
    currentTheme,
  );
}
