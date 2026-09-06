import type { SVGProps } from "react";

type Props = SVGProps<SVGSVGElement>;

/** Premium LawGenie brand mark — scales / spark hybrid, uses currentColor. */
export function LawGenieMark({ className, ...rest }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden={rest["aria-hidden"] ?? true}
      {...rest}
    >
      <path
        d="M16 3.8 17.55 7.1l3.1.38-2.35 2.3.65 3.05L16 11.35l-2.95 1.48.65-3.05-2.35-2.3 3.1-.38L16 3.8Z"
        fill="currentColor"
        opacity="0.95"
      />
      <path d="M16 12.4v10.6" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" />
      <path d="M8.8 15h14.4" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" />
      <path
        d="M8.8 15v4.4c0 .95.75 1.7 1.7 1.7h.55"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <path
        d="M23.2 15v4.4c0 .95-.75 1.7-1.7 1.7h-.55"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <path
        d="M7.4 21.1h4.6M20 21.1h4.6"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <path d="M10.8 26h10.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path
        d="M12.6 26v1.05c0 1.15 1.5 1.9 3.4 1.9s3.4-.75 3.4-1.9V26"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

const base: Props = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

export const Icon = {
  ContractReview: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
      <path d="M14 3v6h6" />
      <path d="m9 14 2 2 4-4" />
    </svg>
  ),
  Compare: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M3 6h7M3 12h7M3 18h7" />
      <path d="M14 6h7M14 12h7M14 18h7" />
      <path d="M11 4v16M13 4v16" />
    </svg>
  ),
  Chat: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12Z" />
      <circle cx="9" cy="12" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="15" cy="12" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  ),
  Research: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M4 19V5a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v14" />
      <path d="M4 19a2 2 0 0 0 2 2h13" />
      <path d="M9 7h6M9 11h6M9 15h4" />
    </svg>
  ),
  Workflow: (p: Props) => (
    <svg {...base} {...p}>
      <rect x="3" y="3" width="6" height="6" rx="1" />
      <rect x="15" y="3" width="6" height="6" rx="1" />
      <rect x="9" y="15" width="6" height="6" rx="1" />
      <path d="M6 9v2a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V9" />
      <path d="M12 13v2" />
    </svg>
  ),
  Radar: (p: Props) => (
    <svg {...base} {...p}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <path d="M12 3v9l6 6" />
    </svg>
  ),
  Sparkles: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
    </svg>
  ),
  Shield: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M12 3 4 6v6c0 4.5 3.4 8.4 8 9 4.6-.6 8-4.5 8-9V6l-8-3Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  ),
  Activity: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M3 12h4l3-8 4 16 3-8h4" />
    </svg>
  ),
  BarChart: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M4 20V10M10 20V4M16 20v-6M22 20V8" />
    </svg>
  ),
  Clock: (p: Props) => (
    <svg {...base} {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  ),
  Documents: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  ),
  Paperclip: (p: Props) => (
    <svg {...base} {...p}>
      <path d="m21.44 11.05-8.49 8.49a5.25 5.25 0 0 1-7.43-7.43l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a1.75 1.75 0 0 1-2.47-2.47l8.49-8.48" />
    </svg>
  ),
  ArrowRight: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  ),
  Bolt: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />
    </svg>
  ),
  Inbox: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5 5l-2 7v6a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-6l-2-7H5Z" />
    </svg>
  ),
  Settings: (p: Props) => (
    <svg {...base} {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  ),
  Plug: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M12 22v-5" />
      <path d="M9 8V2M15 8V2" />
      <path d="M7 8h10v4a5 5 0 0 1-10 0V8Z" />
    </svg>
  ),
  Grid: (p: Props) => (
    <svg {...base} {...p}>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  Flag: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M4 22V4" />
      <path d="M4 4h14l-2 4 2 4H4" />
    </svg>
  ),
  Flame: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M12 2c1 4 4 5 4 9a4 4 0 1 1-8 0c0-2 1-3 1-5 1 2 3 1 3-4Z" />
      <path d="M12 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z" />
    </svg>
  ),
  Focus: (p: Props) => (
    <svg {...base} {...p}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </svg>
  ),
  Mail: (p: Props) => (
    <svg {...base} {...p}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 7 9-7" />
    </svg>
  ),
  Plus: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
  Check: (p: Props) => (
    <svg {...base} {...p}>
      <path d="m5 12 5 5L20 7" />
    </svg>
  ),
  Pause: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M9 5v14M15 5v14" />
    </svg>
  ),
  Trash: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" />
      <path d="M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3" />
    </svg>
  ),
  Calendar: (p: Props) => (
    <svg {...base} {...p}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 3v4M16 3v4" />
    </svg>
  ),
  Rocket: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M5 19c-1 .5-2 1.5-2 3 1.5 0 2.5-1 3-2" />
      <path d="M13 5c5 0 8 3 8 8-4 0-7 1-10 4l-3-3c3-3 4-6 5-9Z" />
      <circle cx="15" cy="9" r="1.5" />
      <path d="M9 11l-3 3c-1 1-1 3 0 4 1 1 3 1 4 0l3-3" />
    </svg>
  ),
  Branch: (p: Props) => (
    <svg {...base} {...p}>
      <circle cx="6" cy="6" r="2.2" />
      <circle cx="6" cy="18" r="2.2" />
      <circle cx="18" cy="6" r="2.2" />
      <path d="M6 8.2v7.6" />
      <path d="M18 8.2c0 4-6 4-6 8" />
    </svg>
  ),
  PullRequest: (p: Props) => (
    <svg {...base} {...p}>
      <circle cx="6" cy="6" r="2.2" />
      <circle cx="6" cy="18" r="2.2" />
      <circle cx="18" cy="18" r="2.2" />
      <path d="M6 8.2v7.6" />
      <path d="M18 15.8V11a3 3 0 0 0-3-3h-2" />
      <path d="M15 5l-2 3 2 3" />
    </svg>
  ),
  Code: (p: Props) => (
    <svg {...base} {...p}>
      <path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14" />
    </svg>
  ),
  Send: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M22 2 11 13" />
      <path d="m22 2-7 20-4-9-9-4 20-7Z" />
    </svg>
  ),
  Copy: (p: Props) => (
    <svg {...base} {...p}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h10" />
    </svg>
  ),
  ThumbsUp: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M7 10v11h10a3 3 0 0 0 3-3l1-7h-7l1-5a2 2 0 0 0-4 0L7 10Z" />
      <path d="M3 10h4v11H3z" />
    </svg>
  ),
  ThumbsDown: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M17 14V3H7a3 3 0 0 0-3 3l-1 7h7l-1 5a2 2 0 0 0 4 0l4-4Z" />
      <path d="M21 14h-4V3h4z" />
    </svg>
  ),
  Refresh: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 3v6h-6" />
    </svg>
  ),
  Stop: (p: Props) => (
    <svg {...base} {...p}>
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  ),
  Volume: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M11 5 6 9H2v6h4l5 4V5Z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M18.5 6a9 9 0 0 1 0 12" />
    </svg>
  ),
  VolumeOff: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M11 5 6 9H2v6h4l5 4V5Z" />
      <path d="m22 9-6 6M16 9l6 6" />
    </svg>
  ),
  Mic: (p: Props) => (
    <svg {...base} {...p}>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <path d="M12 17v4M8 21h8" />
    </svg>
  ),
  Pencil: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  ),
  ChevronDown: (p: Props) => (
    <svg {...base} {...p}>
      <path d="m6 9 6 6 6-6" />
    </svg>
  ),
  Users: (p: Props) => (
    <svg {...base} {...p}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
};

