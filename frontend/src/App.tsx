import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WsProvider } from './api/ws'
import { Dashboard } from './pages/Dashboard'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 5_000,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WsProvider>
        <Dashboard />
      </WsProvider>
    </QueryClientProvider>
  )
}
