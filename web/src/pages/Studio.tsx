import { FormEvent, useCallback, useEffect, useState } from 'react'
import { get, post } from '../api'

interface DocRow {
  id: string
  name: string
  format: string
  created_at?: string
}

interface PublishJob {
  id: string
  title: string
  status: string
  body?: string
}

export default function Studio() {
  const [docs, setDocs] = useState<DocRow[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<string[] | null>(null)
  // word form
  const [wTitle, setWTitle] = useState('')
  const [wBody, setWBody] = useState('') // sections: lines => bullets
  // sheet form
  const [sSheet, setSSheet] = useState('')
  const [sRows, setSRows] = useState('')
  // analytics
  const [aContent, setAContent] = useState('')
  const [anSeries, setAnSeries] = useState('')
  // publish
  const [jobs, setJobs] = useState<PublishJob[]>([])
  const [pjTitle, setPjTitle] = useState('')
  const [pjBody, setPjBody] = useState('')

  const refresh = useCallback(async () => {
    const [d, pj] = await Promise.all([
      get<{ documents: DocRow[] }>('/api/docs'),
      get<{ jobs: PublishJob[] }>('/api/publish/jobs'),
    ])
    setDocs(d.documents)
    setJobs(pj.jobs)
  }, [])

  useEffect(() => {
    refresh().catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [refresh])

  async function buildWord(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    const lines = wBody.split('\n').map((l) => l.trim()).filter(Boolean)
    try {
      const r = await post<{ id: string; audit: { pass: boolean } }>('/api/docs/word', {
        title: wTitle,
        sections: [{ heading: 'Body', body: lines }],
      })
      setNotice(`word doc ${r.id} — audit pass=${r.audit.pass}`)
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'build failed')
    } finally {
      setBusy(false)
    }
  }

  async function buildSheet(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    const rows = sRows
      .split('\n')
      .map((l) => l.split(',').map((c) => c.trim()).filter((c) => c !== ''))
      .filter((r) => r.length)
    try {
      const r = await post<{ id: string }>('/api/docs/spreadsheet', { sheets: [{ name: sSheet || 'Sheet1', rows }] })
      setNotice(`sheet doc ${r.id}`)
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'build failed')
    } finally {
      setBusy(false)
    }
  }

  async function previewDoc(id: string) {
    try {
      const r = await get<{ lines: string[] }>(`/api/docs/${id}/preview`)
      setPreview(r.lines)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'preview failed')
    }
  }

  async function analyze() {
    try {
      const r = await post<{ rows: number; columns: number; col_stats: any[] }>('/api/data/analyze', {
        content: aContent,
        name: 'paste',
      })
      setNotice(
        `analyzed: ${r.rows} rows x ${r.columns} cols — ` +
          (r.col_stats || []).slice(0, 3).map((c) => `${c.name}:${c.type}`).join(', '),
      )
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'analyze failed')
    }
  }

  async function anomalies() {
    try {
      const points = anSeries.split(',').map((x) => Number(x.trim())).filter((n) => !isNaN(n))
      const r = await post<{ cpu?: { anomalies: number[]; method: string } }>('/api/data/anomalies', {
        series: [{ name: 'cpu', points }],
        method: 'hybrid',
      })
      setNotice(`anomalies at indices ${(r.cpu?.anomalies ?? []).join(',') || 'none'} (${r.cpu?.method})`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'anomaly failed')
    }
  }

  async function publish(e: FormEvent) {
    e.preventDefault()
    try {
      await post('/api/publish/jobs', { title: pjTitle, body: pjBody, targets: ['outbox'] })
      setPjTitle('')
      setPjBody('')
      await refresh()
      setNotice('publish job queued — approve to send')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'publish failed')
    }
  }

  async function jobAct(id: string, endpoint: string) {
    try {
      if (endpoint === 'approve') {
        const r = await post<{ job: PublishJob }>(`/api/publish/jobs/${id}/approve`, { approve: true })
        setNotice(`job ${id} → ${r.job.status}`)
        await refresh()
      } else {
        const r = await post<{ status: string; path: string }>(`/api/publish/jobs/${id}/execute`, {})
        setNotice(`published → ${r.path}`)
        await refresh()
      }
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'job action failed')
    }
  }

  return (
    <div className="page">
      <h1>Studio</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Word report</h3>
        <form className="ag-form" onSubmit={buildWord}>
          <input placeholder="title" value={wTitle} onChange={(e) => setWTitle(e.target.value)} />
          <textarea rows={4} value={wBody} onChange={(e) => setWBody(e.target.value)} placeholder="one bullet per line" />
          <button disabled={busy || !wTitle} type="submit">
            build .docx
          </button>
        </form>
      </section>

      <section className="card">
        <h3 className="card-title">Spreadsheet (formulas work when opened)</h3>
        <form className="ag-form" onSubmit={buildSheet}>
          <input placeholder="sheet name" value={sSheet} onChange={(e) => setSSheet(e.target.value)} />
          <textarea rows={4} value={sRows} onChange={(e) => setSRows(e.target.value)} placeholder="rev,cost&#10;100,40&#10;=SUM(A2:A3),=SUM(B2:B3)" />
          <button disabled={busy || !sRows} type="submit">
            build .xlsx
          </button>
        </form>
      </section>

      <section className="card">
        <h3 className="card-title">Data &amp; analytics</h3>
        <table className="table">
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td className="prompt-name">{d.name}</td>
                <td>{d.format}</td>
                <td className="actions">
                  <button onClick={() => previewDoc(d.id)}>preview</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {preview && (
          <details open>
            <summary className="muted small">preview ({preview.length} lines)</summary>
            <pre className="bubble-text">{preview.slice(0, 40).join('\n')}</pre>
          </details>
        )}
        <div className="form-row">
          <textarea rows={3} placeholder="paste CSV or JSON to profile" value={aContent} onChange={(e) => setAContent(e.target.value)} style={{ flex: 2 }} />
          <button onClick={analyze}>analyze</button>
        </div>
        <div className="form-row">
          <input placeholder="comma-separated series e.g. 1,2,1,2,50" value={anSeries} onChange={(e) => setAnSeries(e.target.value)} style={{ flex: 1 }} />
          <button onClick={anomalies}>anomalies</button>
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">Publishing (approval-gated outbox)</h3>
        <form className="form-row" onSubmit={publish}>
          <input placeholder="title" value={pjTitle} onChange={(e) => setPjTitle(e.target.value)} style={{ flex: 1 }} />
          <input placeholder="body" value={pjBody} onChange={(e) => setPjBody(e.target.value)} style={{ flex: 2 }} />
          <button type="submit">queue</button>
        </form>
        <table className="table">
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td className="prompt-name">{j.title}</td>
                <td>{j.status}</td>
                <td className="actions">
                  {j.status === 'pending_approval' && (
                    <button onClick={() => jobAct(j.id, 'approve')}>approve</button>
                  )}
                  {j.status === 'approved' && (
                    <button onClick={() => jobAct(j.id, 'execute')}>execute</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}