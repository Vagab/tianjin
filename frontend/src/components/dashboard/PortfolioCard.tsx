import { usePortfolio } from '../../api/hooks'
import { useWs } from '../../api/ws'
import { formatUSD, formatPnl, formatPct } from '../../lib/utils'

export function PortfolioCard() {
  const { data, isLoading } = usePortfolio()
  const { lastPrice } = useWs()

  if (isLoading || !data) {
    return <CardSkeleton />
  }

  return (
    <div className="rounded-xl bg-surface-raised border border-border p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase">Portfolio</h2>
        {lastPrice && (
          <span className="text-xs text-text-muted font-mono">
            BTC {formatUSD(lastPrice)}
          </span>
        )}
      </div>

      <div className="text-3xl font-semibold tracking-tight mb-4 font-mono">
        {formatUSD(data.balance_usd)}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Stat label="Daily P&L" value={formatPnl(data.daily_pnl)} positive={data.daily_pnl >= 0} />
        <Stat label="Total P&L" value={formatPnl(data.total_pnl)} positive={data.total_pnl >= 0} />
        <Stat label="Win Rate" value={formatPct(data.win_rate)} />
        <Stat label="Open Positions" value={String(data.open_positions)} />
      </div>
    </div>
  )
}

function Stat({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  const color = positive === undefined
    ? 'text-text-primary'
    : positive
      ? 'text-green'
      : 'text-red'

  return (
    <div>
      <div className="text-xs text-text-muted mb-1">{label}</div>
      <div className={`text-sm font-mono font-medium ${color}`}>{value}</div>
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="rounded-xl bg-surface-raised border border-border p-5 animate-pulse">
      <div className="h-4 w-20 bg-surface-overlay rounded mb-4" />
      <div className="h-8 w-32 bg-surface-overlay rounded mb-4" />
      <div className="grid grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i}>
            <div className="h-3 w-16 bg-surface-overlay rounded mb-1" />
            <div className="h-4 w-20 bg-surface-overlay rounded" />
          </div>
        ))}
      </div>
    </div>
  )
}
