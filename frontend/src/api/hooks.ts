import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: api.getPortfolio,
    refetchInterval: 10_000,
  })
}

export function useTrades(limit = 50, offset = 0, outcome?: string) {
  return useQuery({
    queryKey: ['trades', limit, offset, outcome],
    queryFn: () => api.getTrades(limit, offset, outcome),
    refetchInterval: 30_000,
  })
}

export function useTradeStats() {
  return useQuery({
    queryKey: ['tradeStats'],
    queryFn: api.getTradeStats,
    refetchInterval: 30_000,
  })
}

export function useStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: api.getStatus,
    refetchInterval: 5_000,
  })
}

export function useRisk() {
  return useQuery({
    queryKey: ['risk'],
    queryFn: api.getRisk,
    refetchInterval: 10_000,
  })
}

export function usePrices(since?: number) {
  return useQuery({
    queryKey: ['prices', since],
    queryFn: () => api.getPrices(since),
    refetchInterval: 60_000,
  })
}

export function useEquity(since?: number) {
  return useQuery({
    queryKey: ['equity', since],
    queryFn: () => api.getEquity(since),
    refetchInterval: 60_000,
  })
}

export function useMarket() {
  return useQuery({
    queryKey: ['market'],
    queryFn: api.getMarket,
    refetchInterval: 5_000,
  })
}

export function useHalt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.halt,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['status'] })
      qc.invalidateQueries({ queryKey: ['risk'] })
    },
  })
}

export function useResume() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.resume,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['status'] })
      qc.invalidateQueries({ queryKey: ['risk'] })
    },
  })
}
