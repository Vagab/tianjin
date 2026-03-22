import { PortfolioCard } from '../components/dashboard/PortfolioCard'
import { StatusCard } from '../components/dashboard/StatusCard'
import { RiskCard } from '../components/dashboard/RiskCard'
import { StatsCard } from '../components/dashboard/StatsCard'
import { BotControls } from '../components/controls/BotControls'
import { PriceChart } from '../components/charts/PriceChart'
import { EquityCurve } from '../components/charts/EquityCurve'
import { TradeTable } from '../components/trades/TradeTable'

export function Dashboard() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-border px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold tracking-tight">Tianjin</h1>
            <span className="text-xs text-text-muted px-2 py-0.5 rounded bg-surface-overlay">
              Polymarket BTC Bot
            </span>
          </div>
          <BotControls />
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Top row: Portfolio + Status + Risk */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="lg:col-span-1">
            <PortfolioCard />
          </div>
          <div className="lg:col-span-1">
            <StatusCard />
          </div>
          <div className="lg:col-span-1">
            <RiskCard />
          </div>
          <div className="lg:col-span-1">
            <StatsCard />
          </div>
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <PriceChart />
          <EquityCurve />
        </div>

        {/* Trade table */}
        <TradeTable />
      </main>
    </div>
  )
}
