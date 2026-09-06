# Frontend conventions (React 18 + TypeScript + Vite + Tailwind)

Mirror the patterns in `src/lib/api.ts`, `src/types/index.ts`, and `src/components/ui/`.

## Structure & naming

- One **page per module** in `src/pages/` (`Items.tsx`, `Orders.tsx`).
  Page and component files are `PascalCase.tsx`.
- Shared building blocks in `src/components/`; styled primitives (Button, Card, Input,
  Badge, Select, Textarea) in `src/components/ui/`.
- Cross-cutting state in `src/contexts/` (e.g. `AuthContext`).
- Helpers in `src/lib/` (`api.ts`, `utils.ts`).
- TypeScript interfaces mirroring backend schemas live in `src/types/index.ts`.
- Import with the `@/` alias: `import { classNames } from "@/lib/utils"`.
- Use `import type { ... } from "@/types"` for type-only imports.

## API access — go through the central client

Never call `fetch` from a component. Add a method to the `api` object in `src/lib/api.ts`:

```ts
// items
listItems: () => request<ItemSummary[]>("/api/items"),
createItem: (data: { name: string; kind: string }) =>
  request<Item>("/api/items", { method: "POST", body: JSON.stringify(data) }),
getItem: (id: number) => request<Item>(`/api/items/${id}`),
```

Rules:
- The shared `request<T>()` wrapper sets JSON headers, attaches the `Bearer` token,
  and throws `ApiError(status, detail)` on non-2xx. Reuse it; don't reinvent it.
- **Request/response field names are `snake_case`** to match the backend wire format
  (the TS interfaces in `types/index.ts` use `snake_case` too).
- Build query strings with `URLSearchParams` and `encodeURIComponent`, as the existing
  list endpoints do.
- The auth token is stored in `localStorage` under a single namespaced key — use the
  `getToken`/`setToken` helpers, never touch `localStorage` directly elsewhere.
- Base URL defaults to same-origin (`""`); the nginx/Vite proxy forwards `/api`.
  Override only with `VITE_API_BASE_URL`.

## UI primitives

Styled components take a typed `Props` interface, expose `variant`/`size` unions, and
compose Tailwind classes through `classNames(...)`:

```tsx
interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  children: ReactNode;
}

export function Button({ variant = "primary", size = "md", className, children, ...rest }: Props) {
  const base = "inline-flex items-center justify-center font-medium rounded-md ...";
  const variants: Record<string, string> = {
    primary: "bg-blue-700 hover:bg-blue-600 text-white",
    ...
  };
  return <button className={classNames(base, ..., variants[variant], className)} {...rest}>{children}</button>;
}
```

- Use `export function Foo(...)` (named exports), not default exports, for components.
- Styling is Tailwind utility classes — use the palette defined in `tailwind.config.js`.
  Don't introduce a CSS-in-JS layer.
- Reuse `components/ui/*` primitives instead of re-styling raw `<button>`/`<input>`.

## TypeScript

- `strict` is on. No `any` for API payloads — add an interface in `types/index.ts`.
- Prefer `type | null` and explicit optional (`field?:`) matching the backend's
  nullable/optional fields.
