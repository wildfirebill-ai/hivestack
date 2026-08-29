import { FormEvent, useCallback, useEffect, useState } from 'react'
import { get, post } from '../api'

interface NoteInfo {
  id: number
  scope: string
  title: string
  kind: string
  archived: number
  created_at?: string
}

interface SearchResult {
  chunk_id: number
  note_id: number
  title: string
  scope: string
  kind: string
  content: string
  snippet: string
  score: number
}

interface Entity {
  id: number
  name: string
  kind: string
  scope: string
}

interface LinkRow {
  id: number
  source: string
  target: string
  relation: string
  valid_from?: string
  valid_to?: string
}

export default function Memory() {
  const [emb, setEmb] = useState(false)
  const [notes, setNotes] = useState<NoteInfo[]>([])
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [q, setQ] = useState('')
  const [scope, setScope] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // forms
  const [nScope, setNScope] = useState('global')
  const [nTitle, setNTitle] = useState('')
  const [nContent, setNContent] = useState('')
  const [iType, setIType] = useState('text')
  const [iTitle, setITitle] = useState('')
  const [iContent, setIContent] = useState('')
  const [iScope, setIScope] = useState('global')
  // kb
  const [entities, setEntities] = useState<Entity[]>([])
  const [links, setLinks] = useState<LinkRow[]>([])
  const [eName, setEName] = useState('')
  const [lSrc, setLSrc] = useState('')
  const [lRel, setLRel] = useState('')
  const [lTgt, setLTgt] = useState('')

  const refresh = useCallback(async () => {
    const [o, n, kb] = await Promise.all([
      get<{ embeddings: boolean }>('/api/memory'),
      get<{ notes: NoteInfo[] }>('/api/memory/notes'),
      get<{ entities: Entity[]; links: LinkRow[] }>('/api/memory/kb'),
    ])
    setEmb(o.embeddings)
    setNotes(n.notes)
    setEntities(kb.entities)
    setLinks(kb.links)
  }, [])

  useEffect(() => {
    refresh().catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [refresh])

  async function addNote(e: FormEvent) {
    e.preventDefault()
    if (!nTitle || !nContent) return
    try {
      await post('/api/memory/notes', { scope: nScope, title: nTitle, content: nContent, kind: 'note' })
      setNTitle('')
      setNContent('')
      await refresh()
      setNotice('note saved')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'save failed')
    }
  }

  async function search(e?: FormEvent) {
    e?.preventDefault()
    if (!q.trim()) return
    try {
      const r = await post<{ results: SearchResult[] }>('/api/memory/search', { query: q, scope: scope || null, k: 8 })
      setResults(r.results)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'search failed')
    }
  }

  async function ingest(e: FormEvent) {
    e.preventDefault()
    if (!iTitle) return
    try {
      const body: Record<string, string> = { source_type: iType, title: iTitle, scope: iScope }
      if (iType === 'url') body.url = iContent
      else body.content = iContent
      const r = await post<{ note_id: number; chars: number }>('/api/memory/ingest', body)
      setNotice(`ingested ${r.chars} chars → note ${r.note_id}`)
      setIContent('')
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'ingest failed')
    }
  }

  async function compact(scopeName: string) {
    setBusy(true)
    try {
      const r = await post<{ merged: number }>('/api/memory/compact', { scope: scopeName || 'global' })
      setNotice(`compaction built ${r.merged} summary/s`)
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'compact failed')
    } finally {
      setBusy(false)
    }
  }

  function del(path: string) {
    const token = localStorage.getItem('hivestack_token')
    return fetch(path, { method: 'DELETE', headers: token ? { Authorization: `Bearer ${token}` } : {} })
  }

  async function archiveOrUn(noteId: number, archived: boolean) {
    await post(`/api/memory/archive/${noteId}?archived=${archived}`, {})
    await refresh()
  }

  async function addEntity() {
    if (!eName.trim()) return
    await post('/api/memory/entities', { name: eName, scope: 'global' })
    setEName('')
    await refresh()
  }

  async function addLink() {
    if (!lSrc.trim() || !lRel.trim() || !lTgt.trim()) return
    await post('/api/memory/links', { source: lSrc, relation: lRel, target: lTgt, scope: 'global' })
    setLSrc('')
    setLTgt('')
    await refresh()
  }

  return (
    <div className="page">
      <h1>Memory &amp; Knowledge</h1>
      {notice && <div className="notice">{notice}</div>}
      <div className="muted small" style={{ marginBottom: 12 }}>
        embeddings: {emb ? 'active (all-MiniLM-L6-v2, local CPU)' : 'unavailable — keyword search only'}
      </div>

      <section className="card">
        <h3 className="card-title">Search</h3>
        <form className="form-row" onSubmit={search}>
          <input placeholder="semantic + keyword query" value={q} onChange={(e) => setQ(e.target.value)} />
          <input placeholder="scope (optional)" value={scope} onChange={(e) => setScope(e.target.value)} style={{ flex: '0 0 160px' }} />
          <button type="submit">search</button>
        </form>
        {results && (
          <table className="table">
            <tbody>
              {results.map((r) => (
                <tr key={r.chunk_id}>
                  <td className="prompt-desccell">
                    <div className="prompt-name">{r.title}</div>
                    <div className="prompt-desc">{r.snippet}…</div>
                    <div className="muted small">
                      score {r.score} · {r.kind} · scope {r.scope}
                    </div>
                  </td>
                </tr>
              ))}
              {results.length === 0 && (
                <tr>
                  <td className="prompt-desc">no matches</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3 className="card-title">Add note (verbatim)</h3>
        <form className="ag-form" onSubmit={addNote}>
          <div className="form-row">
            <input placeholder="scope (global)" value={nScope} onChange={(e) => setNScope(e.target.value)} />
            <input placeholder="title" value={nTitle} onChange={(e) => setNTitle(e.target.value)} />
          </div>
          <textarea rows={3} value={nContent} onChange={(e) => setNContent(e.target.value)} placeholder="verbatim content…" />
          <button type="submit">save note</button>
        </form>
      </section>

      <section className="card">
        <h3 className="card-title">Ingest (RAG documents)</h3>
        <form className="ag-form" onSubmit={ingest}>
          <div className="form-row">
            <select value={iType} onChange={(e) => setIType(e.target.value)}>
              <option value="text">text</option>
              <option value="csv">csv</option>
              <option value="url">url (needs offline off)</option>
            </select>
            <input placeholder="title" value={iTitle} onChange={(e) => setITitle(e.target.value)} style={{ flex: 1 }} />
            <input placeholder="scope" value={iScope} onChange={(e) => setIScope(e.target.value)} style={{ flex: '0 0 130px' }} />
          </div>
          <textarea rows={4} value={iContent} onChange={(e) => setIContent(e.target.value)} placeholder={iType === 'url' ? 'https://…' : 'paste content (txt/csv)'} />
          <button type="submit">ingest &amp; chunk</button>
        </form>
      </section>

      <section className="card">
        <h3 className="card-title">Notes ({notes.length})</h3>
        <table className="table">
          <tbody>
            {notes.map((n) => (
              <tr key={n.id}>
                <td className="prompt-name">{n.title}</td>
                <td className="prompt-desc">
                  {n.kind} · {n.scope}
                </td>
                <td className="actions">
                  <button onClick={() => archiveOrUn(n.id, n.archived === 0)}>
                    {n.archived ? 'un-archive' : 'archive'}
                  </button>
                  <button onClick={() => del(`/api/memory/notes/${n.id}`).then(refresh)}>delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button disabled={busy} onClick={() => compact('')} style={{ marginTop: 10 }}>
          {busy ? 'compacting…' : 'compact (merge similar → summaries, archive originals)'}
        </button>
      </section>

      <section className="card">
        <h3 className="card-title">Knowledge graph</h3>
        <div className="form-row">
          <input placeholder="entity name" value={eName} onChange={(e) => setEName(e.target.value)} />
          <button onClick={addEntity}>add entity</button>
        </div>
        <div className="form-row">
          <input placeholder="source" value={lSrc} onChange={(e) => setLSrc(e.target.value)} />
          <input placeholder="relation" value={lRel} onChange={(e) => setLRel(e.target.value)} style={{ flex: '0 0 130px' }} />
          <input placeholder="target" value={lTgt} onChange={(e) => setLTgt(e.target.value)} />
          <button onClick={addLink}>add link</button>
        </div>
        <p className="muted small">entities: {entities.length} · active links: {links.length}</p>
        <table className="table">
          <tbody>
            {links.map((l) => (
              <tr key={l.id}>
                <td className="prompt-name">
                  {l.source} <span className="muted">—{l.relation}→</span> {l.target}
                </td>
                <td className="actions">
                  <button onClick={() => post(`/api/memory/links/${l.id}/invalidate`, {}).then(refresh)}>
                    invalidate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}