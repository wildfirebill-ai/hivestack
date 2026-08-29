import { FormEvent, useEffect, useRef, useState } from 'react'
import { get, ModelInfo, streamChat, Usage } from '../api'

interface Msg {
  role: 'user' | 'assistant'
  text: string
  meta?: string // model · provider · tokens
  error?: boolean
}

export default function Chat() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [modelName, setModelName] = useState<string>('')
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const tailRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    get<{ models: ModelInfo[]; default_model: string }>('/api/models')
      .then((r) => {
        setModels(r.models)
        const enabled = r.models.filter((m) => m.enabled)
        const preferred =
          r.default_model || enabled.find((m) => m.is_default)?.name || enabled[0]?.name || ''
        setModelName(preferred)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'failed to load models'))
  }, [])

  useEffect(() => {
    tailRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const usable = models.filter((m) => m.enabled)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setError(null)
    setMessages((m) => [...m, { role: 'user', text }])
    setBusy(true)
    const asstIndex = messages.length + 1
    setMessages((m) => [...m, { role: 'assistant', text: '' }])

    await streamChat(
      { message: text, provider: null, model: modelName || null, prompt: null },
      {
        onDelta: (t) =>
          setMessages((m) => m.map((msg, i) => (i === asstIndex ? { ...msg, text: msg.text + t } : msg))),
        onError: (msg) =>
          setMessages((m) =>
            m.map((msg2, i) =>
              i === asstIndex ? { ...msg2, text: `⚠ ${msg}`, error: true } : msg2,
            ),
          ),
        onDone: (info) => {
          setMessages((m) =>
            m.map((msg, i) => {
              if (i !== asstIndex) return msg
              const tokens = info.usage ? `${info.usage.input_tokens}→${info.usage.output_tokens}` : ''
              return {
                ...msg,
                meta: [info.provider, info.model ? `model:${info.model}` : '', tokens && `${tokens} tok`]
                  .filter(Boolean)
                  .join(' · '),
              }
            }),
          )
        },
      },
    )
    setBusy(false)
  }

  return (
    <div className="page chat-page">
      <div className="chat-toolbar">
        <h1>Chat</h1>
        <select
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          disabled={busy || usable.length === 0}
        >
          {usable.length === 0 && <option value="">no models enabled</option>}
          {usable.map((m) => (
            <option key={m.name} value={m.name}>
              {m.name} ({m.provider}/{m.model_id})
            </option>
          ))}
        </select>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="thread">
        {messages.length === 0 && (
          <div className="muted empty">
            {usable.length === 0
              ? 'No models enabled yet — add/enable one in Settings → Models, or pull a model first.'
              : `Pick a model and send a message. Streaming runs through your local engine.`}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}${m.error ? ' err' : ''}`}>
            <div className="bubble-meta">
              {m.role}
              {m.meta ? ` · ${m.meta}` : ''}
            </div>
            <pre className="bubble-text">{m.text}</pre>
          </div>
        ))}
        {busy && <div className="muted">streaming…</div>}
        <div ref={tailRef} />
      </div>
      <form className="compose" onSubmit={submit}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Message the local agent…" />
        <button disabled={busy} type="submit">
          Send
        </button>
      </form>
    </div>
  )
}