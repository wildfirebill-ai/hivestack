import { FormEvent, useCallback, useEffect, useState } from 'react'
import { get, post } from '../api'

interface WorkflowInfo {
  id: string
  name: string
  enabled: boolean
}

interface RunSummary {
  id: string
  workflow_id: string
  status: string
  current_step?: string
  error?: string
  created_at?: string
}

interface StepRun {
  id: number
  step_id: string
  status: string
  attempts: number
  output?: string
}

interface RunDetail extends RunSummary {
  steps: StepRun[]
  context?: Record<string, string>
}

interface ScheduleInfo {
  id: string
  workflow_id: string
  kind: string
  value: string
  enabled: boolean
  next_run_at?: string
}

const SAMPLE = `{
  "steps": [
    {"id": "s1", "type": "tool", "tool": "calculator", "args": {"expression": "1+1"}},
    {"id": "s2", "type": "tool", "tool": "calculator", "args": {"expression": "2+2"}},
    {"id": "agg", "type": "tool", "tool": "calculator", "args": {"expression": "3+4"}, "deps": ["s1", "s2"]},
    {"id": "gate", "type": "wait", "seconds": 1, "mode": "approval", "note": "review before release", "deps": ["agg"]},
    {"id": "done", "type": "tool", "tool": "calculator", "args": {"expression": "7*7"}, "deps": ["gate"]}
  ]
}`

