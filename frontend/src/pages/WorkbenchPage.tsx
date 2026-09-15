import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { api, clearToken, downloadAttachment, downloadResult, getToken } from '../api'
import { useChatSocket, type WsEvent } from '../hooks/useChatSocket'

type Conversation = {
  conversation_id: number
  title: string
  status: string
  last_message_at: string | null
}

type Message = {
  message_id: number
  role: string
  content: string
  created_at: string
}

type Attachment = {
  attachment_id: number
  file_name: string
  file_type: string
  file_size: number
  parse_status: string
  created_at: string
}

type AnalysisResult = {
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
  result_id?: number
  task_id?: number
}

type TaskView = {
  task_id: number | null
  task_status: string
  current_step: string
  error_message: string
  stream: string
  tools: string[]
}

const emptyTask: TaskView = {
  task_id: null,
  task_status: 'idle',
  current_step: '-',
  error_message: '',
  stream: '',
  tools: [],
}

export function WorkbenchPage() {
  const [user, setUser] = useState<{ display_name: string; role: string } | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [input, setInput] = useState('')
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [task, setTask] = useState<TaskView>(emptyTask)
  const [showAttachments, setShowAttachments] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  const loadConversations = useCallback(async () => {
    const list = await api.listChats()
    setConversations(list)
    return list
  }, [])

  const loadConversationDetail = useCallback(async (id: number) => {
    const [msgs, atts, latest] = await Promise.all([
      api.listMessages(id),
      api.listAttachments(id),
      api.latestResult(id),
    ])
    setMessages(msgs)
    setAttachments(atts)
    setResult(latest)
  }, [])

  useEffect(() => {
    if (!getToken()) {
      window.location.href = '/login'
      return
    }
    api
      .me()
      .then((u) => setUser({ display_name: u.display_name, role: u.role }))
      .catch(() => {
        clearToken()
        window.location.href = '/login'
      })
    loadConversations().then((list) => {
      if (list.length) {
        setActiveId(list[0].conversation_id)
      }
    })
  }, [loadConversations])

  useEffect(() => {
    if (activeId != null) {
      setTask(emptyTask)
      loadConversationDetail(activeId).catch((e: Error) => setNotice(e.message))
    }
  }, [activeId, loadConversationDetail])

  const onWsEvent = useCallback(
    async (ev: WsEvent) => {
      if (ev.type === 'message_start') {
        setTask((t) => ({
          ...t,
          task_id: ev.task_id ?? t.task_id,
          task_status: 'running',
          current_step: 'preparing',
          stream: '',
          tools: [],
          error_message: '',
        }))
      }
      if (ev.type === 'message_delta' && ev.delta_text) {
        setTask((t) => ({ ...t, stream: t.stream + ev.delta_text }))
      }
      if (ev.type === 'tool_start' && ev.tool_name) {
        setTask((t) => ({ ...t, tools: [...t.tools, `▶ ${ev.tool_name}`], current_step: ev.tool_name || t.current_step }))
      }
      if (ev.type === 'tool_finish' && ev.tool_name) {
        setTask((t) => ({
          ...t,
          tools: [...t.tools, `✓ ${ev.tool_name}: ${ev.tool_result_summary || ''}`],
        }))
      }
      if (ev.type === 'task_status') {
        setTask((t) => ({
          ...t,
          task_status: ev.task_status || t.task_status,
          current_step: ev.current_step || t.current_step,
        }))
      }
      if (ev.type === 'result_ready' && ev.task_id) {
        const r = await api.getResult(ev.task_id)
        setResult({ ...r, task_id: ev.task_id })
        if (activeId) await loadConversationDetail(activeId)
      }
      if (ev.type === 'error') {
        setTask((t) => ({
          ...t,
          task_status: 'failed',
          error_message: ev.error_message || '分析失败',
        }))
      }
      if (ev.type === 'done') {
        setTask((t) => ({
          ...t,
          task_status: t.task_status === 'failed' || t.task_status === 'cancelled' ? t.task_status : 'success',
          current_step: 'done',
        }))
        setBusy(false)
        await loadConversations()
      }
    },
    [activeId, loadConversationDetail, loadConversations],
  )

  const { connected, startTask, cancelTask, reconnect } = useChatSocket(activeId, onWsEvent)

  const createConversation = async () => {
    const title = `分析 ${new Date().toLocaleString()}`
    const created = await api.createChat(title)
    await loadConversations()
    setActiveId(created.conversation_id)
  }

  const renameConversation = async (id: number) => {
    const title = prompt('新的会话标题')
    if (!title) return
    await api.updateChat(id, title)
    await loadConversations()
  }

  const deleteConversation = async (id: number) => {
    if (!confirm('删除会话将同时删除消息、附件与结果，确认？')) return
    await api.deleteChat([id])
    const list = await loadConversations()
    if (activeId === id) {
      setActiveId(list[0]?.conversation_id ?? null)
      setMessages([])
      setAttachments([])
      setResult(null)
    }
  }

  const onSend = async (e: FormEvent) => {
    e.preventDefault()
    if (!activeId || !input.trim() || busy) return
    setBusy(true)
    setNotice('')
    try {
      if (!connected) await reconnect()
      const res = await api.sendMessage(activeId, input.trim())
      setInput('')
      setMessages((m) => [
        ...m,
        {
          message_id: res.message_id,
          role: 'user',
          content: input.trim(),
          created_at: new Date().toISOString(),
        },
      ])
      setTask({
        task_id: res.task_id,
        task_status: res.task_status,
        current_step: 'queued',
        error_message: '',
        stream: '',
        tools: [],
      })
      // slight delay to ensure ws ready
      setTimeout(() => startTask(res.task_id), 150)
    } catch (err) {
      setBusy(false)
      setNotice(err instanceof Error ? err.message : String(err))
    }
  }

  const onUpload = async (file: File | null) => {
    if (!file || !activeId) return
    await api.upload(activeId, file)
    setAttachments(await api.listAttachments(activeId))
    setNotice(`已上传 ${file.name}`)
  }

  const onCancel = async () => {
    if (!task.task_id) return
    cancelTask(task.task_id)
    await api.cancelTask(task.task_id)
    setBusy(false)
    setTask((t) => ({ ...t, task_status: 'cancelled', current_step: 'cancelled' }))
  }

  const copyResult = async () => {
    if (!result) return
    await navigator.clipboard.writeText(result.result_markdown || result.conclusion_text)
    setNotice('结果已复制')
  }

  const reloadConfig = async () => {
    try {
      const res = await api.reloadConfig()
      setNotice(res.message)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err))
    }
  }

  const activeTitle = useMemo(
    () => conversations.find((c) => c.conversation_id === activeId)?.title || '未选择会话',
    [conversations, activeId],
  )

  return (
    <div className="workbench">
      <aside className="sidebar">
        <div className="sidebar-head">
          <div>
            <p className="brand-sm">经营归因</p>
            <strong>{user?.display_name || '用户'}</strong>
          </div>
          <button type="button" className="btn small" onClick={() => createConversation()}>
            新建
          </button>
        </div>
        <ul className="conv-list">
          {conversations.map((c) => (
            <li key={c.conversation_id} className={c.conversation_id === activeId ? 'active' : ''}>
              <button type="button" className="conv-main" onClick={() => setActiveId(c.conversation_id)}>
                {c.title}
              </button>
              <div className="conv-actions">
                <button type="button" onClick={() => renameConversation(c.conversation_id)}>
                  改
                </button>
                <button type="button" onClick={() => deleteConversation(c.conversation_id)}>
                  删
                </button>
              </div>
            </li>
          ))}
        </ul>
        <div className="sidebar-foot">
          <button type="button" className="btn ghost small" onClick={() => setShowAttachments((v) => !v)}>
            {showAttachments ? '隐藏附件' : '附件侧栏'}
          </button>
          {user?.role === 'admin' && (
            <button type="button" className="btn ghost small" onClick={reloadConfig}>
              重载配置
            </button>
          )}
          <button
            type="button"
            className="btn ghost small"
            onClick={() => {
              clearToken()
              window.location.href = '/login'
            }}
          >
            退出
          </button>
        </div>
      </aside>

      <main className="center">
        <header className="center-head">
          <div>
            <h2>{activeTitle}</h2>
            <p className="meta">
              WS {connected ? '已连接' : '未连接'} · 任务 {task.task_status} / {task.current_step}
            </p>
          </div>
          {busy && (
            <button type="button" className="btn danger small" onClick={onCancel}>
              取消分析
            </button>
          )}
        </header>

        <div className="chat-area">
          {messages.map((m) => (
            <div key={m.message_id} className={`bubble ${m.role}`}>
              <span className="role">{m.role}</span>
              <pre>{m.content}</pre>
            </div>
          ))}
          {task.stream && (
            <div className="bubble assistant live">
              <span className="role">live</span>
              <pre>{task.stream}</pre>
            </div>
          )}
        </div>

        <section className="task-panel">
          <h3>实时任务</h3>
          <p>
            状态：{task.task_status} · 步骤：{task.current_step}
          </p>
          {task.error_message && <p className="error">{task.error_message}</p>}
          <ul>
            {task.tools.map((t, i) => (
              <li key={`${t}-${i}`}>{t}</li>
            ))}
          </ul>
        </section>

        <form className="composer" onSubmit={onSend}>
          <label className="upload-btn">
            上传
            <input
              type="file"
              hidden
              onChange={(e) => {
                void onUpload(e.target.files?.[0] || null)
                e.target.value = ''
              }}
            />
          </label>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入经营分析问题，例如：近30天商品目录转化为何下降？"
            disabled={!activeId || busy}
          />
          <button className="btn primary" type="submit" disabled={!activeId || busy || !input.trim()}>
            发送
          </button>
        </form>
        {notice && <p className="notice">{notice}</p>}
      </main>

      <aside className="right">
        {showAttachments && (
          <section className="panel">
            <h3>附件</h3>
            <ul className="att-list">
              {attachments.map((a) => (
                <li key={a.attachment_id}>
                  <div>
                    <strong>{a.file_name}</strong>
                    <p>
                      {a.file_type} · {(a.file_size / 1024).toFixed(1)} KB · {a.parse_status}
                    </p>
                    <p className="meta">{new Date(a.created_at).toLocaleString()}</p>
                  </div>
                  <div className="att-actions">
                    <button
                      type="button"
                      onClick={() => downloadAttachment(a.attachment_id, a.file_name).catch((e: Error) => setNotice(e.message))}
                    >
                      下载
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        await api.deleteAttachment(a.attachment_id)
                        if (activeId) setAttachments(await api.listAttachments(activeId))
                      }}
                    >
                      删除
                    </button>
                  </div>
                </li>
              ))}
              {!attachments.length && <li className="empty">暂无附件</li>}
            </ul>
          </section>
        )}

        <section className="panel result-panel">
          <div className="panel-head">
            <h3>分析结果</h3>
            <div className="panel-actions">
              <button type="button" className="btn ghost small" onClick={copyResult} disabled={!result}>
                复制
              </button>
              {result?.task_id && (
                <button
                  type="button"
                  className="btn ghost small"
                  onClick={() => downloadResult(result.task_id!).catch((e: Error) => setNotice(e.message))}
                >
                  导出
                </button>
              )}
            </div>
          </div>
          {!result ? (
            <p className="empty">本轮结果将展示在这里</p>
          ) : (
            <div className="result-body">
              <h4>问题定义</h4>
              <p>{result.problem_definition}</p>
              <h4>关键指标</h4>
              <ul>
                {result.key_metrics.map((m) => (
                  <li key={m.metric_name}>
                    {m.metric_name}：{String(m.metric_value)}
                    {m.metric_unit}（{m.metric_period}）
                  </li>
                ))}
              </ul>
              <h4>证据列表</h4>
              <ul>
                {result.evidence_list.map((e, i) => (
                  <li key={`${e.source_name}-${i}`}>
                    <strong>{e.source_name}</strong> — {e.evidence_text}
                    <span className="meta"> · 置信度 {e.confidence}</span>
                  </li>
                ))}
              </ul>
              <h4>归因结论</h4>
              <p>{result.conclusion_text}</p>
              <h4>待补充数据</h4>
              <p>{result.missing_data_text}</p>
              <h4>下一步建议</h4>
              <pre>{result.next_action_text}</pre>
            </div>
          )}
        </section>
      </aside>
    </div>
  )
}
