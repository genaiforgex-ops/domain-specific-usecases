import { sectionsFor } from '../../lib/briefSpec';
import type { Brief } from '../../lib/types';
import { BriefReferenceGallery } from './BriefReferenceGallery';

/**
 * Long-form reading view of a brief — a calm Notion/Medium-style document rather
 * than a form dump. A narrow reading column, generous line-height, section
 * headings and quiet field labels. Empty fields are dropped so the page reads as
 * prose, not a sparse table.
 */
export function BriefDocument({ brief }: { brief: Brief }) {
  const sections = sectionsFor(brief.brief_type)
    .map((s) => ({
      ...s,
      fields: s.fields.filter((f) => (brief[f.key] ?? '').toString().trim()),
    }))
    .filter((s) => s.fields.length);

  const references = brief.reference_images ?? [];

  if (!sections.length && !references.length) {
    return (
      <p className="text-subheadline text-label-tertiary">This brief has no content yet.</p>
    );
  }

  return (
    <article className="w-full px-1">
      {sections.map((section, si) => (
        <section key={section.title} className={si === 0 ? '' : 'mt-10'}>
          <h2 className="text-title-3 font-bold text-label tracking-tight mb-5 pb-2 border-b border-separator">
            {section.title}
          </h2>
          <div className="space-y-6">
            {section.fields.map((f) => {
              const value = brief[f.key]!.toString();
              const long = value.length > 80 || value.includes('\n');
              return (
                <div key={f.key} className={long ? '' : 'sm:flex sm:gap-6'}>
                  <p className="text-caption font-semibold uppercase tracking-wide text-label-tertiary mb-1.5 sm:mb-0 sm:w-44 sm:shrink-0 sm:pt-0.5">
                    {f.label}
                  </p>
                  <p className="flex-1 text-[17px] leading-[1.75] text-label whitespace-pre-wrap">
                    {value}
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      ))}

      <BriefReferenceGallery briefId={brief.id} images={references} />
    </article>
  );
}
