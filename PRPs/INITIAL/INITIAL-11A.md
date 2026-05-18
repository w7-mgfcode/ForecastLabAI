# INITIAL-11A.md — ForecastLab Dashboard (The Face)

> **Part A of 3**: Setup & Configuration
> See also: [INITIAL-11B.md](./INITIAL-11B.md) (Architecture & Features) | [INITIAL-11C.md](./INITIAL-11C.md) (Pages & Components)

---

## Prerequisites

- Node.js 20+
- pnpm (recommended) or npm
- Backend API running on `http://localhost:8123`

---

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # shadcn/ui components (auto-generated)
│   │   ├── data-table/      # DataTable wrapper
│   │   ├── charts/          # Chart components
│   │   ├── chat/            # Chat components
│   │   └── layout/          # App shell, nav
│   ├── hooks/               # TanStack Query hooks
│   ├── lib/
│   │   ├── api.ts           # API client
│   │   └── utils.ts         # cn() utility
│   ├── pages/               # Route pages
│   └── App.tsx
├── .env.example
├── package.json
├── tailwind.config.js
└── vite.config.ts
```

---

## Installation

### Step 1: Create Project

```bash
pnpm create vite frontend --template react-ts
cd frontend
```

### Step 2: Install Dependencies

```bash
# Core dependencies
pnpm add @tanstack/react-query @tanstack/react-table recharts date-fns lucide-react

# Tailwind CSS 4
pnpm add -D tailwindcss @tailwindcss/vite
npx tailwindcss init
```

### Step 3: Initialize shadcn/ui

```bash
npx shadcn@latest init
```

When prompted:
- Style: **New York**
- Base color: **Neutral**
- CSS variables: **Yes**

### Step 4: Install shadcn Components

```bash
# Layout & Navigation
npx shadcn@latest add card tabs navigation-menu sheet scroll-area separator

# Data Display
npx shadcn@latest add table badge skeleton pagination progress

# Form Components
npx shadcn@latest add button input select textarea calendar popover checkbox

# Feedback & Overlays
npx shadcn@latest add sonner tooltip alert-dialog dialog

# Interactive
npx shadcn@latest add collapsible accordion dropdown-menu

# Charts (wraps Recharts)
npx shadcn@latest add chart
```

---

## Environment Configuration

Create `.env` from `.env.example`:

```env
# .env.example

# API Configuration
VITE_API_BASE_URL=http://localhost:8123
VITE_WS_URL=ws://localhost:8123/agents/stream

# Feature Flags
VITE_ENABLE_AGENT_CHAT=true
VITE_ENABLE_ADMIN_PANEL=true

# Visualization
VITE_DEFAULT_PAGE_SIZE=25
VITE_MAX_CHART_POINTS=365
```

---

## Theme Configuration

Add chart color variables to `src/index.css`:

```css
@layer base {
  :root {
    --chart-1: 221.2 83.2% 53.3%;
    --chart-2: 142.1 76.2% 36.3%;
    --chart-3: 47.9 95.8% 53.1%;
    --chart-4: 24.6 95% 53.1%;
    --chart-5: 280.1 93.6% 53.1%;
  }

  .dark {
    --chart-1: 217.2 91.2% 59.8%;
    --chart-2: 142.1 70.6% 45.3%;
    --chart-3: 47.9 95.8% 53.1%;
    --chart-4: 24.6 95% 53.1%;
    --chart-5: 280.1 93.6% 53.1%;
  }
}
```

---

## Verify Setup

```bash
# Start dev server
pnpm dev

# Open http://localhost:5173
```

You should see the Vite + React welcome page. shadcn/ui components are now available in `src/components/ui/`.

---

## Documentation Links

- [shadcn/ui Documentation](https://ui.shadcn.com/)
- [shadcn/ui Installation](https://ui.shadcn.com/docs/installation)
- [Vite Documentation](https://vite.dev/)
- [TanStack Query](https://tanstack.com/query/latest)
- [TanStack Table](https://tanstack.com/table/latest)
- [Tailwind CSS 4](https://tailwindcss.com/)

---

## Other Considerations

- **Node Version**: Use Node.js 20+ for best compatibility
- **Package Manager**: pnpm is recommended for faster installs
- **TypeScript**: Strict mode enabled by default
- **Path Aliases**: `@/` maps to `src/` via tsconfig
- **CSS Variables**: shadcn/ui uses CSS variables for theming

---

## Next Steps

1. **Read [INITIAL-11B.md](./INITIAL-11B.md)** — Understand the architecture and features
2. **Read [INITIAL-11C.md](./INITIAL-11C.md)** — Implement pages and components
