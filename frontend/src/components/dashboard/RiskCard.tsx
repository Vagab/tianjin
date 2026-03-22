import { useRisk, usePortfolio } from '../../api/hooks'
import { formatUSD, formatPct } from '../../lib/utils'

export function RiskCard() {
  const { data: risk } = useRisk()
  const { data: portfolio } = usePortfolio()

  if (!risk) return null

  const exposurePct = portfolio
    ? portfolio.open_exposure / risk.max_exposure_usd
    : 0

  return (
    <div className="rounded-xl bg-surface-raised border border-border p-5">
      <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase mb-4">Risk</h2>

      <div className="space-y-3">
        <RiskRow label="Max Position" value={formatUSD(risk.max_position_usd)} />
        <RiskRow label="Max Exposure" value={formatUSD(risk.max_exposure_usd)} />
        <RiskRow label="Max Daily Loss" value={formatUSD(risk.max_daily_loss_usd)} />
        <RiskRow label="Kelly Fraction" value={formatPct(risk.kelly_fraction)} />
        <RiskRow label="Min Edge" value={formatPct(risk.min_edge)} />

        <div className="border-t border-border-subtle pt-3">
          <RiskRow
            label="Consec. Losses"
            value={`${risk.consecutive_losses} / 8`}
            warn={risk.consecutive_losses >= 5}
          />
        </div>

        {portfolio && (
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-text-muted">Exposure</span>
              <span className="text-text-secondary font-mono">
                {formatUSD(portfolio.open_exposure)} / {formatUSD(risk.max_exposure_usd)}
              </span>
            </div>
            <div className="h-1.5 bg-surface-overlay rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  exposurePct > 0.8 ? 'bg-red' : exposurePct > 0.5 ? 'bg-yellow' : 'bg-accent'
                }`}
                style={{ width: `${Math.min(exposurePct * 100, 100)}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function RiskRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={`text-sm font-mono ${warn ? 'text-yellow' : 'text-text-primary'}`}>
        {value}
      </span>
    </div>
  )
}
