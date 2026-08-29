import { FormEvent, useCallback, useEffect, useState } from 'react'
import { get, ModelInfo, post } from '../api'

interface RunInfo {
  id: string
  name: string
  goal: string
  status: string
  provider?: string
  model?: string
  error?: string
  tokens_in?: number
  tokens_out?: number
  created_at?: string
  updated_at?: string
}

interface EventRow {
  id: number
  kind: string
  data: string
  created_at: string
}

interface RunDetail extends RunInfo {
  events: EventRow[]
  tokens_in?: number
  tokens_out?: number
}

interface ToolInfo {
  name: string
  description: string
  scope: string
  network: boolean
}

const SCOPES = ['low', 'medium', 'high'] as const

export default function Agents() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [model, setModel] = useState('')
  const [goal, setGoal] = useState('')
  const [name, setName] = useState('')
  const [maxSteps, setMaxSteps] = useState(8)
  const [scopes, setScopes] = useState<string[]>(['low', 'medium'])
  const [tasks, setTasks] = useState<RunInfo[]>([])
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const [t, tl] = await Promise.all([
      get<{ tasks: RunInfo[] }>('/api/agents/tasks'),
      get<{ tools: ToolInfo[] }>('/api/agents/tools'),
    ])
    setTasks(t.tasks)
    setTools(tl.tools)
  }, [])

  useEffect(() => {
    get<{ models: ModelInfo[]; default_model: string }>('/api/models')
      .then((r) => {
        const enabled = r.models.filter((m) => m.enabled)
        setModels(enabled)
        setModel(r.default_model || enabled[0]?.name || '')
      })
      .catch((err) => setNotice(err instanceof Error ? err.message : 'failed to load models'))
    refresh().catch((err) => setNotice(err instanceof Error ? err.message : 'failed to load'))
  }, [refresh])

  async function run(e: FormEvent) {
    e.preventDefault()
    if (!goal.trim() || busy) return
    setBusy(true)
    setNotice(null)
    try {
      const created = await post<RunInfo>('/api/agents/tasks', {
        goal,
        name,
        model: model || null,
        max_steps: maxSteps,
        allowed_scopes: scopes,
      })
      setNotice(`run started: ${created.id}`)
      setDetail(await get<RunDetail>(`/api/agents/tasks/${created.id}`))
      setTimeout(refresh, 1500)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'failed to start run')
    } finally {
      setBusy(false)
    }
  }

  async function openDetail(id: string) {
    setDetail(await get<RunDetail>(`/api/agents/tasks/${id}`))
  }

  async function cancelRun(id: string) {
    await post(`/api/agents/tasks/${id}/cancel`, {})
    setNotice('cancel requested')
    setTimeout(refresh, 1500)
  }

  function toggleScope(s: string) {
    setScopes((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]))
  }

  const kindColor: Record<string, string> = {
    started: 'var(--accent)',
    llm: 'var(--green)',
    tool_call: 'var(--orange)',
    tool_result: 'var(--green)',
    tool_denied: 'var(--red)',
    tool_error: 'var(--red)',
    error: 'var(--red)',
    completed: 'var(--green)',
    cancelled: 'var(--muted)',
  }

  return (
    <div className="page">
      <h1>Agents</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Run an agent task</h3>
        <form className="ag-form" onSubmit={run}>
          <label>
            Goal
            <textarea
              rows={2}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. List the workspace, read notes.txt, then summarize your findings into summary.md"
            />
          </label>
          <div className="form-row">
            <input placeholder="name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {models.length === 0 && <option value="">no enabled models</option>}
              {models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
            <input
              type="number"
              min={1}
              max={40}
              value={maxSteps}
              onChange={(e) => setMaxSteps(Number(e.target.value))}
              style={{ width: 90 }}
            />
            <span className="muted small">max steps</span>
          </div>
          <div className="form-row">
            <span className="muted small">permitted scopes:</span>
            {SCOPES.map((s) => (
              <button
                key={s}
                type="button"
                className={scopes.includes(s) ? 'scope-on' : 'scope-off'}
                onClick={() => toggleScope(s)}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="form-row">
            <button disabled={busy || !goal.trim()} type="submit">
              {busy ? 'starting…' : 'Run task'}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h3 className="card-title">Tools ({tools.length})</h3>
        <table className="table">
          <tbody>
            {tools.map((t) => (
              <tr key={t.name}>
                <td className="prompt-name">{t.name}</td>
                <td>{t.description.slice(0, 90)}</td>
                <td>
                  <code className={`badge scope-${t.scope}`}>{t.scope}</code>
                </td>
                <td>{t.network ? 'net' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3 className="card-title">Runs ({tasks.length})</h3>
        <table className="table">
          <thead>
            <tr>
              <th>id</th>
              <th>status</th>
              <th>goal</th>
              <th>tokens</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td className="prompt-name">{t.id}</td>
                <td>{t.status}</td>
                <td className="prompt-desc">{t.goal.slice(0, 60)}</td>
                <td>
                  {t.tokens_in}/{t.tokens_out}
                </td>
                <td className="actions">
                  <button onClick={() => openDetail(t.id)}>view</button>
                  {t.status === 'running' && <button onClick={() => cancelRun(t.id)}>cancel</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={refresh} style={{ marginTop: 10 }}>
          refresh
        </button>
      </section>

      {detail && (
        <section className="card">
          <h3 className="card-title">
            Run {detail.id} — <span className="muted">{detail.status}</span>
          </h3>
          <p className="muted small">{detail.goal}</p>
          {detail.error && <div className="error">{detail.error}</div>}
          <div className="event-list">
            {detail.events.map((ev) => {
              let label = ev.kind
              try {
                const d = JSON.parse(ev.data)
                if (d.step) label += ` #${d.step}`
                if (d.tool) label += ` · ${d.tool}`
                if (ev.kind === 'llm' && d.content) label += ` · ${d.content.slice(0, 60)}`
                if (ev.kind === 'tool_result' && d.out) label += ` · ${d.out.slice(0, 60)}`
                if (ev.kind === 'tool_denied' && d.reason) label += ` · ${d.reason}`
              } catch {
                /* keep bare kind */
              }
              return (
                <div key={ev.id} className="event-row">
                  <span className="kind" style={{ color: kindColor[ev.kind] ?? 'var(--text)' }}>
                    {ev.kind}
                  </span>
                  <span className="prompt-desc">{label.replace(/^[a-z_]+/, '')}</span>
                </div>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}