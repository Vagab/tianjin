import { useState, useEffect, useCallback } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WsProvider } from './api/ws'
import { Dashboard } from './pages/Dashboard'
import { Auth } from './pages/Auth'
import { api } from './api/client'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 5_000,
    },
  },
})

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null) // null = loading

  const checkAuth = useCallback(async () => {
    try {
      await api.me()
      setAuthed(true)
    } catch {
      setAuthed(false)
    }
  }, [])

  useEffect(() => {
    checkAuth()

    const handleLogout = () => setAuthed(false)
    window.addEventListener('auth:logout', handleLogout)
    return () => window.removeEventListener('auth:logout', handleLogout)
  }, [checkAuth])

  // Loading state
  if (authed === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-text-muted text-sm">Loading...</div>
      </div>
    )
  }

  if (!authed) {
    return (
      <QueryClientProvider client={queryClient}>
        <Auth onAuth={() => setAuthed(true)} />
      </QueryClientProvider>
    )
  }

  return (
    <QueryClientProvider client={queryClient}>
      <WsProvider>
        <Dashboard onLogout={() => { api.logout(); setAuthed(false) }} />
      </WsProvider>
    </QueryClientProvider>
  )
}
