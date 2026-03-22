import { useMemo } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import { useEquity } from '../../api/hooks'
import { formatUSD, formatTime } from '../../lib/utils'

export function EquityCurve() {
  const since = useMemo(() => Date.now() / 1000 - 7 * 86400, [])
  const { data: snapshots } = useEquity(since)

  const chartData = useMemo(() => {
    if (!snapshots?.length) return []
    return snapshots.map((s) => ({
      time: s.timestamp,
      balance: s.balance_usd,
      pnl: s.total_pnl,
    }))
  }, [snapshots])

  const hasData = chartData.length > 0
  const isProfitable = hasData && chartData[chartData.length - 1].pnl >= 0

  return (
    <div className="rounded-xl bg-surface-raised border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border-subtle">
        <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase">
          Equity Curve
        </h2>
      </div>
      <div className="h-[250px] w-full p-2">
        {!hasData ? (
          <div className="flex items-center justify-center h-full text-text-muted text-sm">
            No data yet — snapshots recorded every 60s
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor={isProfitable ? '#22c55e' : '#ef4444'}
                    stopOpacity={0.3}
                  />
                  <stop
                    offset="100%"
                    stopColor={isProfitable ? '#22c55e' : '#ef4444'}
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e1e2e" strokeDasharray="3 3" />
              <XAxis
                dataKey="time"
                tickFormatter={(t) => formatTime(t)}
                stroke="#555570"
                tick={{ fontSize: 10 }}
                axisLine={{ stroke: '#2a2a3a' }}
              />
              <YAxis
                tickFormatter={(v) => `$${v.toFixed(0)}`}
                stroke="#555570"
                tick={{ fontSize: 10 }}
                axisLine={{ stroke: '#2a2a3a' }}
                width={60}
              />
              <Tooltip
                contentStyle={{
                  background: '#1a1a25',
                  border: '1px solid #2a2a3a',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                labelFormatter={(t) => formatTime(t as number)}
                formatter={(value) => [formatUSD(value as number), 'Balance']}
              />
              <Area
                type="monotone"
                dataKey="balance"
                stroke={isProfitable ? '#22c55e' : '#ef4444'}
                strokeWidth={2}
                fill="url(#equityGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
