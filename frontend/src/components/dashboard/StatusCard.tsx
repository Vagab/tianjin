import { useStatus, useMarket } from '../../api/hooks'
import { useWs } from '../../api/ws'
import { timeAgo } from '../../lib/utils'
import { useEffect, useState } from 'react'

export function StatusCard() {
  const { data: status } = useStatus()
  const { data: market } = useMarket()
  const { connected } = useWs()

  const hasMarket = market && 'slug' in market
  const [countdown, setCountdown] = useState('')

  useEffect(() => {
    if (!hasMarket || !market.end_ts) return
    const interval = setInterval(() => {
      const remaining = market.end_ts - Date.now() / 1000
      if (remaining <= 0) {
        setCountdown('Closed')
      } else {
        const m = Math.floor(remaining / 60)
        const s = Math.floor(remaining % 60)
        setCountdown(`${m}:${s.toString().padStart(2, '0')}`)
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [hasMarket, market])

  return (
    <div className="rounded-xl bg-surface-raised border border-border p-5">
      <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase mb-4">Status</h2>

      <div className="space-y-3">
        <Row label="Bot">
          <StatusDot active={!!status?.running} />
          <span className="text-sm">
            {status?.running ? 'Running' : 'Stopped'}
            {status?.paper_trading && <span className="ml-1.5 text-yellow text-xs">(Paper)</span>}
          </span>
        </Row>

        <Row label="Trading">
          <StatusDot active={!status?.halted} color={status?.halted ? 'red' : 'green'} />
          <span className="text-sm">{status?.halted ? 'Halted' : 'Active'}</span>
        </Row>

        <Row label="WebSocket">
          <StatusDot active={connected} />
          <span className="text-sm">{connected ? 'Connected' : 'Disconnected'}</span>
        </Row>

        {status?.uptime_seconds ? (
          <Row label="Uptime">
            <span className="text-sm font-mono text-text-primary">{timeAgo(status.uptime_seconds)}</span>
          </Row>
        ) : null}

        {hasMarket && (
          <>
            <div className="border-t border-border-subtle pt-3 mt-3">
              <div className="text-xs text-text-muted mb-1.5">Current Market</div>
              <div className="text-xs font-mono text-text-secondary truncate">{market.slug}</div>
            </div>
            <div className="flex gap-4">
              <div>
                <span className="text-xs text-text-muted">Up </span>
                <span className="text-sm font-mono text-green">{market.up_price.toFixed(3)}</span>
              </div>
              <div>
                <span className="text-xs text-text-muted">Down </span>
                <span className="text-sm font-mono text-red">{market.down_price.toFixed(3)}</span>
              </div>
              <div className="ml-auto">
                <span className="text-sm font-mono text-text-primary">{countdown}</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted w-16 shrink-0">{label}</span>
      <div className="flex items-center gap-1.5">{children}</div>
    </div>
  )
}

function StatusDot({ active, color }: { active: boolean; color?: 'green' | 'red' }) {
  const c = color ?? (active ? 'green' : 'red')
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${
        c === 'green' ? 'bg-green' : 'bg-red'
      } ${active ? 'animate-pulse' : ''}`}
    />
  )
}
