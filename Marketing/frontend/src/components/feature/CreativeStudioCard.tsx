import { useState } from 'react';
import { Pencil } from 'lucide-react';
import { Button } from '../ui/Button';
import { CreativeCard } from './CreativeCard';
import { CreativeEditor } from './CreativeEditor';
import type { Creative } from '../../lib/types';

// One creative inside the Copy Studio: a clean read-only preview with a single
// Edit action. Editing + version history live in the CreativeEditor popup, so
// the studio panel itself stays uncluttered.
export function CreativeStudioCard({
  briefId,
  creative,
  index,
  onUpdated,
}: Readonly<{
  briefId: string;
  creative: Creative;
  index: number;
  onUpdated: (c: Creative) => void;
}>) {
  const [editorOpen, setEditorOpen] = useState(false);

  return (
    <div className="rounded-lg border border-separator overflow-hidden">
      <CreativeCard c={creative} index={index} />
      <div className="flex justify-end px-4 py-2.5 border-t border-separator bg-bg-secondary">
        <Button variant="tinted" size="sm" onClick={() => setEditorOpen(true)}>
          <Pencil size={14} /> Edit
        </Button>
      </div>

      <CreativeEditor
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        briefId={briefId}
        creative={creative}
        index={index}
        onUpdated={onUpdated}
      />
    </div>
  );
}
