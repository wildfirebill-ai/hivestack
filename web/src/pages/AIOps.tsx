import { useEffect, useState } from 'react'
import { get, post } from '../api'

interface DemoResult {
  ok: boolean
  metric?: string
  anomalies: { ts: string; value: number }[]
  rca?: { root: { name: string }; affected: string[] }
  incident_id?: string
  alert_id?: string
  remediation_id?: string
  reason?: string
}

interface Incident {
  id: string
  title: string
  status: string
  symptom: string
  events?: { id: number; kind: string; data: string }[]
}

interface Alert {
  id: string
  name: string
  severity: string
  status: string
  message: string
}

interface ChaosRun {
  id: string
  target: string
  fault_type: string
  status: string
}

export default function AIOps() {
  const [target, setTarget] = useState('db')
  const [fault, setFault] = useState('latency')
  const [demo, setDemo] = useState<DemoResult | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [inc, setInc] = useState<Incident | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [chaos, setChaos] = useState<ChaosRun[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [runTargets, setRunTargets] = useState<{ name: string }[]>([])
  const [tick, setTick] = useState(0)
  const refresh = () => setTick((x) => x + 1)

  useEffect(() => {
    Promise.all([
      get<{ incidents: Incident[] }>('/api/aiops/incidents'),
      get<{ alerts: Alert[] }>('/api/aiops/alerts'),
      get<{ runs: ChaosRun[] }>('/api/aiops/chaos'),
      get<{ targets: { name: string }[] }>('/api/aiops/chaos/targets'),
    ])
      .then(([i, a, c, t]) => {
        setIncidents(i.incidents)
        setAlerts(a.alerts)
        setChaos(c.runs)
        setRunTargets(t.targets)
      })
      .catch(() => undefined)
  }, [tick])

  async function runDemo() {
    setBusy(true)
    setNotice(null)
    try {
      const r = await post<DemoResult>('/api/aiops/demo', { target, fault_type: fault })
      setDemo(r)
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'demo failed')
    } finally {
      setBusy(false)
    }
  }

  async function approve(remId: string) {
    try {
      const r = await post<{ verified: boolean; status: string }>(`/api/aiops/remediation/${remId}/approve`, { approve: true })
      setNotice(`approved → ${r.status} (verified=${r.verified})`)
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'approval failed')
    }
  }

  async function openIncident(id: string) {
    setInc(await get<Incident>(`/api/aiops/incidents/${id}`))
  }

  async function postmortem(id: string) {
    try {
      const r = await post<{ path: string }>(`/api/aiops/incidents/${id}/postmortem`, {})
      setNotice(`postmortem → ${r.path}`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'postmortem failed')
    }
  }

  async function alertStatus(id: string, status: string) {
    await post(`/api/aiops/alerts/${id}/status`, { status })
    await refresh()
  }

  return (
    <div className="page">
      <h1>AIOps</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Demo: inject fault → detect → alert → incident → approve</h3>
        <div className="form-row">
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {(runTargets.length === 0 ? [{ name: 'web-api' }, { name: 'db' }, { name: 'worker' }] : runTargets).map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
              </option>
            ))}
          </select>
          <select value={fault} onChange={(e) => setFault(e.target.value)}>
            <option value="latency">latency</option>
            <option value="cpu_spike">cpu spike</option>
            <option value="down">down</option>
          </select>
          <button disabled={busy} onClick={runDemo}>
            {busy ? 'running…' : 'run incident demo'}
          </button>
        </div>
        {demo && (
          <div className="bubble-text" style={{ marginTop: 8 }}>
            {demo.ok ? (
              <>
                fault on <b>{demo.metric}</b> — {demo.anomalies.length} anomaly readings · RCA root:{' '}
                <b>{demo.rca?.root.name}</b> · affected: {demo.rca?.affected.join(', ')}
                <br />
                incident {demo.incident_id} · alert {demo.alert_id}
                {demo.remediation_id && (
                  <>
                    <br />
                    <button onClick={() => approve(demo.remediation_id!)} className="scope-on" style={{ marginTop: 6 }}>
                      approve remediation &amp; verify recovery
                    </button>
                  </>
                )}
              </>
            ) : (
              `no anomalies: ${demo.reason}`
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h3 className="card-title">Incidents ({incidents.length})</h3>
        <table className="table">
          <tbody>
            {incidents.map((i) => (
              <tr key={i.id}>
                <td className="prompt-name">{i.title}</td>
                <td>{i.status}</td>
                <td className="prompt-desc">{i.symptom}</td>
                <td className="actions">
                  <button onClick={() => openIncident(i.id)}>view</button>
                  <button onClick={() => postmortem(i.id)}>postmortem</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {inc && (
          <div style={{ marginTop: 10 }}>
            <h4 className="muted small">Run {inc.id} — {inc.status}</h4>
            <table className="table">
              <tbody>
                {inc.events?.map((ev) => (
                  <tr key={ev.id}>
                    <td className="prompt-name">{ev.kind}</td>
                    <td className="prompt-desc">{ev.data.slice(0, 90)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h3 className="card-title">Alerts ({alerts.length})</h3>
        <table className="table">
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id}>
                <td className="prompt-name">{a.name}</td>
                <td>{a.severity}</td>
                <td>{a.status}</td>
                <td className="prompt-desc">{a.message?.slice(0, 60)}</td>
                <td className="actions">
                  {a.status === 'open' && <button onClick={() => alertStatus(a.id, 'ack')}>ack</button>}
                  <button onClick={() => alertStatus(a.id, 'closed')}>close</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3 className="card-title">Chaos runs</h3>
        <p className="muted small">
          {chaos.map((c) => `${c.target}:${c.fault_type}:${c.status}`).join(' · ') || 'none'}
        </p>
        <button
          onClick={async () => {
            const r = await get<{ runs: ChaosRun[] }>('/api/aiops/chaos')
            setChaos(r.runs)
          }}
        >
          refresh
        </button>
      </section>
    </div>
  )
}