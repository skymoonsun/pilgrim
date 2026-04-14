> Claude Code: modular rules in `.claude/rules/` — [Memory & rules](https://code.claude.com/docs/en/memory). Cursor equivalent: `.cursor/rules/frontend.mdc`.

# Frontend — Pilgrim Dashboard

Pilgrim's frontend is a **React 19 + TypeScript + Vite** single-page application that provides a dashboard for managing crawl configurations, testing scrapes, and monitoring jobs.

## 1. Stack

| Technology | Purpose |
|-----------|---------|
| **React 19** | UI framework |
| **TypeScript** | Type safety |
| **Vite 8** | Dev server + bundler |
| **React Router 7** | Client-side routing |
| **Vanilla CSS** | Styling (no Tailwind) |

## 2. Directory layout

```
frontend/src/
├── api/client.ts              # Typed API client (all endpoints)
├── components/
│   ├── icons/Icons.tsx         # Inline SVG icon library
│   └── layout/                 # AppLayout, Sidebar, Header
├── pages/
│   ├── Dashboard/              # Health cards, metrics, recent jobs
│   ├── Configurations/         # CRUD table for crawl configs
│   ├── ScrapePlayground/       # Config + URL → JSON response
│   ├── Jobs/                   # Job listing with status badges
│   └── Settings/               # App settings (placeholder)
├── App.tsx                     # React Router routes
├── main.tsx                    # Entry (BrowserRouter)
└── index.css                   # Design system (CSS variables)
```

## 3. Design system rules

- **Dark theme only** — CSS variable layers (`--bg-primary` to `--bg-sidebar`)
- **Vanilla CSS** — No CSS frameworks; styles in `index.css` using custom properties
- **Glassmorphism cards** — `backdrop-filter: blur(8px)` + transparent backgrounds
- **Color palette**: Cyan `#00f0ff`, blue `#0080ff`, dark navy backgrounds
- **Typography**: Inter (Google Fonts), monospace for code/IDs
- **Icons**: Inline SVG in `components/icons/Icons.tsx` — no emoji, no icon fonts
- **Animations**: `fadeIn` keyframes with staggered delays

## 4. Component conventions

- Pages in `src/pages/<PageName>/<PageName>.tsx`
- Layout in `src/components/layout/`
- API calls through `src/api/client.ts` — never raw `fetch()` in components
- Loading = `.spinner` class; empty = `.empty-state` class + SVG icon

## 5. API proxy

Vite proxies `/api/*` → `http://api:8000` (Docker service name). **Never hardcode** `localhost:8000`.

## 6. Route ↔ API mapping

| Route | Backend endpoints |
|-------|-------------------|
| `/` | `GET /health/readiness`, `GET /crawl-configs/`, `GET /crawl/jobs` |
| `/configurations` | CRUD `/crawl-configs/` |
| `/scrape` | `POST /scrape/`, `GET /crawl-configs/` |
| `/jobs` | `GET /crawl/jobs` |

## 7. Adding a new page

1. Create `src/pages/NewPage/NewPage.tsx`
2. Add route in `App.tsx` inside the `<Route element={<AppLayout />}>` group
3. Add nav item in `Sidebar.tsx` with SVG icon from `Icons.tsx`
4. Add types + methods to `api/client.ts` if needed
