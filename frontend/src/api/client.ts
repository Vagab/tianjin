const BASE = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  getPortfolio: () => request<import('../types').Portfolio>('/portfolio'),
  getTrades: (limit = 50, offset = 0, outcome?: string) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (outcome) params.set('outcome', outcome)
    return request<import('../types').TradesList>(`/trades?${params}`)
  },
  getTradeStats: () => request<import('../types').TradeStats>('/trades/stats'),
  getStatus: () => request<import('../types').BotStatus>('/status'),
  getRisk: () => request<import('../types').Risk>('/risk'),
  getPrices: (since?: number) => {
    const params = since ? `?since=${since}` : ''
    return request<import('../types').PriceTick[]>(`/prices${params}`)
  },
  getEquity: (since?: number) => {
    const params = since ? `?since=${since}` : ''
    return request<import('../types').EquitySnapshot[]>(`/equity${params}`)
  },
  getMarket: () => request<import('../types').Market | { market: null }>('/market'),
  halt: () => request('/control/halt', { method: 'POST' }),
  resume: () => request('/control/resume', { method: 'POST' }),
}
