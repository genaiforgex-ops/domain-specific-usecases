import { useEffect, useState } from 'react';
import { Sparkles, Pencil, CheckCircle2 } from 'lucide-react';
import { Card, EmptyState, Pill } from '../ui/primitives';
import { Button } from '../ui/Button';
import { CreativeCard } from './CreativeCard';
import { CopyStudio } from './CopyStudio';
import { api } from '../../lib/api';
import type { Brief, Creative, RoleId } from '../../lib/types';

// Brief → copies. The Copywriter's generate / edit / route / submit flow lives in
// the Copy Studio sheet (opened from here) — the copy counterpart to the
// Designer's image workspace. This panel is the on-page anchor: a read-only
// preview of the copies for every viewer, plus the button that opens the studio.
export function CreativePanel({
  brief,
  role,
  onChanged,
}: Readonly<{
  brief: Brief;
  role: RoleId | null;
  onChanged?: (b: Brief) => void;
}>) {
  // Copies exist from the copywriting stage onward; they're read-only once the
  // brief is handed to design.
  const visible = brief.stage !== 'draft' && brief.stage !== 'brief_review';
  const submitted = visible && brief.stage !== 'copywriting';
  const canWrite = role === 'CW' && brief.stage === 'copywriting';

  const [creatives, setCreatives] = useState<Creative[] | null>(null);
  const [studioOpen, setStudioOpen] = useState(false);

  useEffect(() => {
    if (!visible) {
      setCreatives([]);
      return;
    }
    api.listCreatives(brief.id).then(setCreatives).catch(() => setCreatives([]));
  }, [brief.id, visible]);

  // Hidden until copies exist or the Copywriter can write them.
  if (!visible) return null;
  if (!canWrite && !submitted && creatives !== null && creatives.length === 0) return null;

  const has = (creatives?.length ?? 0) > 0;

  return (
    <Card className={`p-5${canWrite && !has ? ' border-l-4 border-l-accent' : ''}`}>
      <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div>
          <p className="text-subheadline font-bold text-label flex items-center gap-2">
            Copies
            {submitted && (
              <Pill hue="var(--color-success)" icon={<CheckCircle2 size={11} />}>
                {brief.stage === 'design' ? 'Approved' : 'Submitted for approval'}
              </Pill>
            )}
          </p>
          <p className="text-caption text-label-tertiary mt-0.5">
            {submitted
              ? 'Locked — awaiting / cleared the three-lane approval.'
              : canWrite
                ? 'Draft, edit and route the copies in the Copy Studio.'
                : 'Drafted by the Copy Agent.'}
          </p>
        </div>

        {/* The whole write flow opens in the Copy Studio sheet. */}
        {canWrite && (
          <Button variant={has ? 'tinted' : 'filled'} size={has ? 'md' : 'lg'} onClick={() => setStudioOpen(true)}>
            {has ? (
              <><Pencil size={16} /> Edit &amp; submit copies</>
            ) : (
              <><Sparkles size={18} /> Generate copies</>
            )}
          </Button>
        )}
      </div>

      {creatives === null ? (
        <div className="flex justify-center py-10">
          <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
        </div>
      ) : !has ? (
        <EmptyState
          icon={<Sparkles size={26} />}
          title="No copies yet"
          body={canWrite ? 'Open the Copy Studio to generate a set of copies from the brief.' : 'Copies will appear here once the Copywriter writes them.'}
        />
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
          {creatives.map((c, i) => (
            <CreativeCard key={c.id} c={c} index={i} />
          ))}
        </div>
      )}

      {canWrite && (
        <CopyStudio
          open={studioOpen}
          onClose={() => setStudioOpen(false)}
          brief={brief}
          creatives={creatives ?? []}
          onCreatives={setCreatives}
          onSubmitted={(b) => {
            setStudioOpen(false);
            onChanged?.(b);
          }}
        />
      )}
    </Card>
  );
}
