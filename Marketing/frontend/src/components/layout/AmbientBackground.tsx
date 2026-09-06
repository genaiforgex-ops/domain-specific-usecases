import { cn } from '../../lib/cn';

// A slow, liquid-like backdrop: a couple of large blurred fields that drift
// faintly behind the content. Drawn from a single hue (the brand accent) so it
// reads as quiet texture, never a multi-colour wash that competes with content.
// The drift freezes automatically under prefers-reduced-motion (see index.css).
//
// Pass `className="ambient--app"` to dial the intensity down for use behind a
// full working canvas (vs. the bolder sign-in screen default).
export function AmbientBackground({ className }: { className?: string }) {
  return (
    <div className={cn('ambient', className)} aria-hidden>
      <span
        className="ambient__blob"
        style={{ top: '-12%', left: '-8%', height: '46vmax', width: '46vmax', background: 'var(--color-accent)', animation: 'drift-a 26s ease-in-out infinite' }}
      />
      <span
        className="ambient__blob"
        style={{ bottom: '-18%', right: '-10%', height: '52vmax', width: '52vmax', background: 'var(--color-accent)', animation: 'drift-b 32s ease-in-out infinite' }}
      />
    </div>
  );
}
