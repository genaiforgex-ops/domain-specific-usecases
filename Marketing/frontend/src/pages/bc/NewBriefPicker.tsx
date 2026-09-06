import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, FileText, Files, Layers, ArrowRight } from 'lucide-react';
import { Page, PageHeader } from '../../components/layout/Page';
import { SIZE_META } from '../../lib/briefSpec';
import type { BriefSize } from '../../lib/types';
import { cn } from '../../lib/cn';

const SIZE_ICON: Record<BriefSize, typeof FileText> = { small: FileText, medium: Files, large: Layers };
const SIZES: BriefSize[] = ['small', 'medium', 'large'];

// Step one of authoring: pick a size. The cards animate out and route to the
// matching template form — nothing else competes for attention on this screen.
export default function NewBriefPicker() {
  const nav = useNavigate();
  const [selected, setSelected] = useState<BriefSize | null>(null);

  const choose = (s: BriefSize) => {
    if (selected) return;
    setSelected(s);
    setTimeout(() => nav(`/briefs/new/${s}`), 220);
  };

  return (
    <Page>
      <button
        onClick={() => nav('/briefs')}
        className="inline-flex items-center gap-1.5 text-footnote text-label-secondary hover:text-label mb-3 focus-ring rounded px-1"
      >
        <ArrowLeft size={15} /> My Briefs
      </button>
      <PageHeader eyebrow="Product Lead" title="New Brief" subtitle="Choose a size to start — the template guides the rest." />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-2">
        {SIZES.map((s, i) => {
          const Icon = SIZE_ICON[s];
          const isSel = selected === s;
          return (
            <motion.button
              key={s}
              onClick={() => choose(s)}
              initial={{ opacity: 0, y: 14 }}
              animate={
                selected == null
                  ? { opacity: 1, y: 0, scale: 1 }
                  : isSel
                    ? { opacity: 1, y: 0, scale: 1.04 }
                    : { opacity: 0, scale: 0.95 }
              }
              transition={{ duration: 0.22, delay: selected ? 0 : i * 0.05, ease: [0.4, 0, 0.2, 1] }}
              whileHover={selected ? undefined : { y: -3 }}
              className={cn(
                'group text-left rounded-2xl border p-6 min-h-[200px] flex flex-col focus-ring transition-shadow',
                isSel ? 'border-accent bg-[color:var(--color-accent-soft)] shadow-elevated' : 'border-separator bg-bg-tertiary hover:shadow-elevated',
              )}
            >
              <span className={cn('grid place-items-center h-14 w-14 rounded-xl mb-4', isSel ? 'bg-accent text-white' : 'bg-bg-secondary text-label-secondary group-hover:text-accent')}>
                <Icon size={26} />
              </span>
              <p className="text-title-3 font-bold text-label">{SIZE_META[s].label}</p>
              <p className="mt-1 text-subheadline text-label-secondary flex-1">{SIZE_META[s].blurb}</p>
              <span className="mt-4 inline-flex items-center gap-1.5 text-footnote font-semibold text-accent">
                Start {SIZE_META[s].label.toLowerCase()} brief
                <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
              </span>
            </motion.button>
          );
        })}
      </div>
    </Page>
  );
}
