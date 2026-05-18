import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from '@/providers/theme-provider'
import { queryClient } from '@/lib/query-client'
import { AppShell } from '@/components/layout/app-shell'
import { LoadingState } from '@/components/common/loading-state'
import { ROUTES } from '@/lib/constants'

// Lazy-loaded page components
const DashboardPage = lazy(() => import('@/pages/dashboard'))
const ShowcasePage = lazy(() => import('@/pages/showcase'))
const SalesExplorerPage = lazy(() => import('@/pages/explorer/sales'))
const StoresExplorerPage = lazy(() => import('@/pages/explorer/stores'))
const StoreDetailPage = lazy(() => import('@/pages/explorer/store-detail'))
const ProductsExplorerPage = lazy(() => import('@/pages/explorer/products'))
const ProductDetailPage = lazy(() => import('@/pages/explorer/product-detail'))
const RunsExplorerPage = lazy(() => import('@/pages/explorer/runs'))
const JobsMonitorPage = lazy(() => import('@/pages/explorer/jobs'))
const ForecastPage = lazy(() => import('@/pages/visualize/forecast'))
const BacktestPage = lazy(() => import('@/pages/visualize/backtest'))
const ChatPage = lazy(() => import('@/pages/chat'))
const KnowledgePage = lazy(() => import('@/pages/knowledge'))
const GuidePage = lazy(() => import('@/pages/guide'))
const AdminPage = lazy(() => import('@/pages/admin'))

function PageLoader() {
  return <LoadingState message="Loading page..." />
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route
                path={ROUTES.DASHBOARD}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <DashboardPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.SHOWCASE}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <ShowcasePage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.EXPLORER.SALES}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <SalesExplorerPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.EXPLORER.STORES}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <StoresExplorerPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.EXPLORER.STORE_DETAIL}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <StoreDetailPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.EXPLORER.PRODUCTS}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <ProductsExplorerPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.EXPLORER.PRODUCT_DETAIL}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <ProductDetailPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.EXPLORER.RUNS}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <RunsExplorerPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.EXPLORER.JOBS}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <JobsMonitorPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.VISUALIZE.FORECAST}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <ForecastPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.VISUALIZE.BACKTEST}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <BacktestPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.KNOWLEDGE}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <KnowledgePage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.CHAT}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <ChatPage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.GUIDE}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <GuidePage />
                  </Suspense>
                }
              />
              <Route
                path={ROUTES.ADMIN}
                element={
                  <Suspense fallback={<PageLoader />}>
                    <AdminPage />
                  </Suspense>
                }
              />
            </Route>
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

export default App
