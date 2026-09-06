import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { cn } from '../../lib/cn';

// The shared "something miraculous is happening" overlay shown while an agent
// works — a glowing orb pulses at the centre, sparkles orbit it, magic dust
// rises, and the status text cycles through what the agent is doing, all inside
// the brand's accent → violet → blue palette. Drop it (absolutely positioned)
// into any `relative` container that wraps a generating AI call and feed it a
// phrase set fit for that step.
//
// Phrase presets for the app's generating calls — keep the voice consistent.
export const MAGIC_PHRASES = {
  brief: [
    'Reading your notes…',
    'Finding the signal…',
    'Pulling out the essentials…',
    'Shaping the brief…',
    'Polishing the details…',
  ],
  copy: [
    'Reading the brief…',
    'Finding the angle…',
    'Writing the headlines…',
    'Sharpening the hook…',
    'Polishing the copy…',
  ],
  image: [
    'Reading the art direction…',
    'Composing the scene…',
    'Setting the light…',
    'Rendering the photograph…',
    'Adding finishing touches…',
  ],
  imageEdit: [
    'Reading your note…',
    'Reworking the image…',
    'Re-lighting the scene…',
    'Rendering the change…',
    'Polishing…',
  ],
} as const;

// Fixed dust particles — start positions, drift and timing precomputed so the
// field looks scattered without re-randomising on every render.
const DUST = Array.from({ length: 14 }, (_, i) => ({
  id: `dust-${i}`,
  left: (i * 53 + 11) % 100,
  drift: ((i * 37) % 40) - 20,
  delay: (i % 7) * 0.32,
  duration: 2.4 + (i % 5) * 0.45,
  size: 4 + (i % 3) * 2,
}));

export function MagicOverlay({
  phrases = MAGIC_PHRASES.brief,
  label = 'Working',
  className,
}: {
  phrases?: readonly string[];
  label?: string;
  className?: string; // override rounding to match the host container
}) {
  const [phrase, setPhrase] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setPhrase((p) => (p + 1) % phrases.length), 1600);
    return () => clearInterval(id);
  }, [phrases.length]);

  return (
    <motion.div
      className={cn('absolute inset-0 z-20 rounded-2xl overflow-hidden grid place-items-center', className)}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      aria-live="polite"
      aria-label={label}
    >
      {/* Frosted, faintly shifting backdrop. */}
      <motion.div
        className="absolute inset-0 backdrop-blur-md"
        style={{ background: 'linear-gradient(135deg, color-mix(in srgb, var(--color-accent) 16%, transparent), color-mix(in srgb, var(--stage-gate) 16%, transparent), color-mix(in srgb, var(--color-accent) 16%, transparent))', backgroundSize: '200% 200%' }}
        animate={{ backgroundPosition: ['0% 0%', '100% 100%', '0% 0%'] }}
        transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Rising magic dust. */}
      {DUST.map((d, i) => (
        <motion.span
          key={d.id}
          className="absolute bottom-0 rounded-full"
          style={{ left: `${d.left}%`, width: d.size, height: d.size, background: i % 2 ? 'var(--stage-gate)' : 'var(--color-accent)' }}
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: -140, x: d.drift, opacity: [0, 0.9, 0], scale: [0.6, 1, 0.4] }}
          transition={{ duration: d.duration, delay: d.delay, repeat: Infinity, ease: 'easeOut' }}
        />
      ))}

      <div className="relative flex flex-col items-center gap-5 px-6 text-center">
        {/* The orb: pulsing glow + orbiting sparkles + a spinning core. */}
        <div className="relative grid place-items-center h-24 w-24">
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ background: 'radial-gradient(circle, color-mix(in srgb, var(--stage-gate) 55%, transparent), transparent 70%)' }}
            animate={{ scale: [1, 1.45, 1], opacity: [0.5, 0.9, 0.5] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
          />
          <motion.span
            className="absolute inset-0"
            animate={{ rotate: 360 }}
            transition={{ duration: 5, repeat: Infinity, ease: 'linear' }}
          >
            {[0, 120, 240].map((deg) => (
              <span
                key={deg}
                className="absolute left-1/2 top-1/2 h-1.5 w-1.5 rounded-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.9)]"
                style={{ transform: `rotate(${deg}deg) translateY(-46px)` }}
              />
            ))}
          </motion.span>
          <motion.span
            className="grid place-items-center h-14 w-14 rounded-2xl text-white shadow-elevated"
            style={{ background: 'linear-gradient(135deg, var(--color-accent), var(--stage-gate))' }}
            animate={{ scale: [1, 1.08, 1], rotate: [0, 8, -8, 0] }}
            transition={{ duration: 2.6, repeat: Infinity, ease: 'easeInOut' }}
          >
            <Sparkles size={26} />
          </motion.span>
        </div>

        <AnimatePresence mode="wait">
          <motion.p
            key={phrase}
            className="text-headline font-semibold text-label"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.4 }}
          >
            {phrases[phrase]}
          </motion.p>
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
