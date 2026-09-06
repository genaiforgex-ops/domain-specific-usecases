import { useEffect, useRef } from 'react';

/**
 * Auto-close an open popover after `delayMs` of user inactivity. The countdown
 * starts when `open` turns true and resets on any pointer/key/scroll activity, so
 * an engaged user keeps the panel open and an idle one has it dismissed for them.
 *
 * Used for the top-bar notifications panel and the identity (avatar) menu.
 */
export function useAutoDismiss(open: boolean, onClose: () => void, delayMs = 7000) {
  // Keep the latest onClose without re-arming the timer every render.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    let timer = window.setTimeout(() => onCloseRef.current(), delayMs);
    const reset = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => onCloseRef.current(), delayMs);
    };
    const events: (keyof DocumentEventMap)[] = [
      'mousemove',
      'mousedown',
      'keydown',
      'touchstart',
      'scroll',
      'wheel',
    ];
    for (const e of events) document.addEventListener(e, reset, { passive: true });
    return () => {
      window.clearTimeout(timer);
      for (const e of events) document.removeEventListener(e, reset);
    };
  }, [open, delayMs]);
}
