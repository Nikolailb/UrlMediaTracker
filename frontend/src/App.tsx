import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'
import { queryClient } from '@/lib/queryClient'
import { ItemsPage } from '@/pages/ItemsPage'
import { AuthProvider } from '@/auth/AuthProvider'
import { useAuth } from '@/auth/context'
import { LoginPage } from '@/auth/LoginPage'

function AppContent() {
  const { session } = useAuth()
  if (session === undefined) return <div className="p-6">Loading…</div>
  return session ? <ItemsPage /> : <LoginPage />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider><AppContent /></AuthProvider>
        <Toaster richColors position="bottom-right" />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

