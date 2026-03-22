import { useEffect, useRef, useMemo } from 'react'
import { createChart, type IChartApi, ColorType, LineStyle, LineSeries } from 'lightweight-charts'
import { usePrices } from '../../api/hooks'
import { useWs } from '../../api/ws'

export function PriceChart() {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartApi = useRef<IChartApi | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesApi = useRef<any>(null)

  const since = useMemo(() => Date.now() / 1000 - 86400, [])
  const { data: historicalPrices } = usePrices(since)
  const { subscribe } = useWs()

  // Create chart
  useEffect(() => {
    if (!chartRef.current) return

    const chart = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8888a0',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1e1e2e', style: LineStyle.Dotted },
        horzLines: { color: '#1e1e2e', style: LineStyle.Dotted },
      },
      crosshair: {
        horzLine: { color: '#6366f1', labelBackgroundColor: '#6366f1' },
        vertLine: { color: '#6366f1', labelBackgroundColor: '#6366f1' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#2a2a3a',
      },
      rightPriceScale: {
        borderColor: '#2a2a3a',
      },
      handleScroll: { vertTouchDrag: false },
    })

    const series = chart.addSeries(LineSeries, {
      color: '#6366f1',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: '#6366f1',
      crosshairMarkerBackgroundColor: '#0a0a0f',
    })

    chartApi.current = chart
    seriesApi.current = series

    const resizeObserver = new ResizeObserver(() => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth })
      }
    })
    resizeObserver.observe(chartRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
    }
  }, [])

  // Load historical data
  useEffect(() => {
    if (!seriesApi.current || !historicalPrices?.length) return
    const data = historicalPrices.map((t) => ({
      time: t.timestamp as any,
      value: t.price,
    }))
    seriesApi.current.setData(data)
  }, [historicalPrices])

  // Live updates via WebSocket
  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type === 'price_tick' && seriesApi.current) {
        seriesApi.current.update({
          time: msg.timestamp as any,
          value: msg.price,
        })
      }
    })
  }, [subscribe])

  return (
    <div className="rounded-xl bg-surface-raised border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border-subtle">
        <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase">BTC Price</h2>
      </div>
      <div ref={chartRef} className="h-[300px] w-full" />
    </div>
  )
}
