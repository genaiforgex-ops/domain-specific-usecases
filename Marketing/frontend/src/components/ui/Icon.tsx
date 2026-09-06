import * as Lucide from 'lucide-react';
import type { LucideProps } from 'lucide-react';

// Resolve a lucide icon by name (nav config stores names as strings).
export function Icon({ name, ...props }: { name: string } & LucideProps) {
  const C = (Lucide as unknown as Record<string, React.ComponentType<LucideProps>>)[name] ?? Lucide.Circle;
  return <C {...props} />;
}
