export const API_BASE = import.meta.env.VITE_API_BASE ?? ''
export const WS_BASE =
  import.meta.env.VITE_WS_BASE ??
  `${typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws'}://${typeof window !== 'undefined' ? window.location.host : 'localhost:5173'}`


const TOKEN_KEY = 'jygy_access_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  const token = getToken()
  // 登录换票接口不要带旧 token，避免干扰
  const isAuthExchange = path.startsWith('/auth/callback') || path.startsWith('/auth/login')
  if (token && !isAuthExchange) headers.set('Authorization', `Bearer ${token}`)
  if (!(options.body instanceof FormData) && !headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (res.status === 401) {
    clearToken()
    if (!path.startsWith('/auth/')) {
      window.location.href = '/login'
    }
    throw new Error('未登录')
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return res as unknown as T
}

export const api = {
  me: () => request<{ id: number; username: string; display_name: string; role: string }>('/auth/me'),
  callback: (code: string) =>
    request<{ access_token: string; user: { id: number; display_name: string; role: string } }>(
      `/auth/callback?code=${encodeURIComponent(code)}`,
    ),
  createChat: (title: string) =>
    request<{ conversation_id: number; title: string; status: string }>('/api/chat/create', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  deleteChat: (conversation_ids: number[]) =>
    request('/api/chat/delete', { method: 'POST', body: JSON.stringify({ conversation_ids }) }),
  updateChat: (conversation_id: number, title: string) =>
    request('/api/chat/update', { method: 'POST', body: JSON.stringify({ conversation_id, title }) }),
  listChats: () =>
    request<Array<{ conversation_id: number; title: string; status: string; last_message_at: string | null }>>(
      '/api/chat/ls',
    ),
  listMessages: (conversation_id: number) =>
    request<
      Array<{
        message_id: number
        role: string
        content: string
        created_at: string
        attachments: Array<{
          attachment_id: number
          file_name: string
          file_type: string
          file_size: number
          parse_status: string
          created_at: string
        }>
      }>
    >(`/api/chat/ls/${conversation_id}`),
  sendMessage: (conversation_id: number, content: string) =>
    request<{ task_id: number; message_id: number; task_status: string }>('/api/chat/send', {
      method: 'POST',
      body: JSON.stringify({ conversation_id, content }),
    }),
  cancelTask: (task_id: number) =>
    request(`/api/chat/cancel?task_id=${task_id}`, { method: 'POST' }),
  wsToken: (conversation_id: number) =>
    request<{ websocket_token: string; expires_in: number }>('/api/chat/ws-token', {
      method: 'POST',
      body: JSON.stringify({ conversation_id }),
    }),
  upload: async (conversation_id: number, file: File) => {
    const form = new FormData()
    form.append('conversation_id', String(conversation_id))
    form.append('file', file)
    return request<{ attachment_id: number; file_name: string; file_path: string }>('/api/attachment/upload', {
      method: 'POST',
      body: form,
    })
  },
  deleteAttachment: (attachment_id: number) =>
    request('/api/attachment/delete', { method: 'POST', body: JSON.stringify({ attachment_id }) }),
  listAttachments: (conversation_id: number) =>
    request<
      Array<{
        attachment_id: number
        file_name: string
        file_type: string
        file_size: number
        parse_status: string
        created_at: string
      }>
    >(`/api/attachment/ls/${conversation_id}`),
  getTask: (task_id: number) =>
    request<{
      task_status: string
      current_step: string
      started_at: string | null
      finished_at: string | null
      error_message: string | null
    }>(`/api/tasks/${task_id}`),
  getResult: (task_id: number) =>
    request<{
      problem_definition: string
      key_metrics: Array<{ metric_name: string; metric_value: unknown; metric_unit: string; metric_period: string }>
      evidence_list: Array<{
        source_type: string
        source_name: string
        evidence_text: string
        related_metric: string
        confidence: number
      }>
      conclusion_text: string
      missing_data_text: string
      next_action_text: string
      result_markdown: string
      result_file_path: string | null
      result_id: number
    }>(`/api/results/${task_id}`),
  latestResult: (conversation_id: number) =>
    request<{
      problem_definition: string
      key_metrics: Array<{ metric_name: string; metric_value: unknown; metric_unit: string; metric_period: string }>
      evidence_list: Array<{
        source_type: string
        source_name: string
        evidence_text: string
        related_metric: string
        confidence: number
      }>
      conclusion_text: string
      missing_data_text: string
      next_action_text: string
      result_markdown: string
      result_file_path: string | null
      result_id: number
    } | null>(`/api/conversations/${conversation_id}/latest-result`),
  getLogs: (task_id: number) =>
    request<Array<{ id: number; log_level: string; log_type: string; log_content: string; created_at: string }>>(
      `/api/tasks/${task_id}/logs`,
    ),
  reloadConfig: () => request<{ status: string; message: string }>('/api/admin/reload', { method: 'POST' }),
  listConfigs: () =>
    request<Array<{ config_key: string; config_value: string; config_group: string }>>('/api/admin/configs'),
}

export async function downloadWithAuth(path: string, filename: string) {
  const token = getToken()
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error('下载失败')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function downloadAttachment(attachment_id: number, fileName: string) {
  return downloadWithAuth(`/api/attachment/get?attachment_id=${attachment_id}`, fileName)
}

export function downloadResult(task_id: number) {
  return downloadWithAuth(`/api/results/${task_id}/download`, `result_task_${task_id}.md`)
}
