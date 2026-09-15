import { useCallback, useEffect, useRef, useState } from 'react'
import { api, WS_BASE } from '../api'

export type WsEvent = {
  type: string
  task_id?: number
  conversation_id?: number
  delta_text?: string
  tool_name?: string
  tool_result_summary?: string
  task_status?: string
  current_step?: string
  result_id?: number
  error_message?: string
  finished_at?: string
}

export function useChatSocket(conversationId: number | null, onEvent: (ev: WsEvent) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  const connect = useCallback(async () => {
    if (!conversationId) return
    if (wsRef.current && wsRef.current.readyState <= 1) {
      wsRef.current.close()
    }
    const { websocket_token } = await api.wsToken(conversationId)
    const url = `${WS_BASE}/api/chat/ws/chat?websocket_token=${encodeURIComponent(websocket_token)}&conversation_id=${conversationId}`
    const ws = new WebSocket(url)
    wsRef.current = ws
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as WsEvent
        handlerRef.current(data)
      } catch {
        /* ignore */
      }
    }
  }, [conversationId])

  useEffect(() => {
    connect().catch(() => setConnected(false))
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  const startTask = useCallback((taskId: number) => {
    wsRef.current?.send(JSON.stringify({ action: 'start_task', task_id: taskId }))
  }, [])

  const cancelTask = useCallback((taskId: number) => {
    wsRef.current?.send(JSON.stringify({ action: 'cancel_task', task_id: taskId }))
  }, [])

  return { connected, startTask, cancelTask, reconnect: connect }
}
