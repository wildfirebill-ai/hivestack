import { useEffect, useState } from 'react'
import { get, post } from '../api'

interface Dashboard {
  today: { calls: number; in_tokens: number; out_tokens: number; total: number }
  runs: Record<string, number>
  incidents: Record<string, number>
  alerts: Record<string, number>
  audit_entries: number
  users: number
  budget: { tokens_used: number; budget: number; pct: number; exceeded: boolean; cost_est: number }
}

interface BudgetCfg {
  enabled: boolean
  budget_enabled: boolean
  daily_token_budget: number
  per_run_token_limit: number
}

interface AuditRow {
  id: number
  ts: string
  actor: string
  action: string
  subject: string
  detail: string
}

export default function Governance() {
  const [dash, setDash] = useState<Dashboard | null>(null)
  const [cfg, setCfg] = useState<BudgetCfg | null>(null)
  const [users, setUsers] = useState<{ name: string; role: string }[]>([])
  const [audit, setAudit] = useState<AuditRow[]>([])
  const [sec, setSec] = useState<{ score: number; checks: { name: string; pass: boolean; detail: string }[] } | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // forms
  const [daily, setDaily] = useState('500000')
  const [perRun, setPerRun] = useState('120000')
  const [uName, setUName] = useState('')
  const [uPass, setUPass] = useState('')
  const [uRole, setURole] = useState('operator')
  const [runId, setRunId] = useState('')
  const [tick, setTick] = useState(0)

  useEffect(() => {
    Promise.all([
      get<Dashboard>('/api/governance/dashboard'),
      get<{ config: BudgetCfg }>('/api/governance/budget'),
      get<{ users: { name: string; role: string }[] }>('/api/governance/users'),
      get<{ entries: AuditRow[] }>('/api/governance/audit'),
      get<{ score: number; checks: { name: string; pass: boolean; detail: string }[] }>('/api/governance/security-review'),
    ])
      .then(([d, b, u, a, s]) => {
        setDash(d)
        setCfg(b.config)
        setUsers(u.users)
        setAudit(a.entries)
        setSec(s)
        setDaily(String(b.config.daily_token_budget))
        setPerRun(String(b.config.per_run_token_limit))
      })
      .catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [tick])

  async function saveBudget() {
    try {
      await post('/api/governance/budget', {
        daily_token_budget: Number(daily),
        per_run_token_limit: Number(perRun),
        budget_enabled: true,
      })
      setNotice('budget updated')
      setTick((x) => x + 1)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'save failed')
    }
  }

  async function addUser() {
    if (!uName || !uPass) return
    try {
      await post('/api/governance/users', { name: uName, password: uPass, role: uRole })
      setUName('')
      setUPass('')
      setTick((x) => x + 1)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'add user failed')
    }
  }

  async function roleChange(name: string, role: string) {
    await post(`/api/governance/users/${name}/role`, { role })
    setTick((x) => x + 1)
  }

  function delUser(name: string) {
    const token = localStorage.getItem('hivestack_token')
    return fetch(`/api/governance/users/${name}`, { method: 'DELETE', headers: token ? { Authorization: `Bearer ${token}` } : {} }).then(() => setTick((x) => x + 1))
  }

  async function verifyRun() {
    if (!runId) return
    try {
      const r = await post<{ verified: boolean; checks: { name: string; pass: boolean }[] }>(`/api/governance/verify/${runId}`, {})
      setNotice(`verify ${runId}: ${r.verified ? 'PASS' : 'FAIL'} — ${r.checks.map((c) => `${c.name}=${c.pass}`).join(', ')}`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'verify failed')
    }
  }

  return (
    <div className="page">
      <h1>Governance</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Posture</h3>
        <div className="cards">
          <div className="card" style={{ margin: 0 }}>
            <Row label="security review" value={sec ? `${sec.score}%` : '…'} />
            <Row label="audit entries" value={String(dash?.audit_entries ?? 0)} />
            <Row label="users" value={String(dash?.users ?? 0)} />
          </div>
          <div className="card" style={{ margin: 0 }}>
            <Row label="today tokens" value={String(dash?.today.total ?? 0)} />
            <Row label="today calls" value={String(dash?.today.calls ?? 0)} />
            <Row label="est. cost" value={`$${(dash?.budget.cost_est ?? 0).toFixed(4)}`} />
          </div>
          <div className="card" style={{ margin: 0 }}>
            <Row label="runs" value={statusSummary(dash?.runs)} />
            <Row label="incidents" value={statusSummary(dash?.incidents)} />
            <Row label="alerts" value={statusSummary(dash?.alerts)} />
          </div>
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">Budget &amp; cost caps</h3>
        <div className="budget-bar">
          <div className="budget-fill" style={{ width: `${Math.min((dash?.budget.pct ?? 0), 100)}%` }} />
        </div>
        <p className="muted small">
          {dash?.budget.tokens_used ?? 0} / {dash?.budget.budget ?? 0} tokens daily (
          {dash?.budget.pct ?? 0}%){dash?.budget.exceeded ? ' — EXCEEDED, new runs blocked' : ''}
        </p>
        <div className="form-row">
          <label className="muted small">daily budget (tokens)</label>
          <input value={daily} onChange={(e) => setDaily(e.target.value)} style={{ width: 140 }} />
          <label className="muted small">per-run limit</label>
          <input value={perRun} onChange={(e) => setPerRun(e.target.value)} style={{ width: 140 }} />
          <button onClick={saveBudget}>save (admin)</button>
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">Users / RBAC</h3>
        <table className="table">
          <tbody>
            {users.map((u) => (
              <tr key={u.name}>
                <td className="prompt-name">{u.name}</td>
                <td>{u.role}</td>
                <td className="actions">
                  <select value={u.role} onChange={(e) => roleChange(u.name, e.target.value)}>
                    <option value="viewer">viewer</option>
                    <option value="operator">operator</option>
                    <option value="admin">admin</option>
                  </select>
                  <button onClick={() => delUser(u.name)}>delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="form-row">
          <input placeholder="name" value={uName} onChange={(e) => setUName(e.target.value)} />
          <input placeholder="password (≥6)" value={uPass} onChange={(e) => setUPass(e.target.value)} />
          <select value={uRole} onChange={(e) => setURole(e.target.value)}>
            <option value="operator">operator</option>
            <option value="viewer">viewer</option>
            <option value="admin">admin</option>
          </select>
          <button onClick={addUser}>add user</button>
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">Immutable audit ({audit.length})</h3>
        <div className="event-list">
          {audit.slice(0, 60).map((e) => (
            <div key={e.id} className="event-row">
              <span className="prompt-name">{e.ts?.slice(0, 19)}</span>
              <span className="kind">{e.actor || 'system'}</span>
              <span>{e.action}</span>
              <span className="prompt-desc">{e.subject ?? ''} {e.detail?.slice(0, 40)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">Security checks</h3>
        {sec && (
          <table className="table">
            <tbody>
              {sec.checks.map((c) => (
                <tr key={c.name}>
                  <td className="prompt-name">{c.name}</td>
                  <td style={{ color: c.pass ? 'var(--green)' : 'var(--red)' }}>{c.pass ? 'PASS' : 'FAIL'}</td>
                  <td className="prompt-desc">{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3 className="card-title">Verification gate</h3>
        <div className="form-row">
          <input placeholder="agent run id" value={runId} onChange={(e) => setRunId(e.target.value)} style={{ flex: 1 }} />
          <button onClick={verifyRun}>verify</button>
        </div>
      </section>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="row">
      <span className="muted">{label}</span>
      <span>{value}</span>
    </div>
  )
}

function statusSummary(rec?: Record<string, number>): string {
  if (!rec) return '…'
  const entries = Object.entries(rec)
  return entries.length ? entries.map(([k, v]) => `${k}:${v}`).join(' ') : '0'
}