/** GitHub octocat-style mark. Monochrome — colour with `text-*`. */
export function GitHubLogo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
      role="img"
      aria-label="GitHub"
      {...props}
    >
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2.17c-3.2.7-3.88-1.36-3.88-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.09-.12-.29-.51-1.47.11-3.05 0 0 .97-.31 3.18 1.18.92-.26 1.91-.39 2.89-.39.98 0 1.97.13 2.89.39 2.21-1.49 3.18-1.18 3.18-1.18.62 1.58.23 2.76.11 3.05.74.8 1.19 1.83 1.19 3.09 0 4.42-2.7 5.4-5.26 5.68.41.35.78 1.04.78 2.1v3.11c0 .31.21.66.8.55C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

/** Brand-coloured Gmail logo. Renders at any size set via className width/height. */
export function GmailLogo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 48 48"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Gmail"
      {...props}
    >
      <path
        fill="#4285F4"
        d="M4 16v22a4 4 0 0 0 4 4h4V21l-8-5Z"
      />
      <path
        fill="#34A853"
        d="M44 16v22a4 4 0 0 1-4 4h-4V21l8-5Z"
      />
      <path
        fill="#EA4335"
        d="M12 42V21l12 8 12-8v21H12Z"
      />
      <path
        fill="#FBBC04"
        d="M36 21 24 29 12 21V8l12 9 12-9v13Z"
      />
      <path
        fill="#C5221F"
        d="M4 8v8l8 5V8L8 6a4 4 0 0 0-4 2Z"
      />
      <path
        fill="#188038"
        d="M44 8v8l-8 5V8l4-2a4 4 0 0 1 4 2Z"
      />
    </svg>
  );
}

export function GoogleDriveLogo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Google Drive" {...props}>
      <path fill="#FFC107" d="M6 32 16 8h16L42 32Z" />
      <path fill="#2196F3" d="M6 32h36l-6 10H12Z" />
      <path fill="#4CAF50" d="M16 8 6 32l6 10 10-24Z" />
    </svg>
  );
}

export function GoogleCalendarLogo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Google Calendar" {...props}>
      <rect x="8" y="10" width="32" height="30" rx="3" fill="#fff" stroke="#4285F4" strokeWidth="2" />
      <path fill="#4285F4" d="M8 16h32v4H8z" />
      <rect x="14" y="6" width="4" height="8" rx="1" fill="#4285F4" />
      <rect x="30" y="6" width="4" height="8" rx="1" fill="#4285F4" />
      <rect x="14" y="24" width="6" height="6" rx="1" fill="#34A853" />
    </svg>
  );
}
