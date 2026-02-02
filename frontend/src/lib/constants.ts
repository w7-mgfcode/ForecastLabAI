// Route paths
export const ROUTES = {
  DASHBOARD: '/',
  EXPLORER: {
    SALES: '/explorer/sales',
    STORES: '/explorer/stores',
    PRODUCTS: '/explorer/products',
    RUNS: '/explorer/runs',
    JOBS: '/explorer/jobs',
  },
  VISUALIZE: {
    FORECAST: '/visualize/forecast',
    BACKTEST: '/visualize/backtest',
  },
  CHAT: '/chat',
  ADMIN: '/admin',
} as const

// Navigation items for the top nav
export const NAV_ITEMS = [
  { label: 'Dashboard', href: ROUTES.DASHBOARD },
  {
    label: 'Explorer',
    items: [
      { label: 'Sales', href: ROUTES.EXPLORER.SALES },
      { label: 'Stores', href: ROUTES.EXPLORER.STORES },
      { label: 'Products', href: ROUTES.EXPLORER.PRODUCTS },
      { label: 'Model Runs', href: ROUTES.EXPLORER.RUNS },
      { label: 'Jobs', href: ROUTES.EXPLORER.JOBS },
    ],
  },
  {
    label: 'Visualize',
    items: [
      { label: 'Forecast', href: ROUTES.VISUALIZE.FORECAST },
      { label: 'Backtest Results', href: ROUTES.VISUALIZE.BACKTEST },
    ],
  },
  { label: 'Chat', href: ROUTES.CHAT },
  { label: 'Admin', href: ROUTES.ADMIN },
] as const

// Default pagination
export const DEFAULT_PAGE_SIZE = 25

// WebSocket URL
export const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8123/agents/stream'

// Feature flags
export const ENABLE_AGENT_CHAT = import.meta.env.VITE_ENABLE_AGENT_CHAT !== 'false'
export const ENABLE_ADMIN_PANEL = import.meta.env.VITE_ENABLE_ADMIN_PANEL !== 'false'
