export interface Portfolio {
  balance_usd: number
  daily_pnl: number
  total_pnl: number
  open_exposure: number
  open_positions: number
  win_rate: number
}

export interface Trade {
  id: number
  timestamp: number
  market_slug: string
  direction: 'UP' | 'DOWN'
  amount_usd: number
  entry_price: number
  edge: number
  outcome: 'win' | 'loss' | null
  pnl: number
}

export interface TradesList {
  trades: Trade[]
  total: number
  limit: number
  offset: number
}

export interface TradeStats {
  total: number
  wins: number
  losses: number
  win_rate: number
  total_pnl: number
  avg_edge: number
  avg_pnl: number
}

export interface BotStatus {
  running: boolean
  halted: boolean
  paper_trading: boolean
  current_market: string | null
  market_end_ts: number | null
  uptime_seconds: number
}

export interface Risk {
  max_position_usd: number
  max_exposure_usd: number
  max_daily_loss_usd: number
  kelly_fraction: number
  min_edge: number
  consecutive_losses: number
  halted: boolean
}

export interface Market {
  slug: string
  question: string
  up_price: number
  down_price: number
  start_ts: number
  end_ts: number
  active: boolean
}

export interface PriceTick {
  timestamp: number
  price: number
  volume: number
}

export interface EquitySnapshot {
  timestamp: number
  balance_usd: number
  daily_pnl: number
  total_pnl: number
  open_exposure: number
}

export type WsMessage =
  | { type: 'price_tick'; price: number; timestamp: number; volume: number }
  | { type: 'trade'; market_slug: string; direction: string; amount_usd: number; edge: number }
  | { type: 'settlement'; market_slug: string; outcome: string; pnl: number }
  | { type: 'portfolio_update'; balance_usd: number; daily_pnl: number; total_pnl: number }
  | { type: 'status_change'; [key: string]: unknown }
