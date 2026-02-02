import { useEffect, useRef, useState, useCallback } from 'react'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface UseWebSocketOptions {
  onMessage?: (data: unknown) => void
  onError?: (error: Event) => void
  reconnectAttempts?: number
  reconnectInterval?: number
  autoConnect?: boolean
}

export function useWebSocket(url: string | null, options: UseWebSocketOptions = {}) {
  const {
    onMessage,
    onError,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
    autoConnect = true,
  } = options

  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectCountRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const shouldReconnectRef = useRef(true)

  // Store options in refs to avoid stale closures
  const urlRef = useRef(url)
  const onMessageRef = useRef(onMessage)
  const onErrorRef = useRef(onError)
  const reconnectAttemptsRef = useRef(reconnectAttempts)
  const reconnectIntervalRef = useRef(reconnectInterval)

  // Ref to hold the connect function for recursive reconnection
  const connectFnRef = useRef<(() => void) | null>(null)

  // Keep refs updated with latest values
  useEffect(() => {
    urlRef.current = url
    onMessageRef.current = onMessage
    onErrorRef.current = onError
    reconnectAttemptsRef.current = reconnectAttempts
    reconnectIntervalRef.current = reconnectInterval
  }, [url, onMessage, onError, reconnectAttempts, reconnectInterval])

  // Define connect function and store in ref
  useEffect(() => {
    const connect = () => {
      const currentUrl = urlRef.current
      if (!currentUrl) return

      // Clear any pending reconnect
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }

      // Close existing connection if any
      if (wsRef.current) {
        wsRef.current.close()
      }

      setStatus('connecting')
      const ws = new WebSocket(currentUrl)

      ws.onopen = () => {
        setStatus('connected')
        reconnectCountRef.current = 0
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string) as unknown
          onMessageRef.current?.(data)
        } catch {
          onMessageRef.current?.(event.data)
        }
      }

      ws.onerror = (error) => {
        setStatus('error')
        onErrorRef.current?.(error)
      }

      ws.onclose = () => {
        setStatus('disconnected')
        wsRef.current = null

        // Attempt reconnection with exponential backoff
        const maxAttempts = reconnectAttemptsRef.current
        const baseInterval = reconnectIntervalRef.current
        if (shouldReconnectRef.current && reconnectCountRef.current < maxAttempts) {
          const delay = baseInterval * Math.pow(2, reconnectCountRef.current)
          reconnectCountRef.current++
          reconnectTimeoutRef.current = setTimeout(() => {
            connectFnRef.current?.()
          }, delay)
        }
      }

      wsRef.current = ws
    }

    connectFnRef.current = connect
  }, [])

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false
    reconnectCountRef.current = reconnectAttemptsRef.current
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    wsRef.current?.close()
    wsRef.current = null
    setStatus('disconnected')
  }, [])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
      return true
    }
    return false
  }, [])

  const reconnect = useCallback(() => {
    shouldReconnectRef.current = true
    reconnectCountRef.current = 0
    connectFnRef.current?.()
  }, [])

  // Auto-connect effect
  useEffect(() => {
    if (url && autoConnect) {
      shouldReconnectRef.current = true
      // Use setTimeout to avoid synchronous setState within effect
      const timeoutId = setTimeout(() => {
        connectFnRef.current?.()
      }, 0)
      return () => {
        clearTimeout(timeoutId)
        shouldReconnectRef.current = false
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
        }
        wsRef.current?.close()
      }
    }
    return () => {
      shouldReconnectRef.current = false
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      wsRef.current?.close()
    }
  }, [url, autoConnect])

  return { status, send, disconnect, reconnect }
}
