import { Outlet } from 'react-router-dom'
import { TopNav } from './top-nav'
import { Toaster } from '@/components/ui/sonner'

export function AppShell() {
  return (
    <div className="relative flex min-h-screen flex-col">
      <TopNav />
      <main className="flex-1 container mx-auto px-4 py-6">
        <Outlet />
      </main>
      <Toaster />
    </div>
  )
}
