type IconProps = { size?: number; className?: string };

const defaults = { size: 20, className: "" };

export function IconHome(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H5a1 1 0 01-1-1V9.5z" />
      <path d="M9 21V12h6v9" />
    </svg>
  );
}

export function IconQueue(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <rect x="3" y="4" width="18" height="4" rx="1" />
      <rect x="3" y="10" width="18" height="4" rx="1" />
      <rect x="3" y="16" width="12" height="4" rx="1" />
    </svg>
  );
}

export function IconShield(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <path d="M12 2l8 4v6c0 5.25-3.5 9.74-8 11-4.5-1.26-8-5.75-8-11V6l8-4z" />
    </svg>
  );
}

export function IconBuilding(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <path d="M4 21V5a1 1 0 011-1h5v17M14 21V9h5a1 1 0 011 1v11M9 9h1M9 13h1M9 17h1M16 13h1M16 17h1" />
    </svg>
  );
}

export function IconChart(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <path d="M4 20V10M10 20V4M16 20v-8M22 20H2" />
    </svg>
  );
}

export function IconRobot(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <rect x="4" y="8" width="16" height="11" rx="2" />
      <path d="M12 8V4M9 4h6" />
      <path d="M4 13H2M22 13h-2" />
      <path d="M9 13h.01M15 13h.01" />
    </svg>
  );
}

export function IconSearch(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-4-4" />
    </svg>
  );
}

export function IconAudit(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" />
      <path d="M14 2v6h6M10 13l2 2 4-5" />
    </svg>
  );
}

export function IconSettings(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
}

export function IconSparkle(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M12 2l1.5 5.5L19 9l-5.5 1.5L12 16l-1.5-5.5L5 9l5.5-1.5L12 2zM5 14l.8 2.8L8.6 18l-2.8.8L5 21.6l-.8-2.8L1.4 18l2.8-.8L5 14zm14 0l.8 2.8 2.8.8-2.8.8-.8 2.8-.8-2.8-2.8-.8 2.8-.8.8-2.8z" />
    </svg>
  );
}

export function IconSun(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

export function IconMoon(p: IconProps) {
  const { size, className } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <path d="M21 12.79A9 9 0 1111.21 3a7 7 0 109.79 9.79z" />
    </svg>
  );
}

export function IconChevron(p: IconProps & { direction?: "left" | "right" }) {
  const { size, className, direction = "right" } = { ...defaults, ...p };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden style={{ transform: direction === "left" ? "rotate(180deg)" : undefined }}>
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}
