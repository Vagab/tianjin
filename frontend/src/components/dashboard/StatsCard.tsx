import { useTradeStats } from '../../api/hooks'
import { formatPnl, formatPct } from '../../lib/utils'

export function StatsCard() {
  const { data } = useTradeStats()

  if (!data) return null

  return (
    <div className="rounded-xl bg-surface-raised border border-border p-5">
      <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase mb-4">
        All-Time Stats
      </h2>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        <StatRow label="Total Trades" value={String(data.total)} />
        <StatRow label="Win Rate" value={formatPct(data.win_rate)} highlight={data.win_rate > 0.5 ? 'green' : 'red'} />
        <StatRow label="Wins" value={String(data.wins)} highlight="green" />
        <StatRow label="Losses" value={String(data.losses)} highlight="red" />
        <StatRow label="Total P&L" value={formatPnl(data.total_pnl)} highlight={data.total_pnl >= 0 ? 'green' : 'red'} />
        <StatRow label="Avg P&L" value={formatPnl(data.avg_pnl)} highlight={data.avg_pnl >= 0 ? 'green' : 'red'} />
        <StatRow label="Avg Edge" value={formatPct(data.avg_edge)} />
      </div>
    </div>
  )
}

function StatRow({ label, value, highlight }: { label: string; value: string; highlight?: 'green' | 'red' }) {
  const color = highlight === 'green' ? 'text-green' : highlight === 'red' ? 'text-red' : 'text-text-primary'
  return (
    <div className="flex justify-between items-center">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={`text-sm font-mono font-medium ${color}`}>{value}</span>
    </div>
  )
}