export default function Workflows() {
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([])
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [schedules, setSchedules] = useState<ScheduleInfo[]>([])
  const [name, setName] = useState('')
  const [defText, setDefText] = useState(SAMPLE)
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // schedule form
  const [sWf, setSWf] = useState('')
  const [sKind, setSKind] = useState('interval')
  const [sValue, setSValue] = useState('3600')

  const refresh = useCallback(async () => {
    const [w, r, s] = await Promise.all([
      get<{ workflows: WorkflowInfo[] }>('/api/workflows'),
      get<{ runs: RunSummary[] }>('/api/workflows/runs/list'),
      get<{ schedules: ScheduleInfo[] }>('/api/workflows/schedules/list'),
    ])
    setWorkflows(w.workflows)
    setRuns(r.runs)
    setSchedules(s.schedules)
  }, [])

  useEffect(() => {
    refresh().catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [refresh])

  async function createWf(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setNotice(null)
    try {
      const definition = JSON.parse(defText)
      await post('/api/workflows', { name: name || 'untitled', definition })
      await refresh()
      setNotice('workflow created')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'invalid definition JSON')
    } finally {
      setBusy(false)
    }
  }

  async function runWf(id: string) {
    await post(`/api/workflows/${id}/run`, {})
    setNotice('run started')
    setTimeout(refresh, 1500)
  }

  async function openRun(id: string) {
    setDetail(await get<RunDetail>(`/api/workflows/runs/${id}`))
  }

  async function act(path: string, body?: unknown, reload = true) {
    try {
      await post(path, body ?? {})
      if (reload) {
        await refresh()
        if (detail) setDetail(await get<RunDetail>(`/api/workflows/runs/${detail.id}`))
      }
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'action failed')
    }
  }

  async function addSchedule(e: FormEvent) {
    e.preventDefault()
    if (!sWf) return
    try {
      await post('/api/workflows/schedules', { workflow_id: sWf, kind: sKind, value: sValue, enabled: true })
      await refresh()
      setNotice('schedule added')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'schedule failed')
    }
  }

  function del(path: string) {
    const token = localStorage.getItem('hivestack_token')
    return fetch(path, { method: 'DELETE', headers: token ? { Authorization: `Bearer ${token}` } : {} })
  }

  const statusColor: Record<string, string> = {
    running: 'var(--accent)',
    awaiting_approval: 'var(--orange)',
    completed: 'var(--green)',
    failed: 'var(--red)',
    cancelled: 'var(--muted)',
  }

  return (
    <div className="page">
      <h1>Workflows</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Create workflow</h3>
        <form className="ag-form" onSubmit={createWf}>
          <input placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
          <textarea
            rows={10}
            value={defText}
            onChange={(e) => setDefText(e.target.value)}
            style={{ fontFamily: 'var(--mono)', fontSize: 12 }}
          />
          <div>
            <button disabled={busy} type="submit">
              Create
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h3 className="card-title">Workflows ({workflows.length})</h3>
        <table className="table">
          <tbody>
            {workflows.map((w) => (
              <tr key={w.id}>
                <td className="prompt-name">{w.name}</td>
                <td className="prompt-desc">{w.id}</td>
                <td className="actions">
                  <button onClick={() => runWf(w.id)}>run</button>
                  <button onClick={() => del(`/api/workflows/${w.id}`).then(() => refresh())}>delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3 className="card-title">Runs ({runs.length})</h3>
        <table className="table">
          <thead>
            <tr>
              <th>id</th>
              <th>wf</th>
              <th>status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td className="prompt-name">{r.id}</td>
                <td className="prompt-desc">{r.workflow_id}</td>
                <td>
                  <span className="kind" style={{ color: statusColor[r.status] ?? 'var(--text)' }}>
                    {r.status}
                  </span>
                </td>
                <td className="actions">
                  <button onClick={() => openRun(r.id)}>view</button>
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
            Run {detail.id} —{' '}
            <span className="kind" style={{ color: statusColor[detail.status] }}>
              {detail.status}
            </span>
          </h3>
          {detail.error && <div className="error">{detail.error}</div>}
          {detail.status === 'awaiting_approval' && (
            <div className="actions" style={{ margin: '8px 0' }}>
              <button className="scope-on" onClick={() => act(`/api/workflows/runs/${detail.id}/approve`, { approve: true })}>
                approve
              </button>
              <button className="scope-off" onClick={() => act(`/api/workflows/runs/${detail.id}/approve`, { approve: false })}>
                deny
              </button>
            </div>
          )}
          {detail.status === 'failed' && (
            <button onClick={() => act(`/api/workflows/runs/${detail.id}/resume`)}>resume</button>
          )}
          {(detail.status === 'running' || detail.status === 'awaiting_approval') && (
            <button style={{ marginLeft: 8 }} onClick={() => act(`/api/workflows/runs/${detail.id}/cancel`)}>
              cancel
            </button>
          )}
          <table className="table">
            <thead>
              <tr>
                <th>step</th>
                <th>status</th>
                <th>attempts</th>
                <th>output</th>
              </tr>
            </thead>
            <tbody>
              {detail.steps.map((s) => {
                let out = s.output || ''
                try {
                  const o = JSON.parse(out)
                  out = typeof o === 'string' ? o : JSON.stringify(o)
                } catch { /* keep */ }
                return (
                  <tr key={s.id}>
                    <td className="prompt-name">{s.step_id}</td>
                    <td>
                      <span className="kind" style={{ color: statusColor[s.status] ?? 'var(--text)' }}>
                        {s.status}
                      </span>
                    </td>
                    <td>{s.attempts}</td>
                    <td className="prompt-desc">{out.slice(0, 80)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      )}

      <section className="card">
        <h3 className="card-title">Schedules</h3>
        <table className="table">
          <tbody>
            {schedules.map((s) => (
              <tr key={s.id}>
                <td className="prompt-name">{s.kind} {s.value}</td>
                <td className="prompt-desc">wf {s.workflow_id}</td>
                <td>{s.enabled ? 'on' : 'off'}</td>
                <td className="prompt-desc">{s.next_run_at ?? ''}</td>
                <td className="actions">
                  <button onClick={() => del(`/api/workflows/schedules/${s.id}`).then(() => refresh())}>delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form className="form-row" onSubmit={addSchedule}>
          <select value={sWf} onChange={(e) => setSWf(e.target.value)}>
            <option value="">workflow…</option>
            {workflows.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          <select value={sKind} onChange={(e) => setSKind(e.target.value)}>
            <option value="interval">interval</option>
            <option value="cron">cron</option>
          </select>
          <input placeholder={sKind === 'interval' ? 'seconds' : '* * * * *'} value={sValue} onChange={(e) => setSValue(e.target.value)} style={{ flex: 1 }} />
          <button type="submit">add</button>
        </form>
      </section>
    </div>
  )
}