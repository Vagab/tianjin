import { useState } from 'react'
import { useTrades } from '../../api/hooks'
import { formatUSD, formatPnl, formatPct, formatDateTime } from '../../lib/utils'
import { cn } from '../../lib/utils'

const PAGE_SIZE = 20

export function TradeTable() {
  const [page, setPage] = useState(0)
  const [filter, setFilter] = useState<string | undefined>(undefined)
  const { data, isLoading } = useTrades(PAGE_SIZE, page * PAGE_SIZE, filter)

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <div className="rounded-xl bg-surface-raised border border-border overflow-hidden">
      <div className="flex items-center justify-between p-4 border-b border-border-subtle">
        <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase">
          Trade History
        </h2>
        <div className="flex gap-1">
          {['all', 'win', 'loss'].map((f) => (
            <button
              key={f}
              onClick={() => { setFilter(f === 'all' ? undefined : f); setPage(0) }}
              className={cn(
                'px-2.5 py-1 rounded text-xs font-medium transition-colors',
                (f === 'all' && !filter) || f === filter
                  ? 'bg-accent/20 text-accent'
                  : 'text-text-muted hover:text-text-secondary',
              )}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-text-muted border-b border-border-subtle">
              <th className="text-left px-4 py-2.5 font-medium">Time</th>
              <th className="text-left px-4 py-2.5 font-medium">Market</th>
              <th className="text-center px-4 py-2.5 font-medium">Dir</th>
              <th className="text-right px-4 py-2.5 font-medium">Amount</th>
              <th className="text-right px-4 py-2.5 font-medium">Price</th>
              <th className="text-right px-4 py-2.5 font-medium">Edge</th>
              <th className="text-center px-4 py-2.5 font-medium">Outcome</th>
              <th className="text-right px-4 py-2.5 font-medium">P&L</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} className="border-b border-border-subtle/50">
                  <td colSpan={8} className="px-4 py-3">
                    <div className="h-4 bg-surface-overlay rounded animate-pulse" />
                  </td>
                </tr>
              ))
            ) : data?.trades.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-text-muted text-sm">
                  No trades yet
                </td>
              </tr>
            ) : (
              data?.trades.map((trade) => (
                <tr
                  key={trade.id}
                  className={cn(
                    'border-b border-border-subtle/50 transition-colors hover:bg-surface-overlay/50',
                    trade.outcome === 'win' && 'bg-green-muted/30',
                    trade.outcome === 'loss' && 'bg-red-muted/30',
                  )}
                >
                  <td className="px-4 py-2.5 font-mono text-xs text-text-secondary">
                    {formatDateTime(trade.timestamp)}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-text-secondary truncate max-w-[180px]">
                    {trade.market_slug.replace('btc-updown-', '')}
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    <span className={cn(
                      'inline-block px-2 py-0.5 rounded text-xs font-medium',
                      trade.direction === 'UP'
                        ? 'bg-green/15 text-green'
                        : 'bg-red/15 text-red',
                    )}>
                      {trade.direction}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs">
                    {formatUSD(trade.amount_usd)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs">
                    {trade.entry_price.toFixed(4)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs">
                    {formatPct(trade.edge)}
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    {trade.outcome ? (
                      <span className={cn(
                        'inline-block px-2 py-0.5 rounded text-xs font-medium',
                        trade.outcome === 'win'
                          ? 'bg-green/15 text-green'
                          : 'bg-red/15 text-red',
                      )}>
                        {trade.outcome.toUpperCase()}
                      </span>
                    ) : (
                      <span className="text-text-muted text-xs">Pending</span>
                    )}
                  </td>
                  <td className={cn(
                    'px-4 py-2.5 text-right font-mono text-xs font-medium',
                    trade.pnl > 0 ? 'text-green' : trade.pnl < 0 ? 'text-red' : 'text-text-muted',
                  )}>
                    {trade.outcome ? formatPnl(trade.pnl) : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-border-subtle">
          <span className="text-xs text-text-muted">
            {data?.total ?? 0} trades total
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1 rounded text-xs text-text-secondary hover:bg-surface-overlay disabled:opacity-30 transition-colors"
            >
              Prev
            </button>
            <span className="px-3 py-1 text-xs text-text-muted">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1 rounded text-xs text-text-secondary hover:bg-surface-overlay disabled:opacity-30 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
