import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from 'react'
import React from 'react'
import type { WsMessage } from '../types'

type Listener = (msg: WsMessage) => void

interface WsContextValue {
  lastPrice: number | null
  connected: boolean
  subscribe: (listener: Listener) => () => void
}

const WsContext = createContext<WsContextValue>({
  lastPrice: null,
  connected: false,
  subscribe: () => () => {},
})

export function useWs() {
  return useContext(WsContext)
}

export function WsProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false)
  const [lastPrice, setLastPrice] = useState<number | null>(null)
  const listenersRef = useRef<Set<Listener>>(new Set())
  const wsRef = useRef<WebSocket | null>(null)

  const subscribe = useCallback((listener: Listener) => {
    listenersRef.current.add(listener)
    return () => { listenersRef.current.delete(listener) }
  }, [])

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>
    let ws: WebSocket

    function connect() {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${proto}//${window.location.host}/ws`
      ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        reconnectTimer = setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data)
          if (msg.type === 'price_tick') {
            setLastPrice(msg.price)
          }
          listenersRef.current.forEach((fn) => fn(msg))
        } catch {
          // ignore malformed messages
        }
      }
    }

    connect()
    return () => {
      clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [])

  return React.createElement(
    WsContext.Provider,
    { value: { lastPrice, connected, subscribe } },
    children,
  )
}
