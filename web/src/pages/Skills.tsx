import { FormEvent, useCallback, useEffect, useState } from 'react'
import { get, post } from '../api'

interface SkillInfo {
  name: string
  version: string
  description: string
  tags: string
  source: string
  status: string
}

interface SourceRow {
  id: number
  kind: string
  ref: string
  recorded_sha?: string
  state: string
  detail: string
}

export default function Skills() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [sources, setSources] = useState<SourceRow[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // generate form
  const [gDesc, setGDesc] = useState('')
  const [gName, setGName] = useState('')
  const [gLl, setGLl] = useState(true)
  // install form
  const [iKind, setIKind] = useState('local')
  const [iRef, setIRef] = useState('')
  // export preview
  const [exported, setExported] = useState('')

  const refresh = useCallback(async () => {
    const [s, src] = await Promise.all([
      get<{ skills: SkillInfo[] }>('/api/skills'),
      get<{ sources: SourceRow[] }>('/api/skills/sources/list'),
    ])
    setSkills(s.skills)
    setSources(src.sources)
  }, [])

  useEffect(() => {
    refresh().catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [refresh])

  async function generate(e: FormEvent) {
    e.preventDefault()
    if (!gDesc.trim()) return
    setBusy(true)
    try {
      const r = await post<{ skill: SkillInfo }>('/api/skills/generate', {
        description: gDesc,
        name: gName || null,
        use_llm: gLl,
      })
      setNotice(`generated skill '${r.skill.name}'`)
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'generate failed')
    } finally {
      setBusy(false)
    }
  }

  async function install(e: FormEvent) {
    e.preventDefault()
    if (!iRef.trim()) return
    setBusy(true)
    try {
      const r = await post<{ skills: { name: string }[] }>('/api/skills/install', { kind: iKind, ref: iRef })
      setNotice(`installed ${r.skills.length} skill(s)`)
      setIRef('')
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'install failed')
    } finally {
      setBusy(false)
    }
  }

  async function validateSkill(name: string) {
    try {
      const r = await post<{ score: number; pass: boolean; checks: { name: string; pass: boolean }[] }>(
        `/api/skills/${name}/validate`,
        {},
      )
      setNotice(`${name}: ${Math.round(r.score * 100)}% pass → ${r.pass}`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'validate failed')
    }
  }

  async function evalSkill(name: string) {
    try {
      const r = await post<{ eval_run: string; status: string; steps: number }>(`/api/skills/${name}/eval`, { probe: '' })
      setNotice(`eval ${name}: run ${r.eval_run} → ${r.status} (${r.steps} steps)`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'eval failed')
    }
  }

  async function exportSkill(name: string) {
    try {
      const r = await get<{ skill_md: string }>(`/api/skills/${name}/export`)
      setExported(r.skill_md)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'export failed')
    }
  }

  function del(name: string) {
    const token = localStorage.getItem('hivestack_token')
    return fetch(`/api/skills/${name}`, {
      method: 'DELETE',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then(() => refresh())
  }

  return (
    <div className="page">
      <h1>Skills</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Generate a skill</h3>
        <form className="ag-form" onSubmit={generate}>
          <input placeholder="name (optional)" value={gName} onChange={(e) => setGName(e.target.value)} />
          <textarea
            rows={3}
            placeholder="Describe the skill in plain language, e.g. 'Summarize a set of markdown notes into one cited report'"
            value={gDesc}
            onChange={(e) => setGDesc(e.target.value)}
          />
          <div className="form-row">
            <label className="muted small" style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={gLl} onChange={(e) => setGLl(e.target.checked)} style={{ width: 'auto' }} />
              author with LLM (falls back to template offline)
            </label>
            <button disabled={busy || !gDesc.trim()} type="submit" style={{ marginLeft: 'auto' }}>
              Generate
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h3 className="card-title">Install from source</h3>
        <form className="form-row" onSubmit={install}>
          <select value={iKind} onChange={(e) => setIKind(e.target.value)}>
            <option value="local">local path</option>
            <option value="git">git url (needs offline off)</option>
          </select>
          <input placeholder={iKind === 'local' ? '/path/to/SKILL.md-or-dir' : 'https://github.com/org/repo'} value={iRef} onChange={(e) => setIRef(e.target.value)} style={{ flex: 1 }} />
          <button disabled={busy} type="submit">
            install
          </button>
        </form>
        {sources.length > 0 && (
          <p className="muted small">
            sources:{' '}
            {sources.map((s) => `${s.kind}:${s.state}`).join(' · ')}
          </p>
        )}
      </section>

      <section className="card">
        <h3 className="card-title">Registry ({skills.length})</h3>
        <table className="table">
          <thead>
            <tr>
              <th>skill</th>
              <th>source</th>
              <th>status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {skills.map((s) => (
              <tr key={s.name}>
                <td>
                  <div className="prompt-name">{s.name}</div>
                  <div className="prompt-desc">{s.description.slice(0, 80)}</div>
                </td>
                <td>{s.source}</td>
                <td>{s.status}</td>
                <td className="actions">
                  <button onClick={() => validateSkill(s.name)}>validate</button>
                  <button onClick={() => evalSkill(s.name)}>eval</button>
                  <button onClick={() => exportSkill(s.name)}>export</button>
                  <button onClick={() => del(s.name)}>delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {exported && (
        <section className="card">
          <h3 className="card-title">Exported SKILL.md</h3>
          <pre className="bubble-text">{exported}</pre>
          <button onClick={() => navigator.clipboard?.writeText(exported)} style={{ marginTop: 8 }}>
            copy
          </button>
          <button onClick={() => setExported('')} style={{ marginLeft: 8 }}>
            close
          </button>
        </section>
      )}
    </div>
  )
}