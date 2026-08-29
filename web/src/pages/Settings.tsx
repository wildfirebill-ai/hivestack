import { useCallback, useEffect, useState } from 'react'
import {
  get,
  McpConnected,
  McpServerInfo,
  ModelInfo,
  post,
  ProviderInfo,
  PromptInfo,
  SystemInfo,
} from '../api'

export default function Settings() {
  const [sys, setSys] = useState<SystemInfo | null>(null)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [modules, setModules] = useState<Record<string, boolean>>({})
  const [models, setModels] = useState<ModelInfo[]>([])
  const [prompts, setPrompts] = useState<PromptInfo[]>([])
  const [mcpServers, setMcpServers] = useState<McpServerInfo[]>([])
  const [mcpConnected, setMcpConnected] = useState<McpConnected[]>([])
  const [mcpToolsCount, setMcpToolsCount] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // models add form
  const [mName, setMName] = useState('')
  const [mProvider, setMProvider] = useState('ollama')
  const [mModelId, setMModelId] = useState('')
  // prompts add form
  const [pName, setPName] = useState('')
  const [pSystem, setPSystem] = useState('')
  // pull form
  const [pullId, setPullId] = useState('qwen2.5:7b')
  const [pullProgress, setPullProgress] = useState('')

  const reload = useCallback(async () => {
    const [s, p, m, mo, pr, mc] = await Promise.all([
      get<SystemInfo>('/api/system'),
      get<{ providers: ProviderInfo[] }>('/api/system/providers'),
      get<{ modules: Record<string, boolean> }>('/api/system/modules'),
      get<{ models: ModelInfo[] }>('/api/models'),
      get<{ prompts: PromptInfo[] }>('/api/prompts'),
      get<{ servers: McpServerInfo[] }>('/api/mcp/servers'),
    ])
    setSys(s)
    setProviders(p.providers)
    setModules(m.modules)
    setModels(mo.models)
    setPrompts(pr.prompts)
    setMcpServers(mc.servers)
    if (mc.servers.some((s) => s.connected)) {
      const cc = await get<{ connected: McpConnected[] }>('/api/mcp/connected')
      setMcpConnected(cc.connected)
      setMcpToolsCount(cc.connected.reduce((a, c) => a + c.tools.length, 0))
    } else {
      setMcpConnected([])
      setMcpToolsCount(0)
    }
  }, [])

  useEffect(() => {
    reload().catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [reload])

  const guard = async (label: string, fn: () => Promise<void>) => {
    setBusy(label)
    try {
      await fn()
      await reload()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'failed')
    } finally {
      setBusy(null)
    }
  }

  async function toggleOffline(enabled: boolean) {
    await guard('offline', async () => {
      await post('/api/system/offline', { enabled })
      setNotice(enabled ? 'offline mode ON — all outside providers locked out' : 'offline mode OFF')
    })
  }
  async function toggleProvider(name: string, enabled: boolean) {
    await guard(`provider:${name}`, () => post(`/api/system/providers/${name}`, { enabled }))
  }
  async function toggleModule(name: string, enabled: boolean) {
    await guard(`module:${name}`, () => post(`/api/system/modules/${name}`, { enabled }))
  }
  async function addModel() {
    await guard('add-model', async () => {
      await post('/api/models', { name: mName, provider: mProvider, model_id: mModelId || mName })
      setMName('')
      setMModelId('')
    })
  }
  async function toggleModel(name: string, enabled: boolean) {
    await guard(`m:${name}`, () => post(`/api/models/${name}/enabled`, { enabled }))
  }
  async function setDefault(name: string, provider: string) {
    await guard('default', () => post('/api/models/default', { provider, model: name }))
  }
  async function testModel(name: string) {
    const r = await get<{ tested: boolean; reachable?: boolean; installed?: boolean; detail?: string }>(
      `/api/models/${name}/test`,
    )
    setNotice(`test ${name}: ${r.detail ?? 'no detail'}`)
  }
  async function removeModel(name: string) {
    await guard(`rm:${name}`, async () => {
      const token = localStorage.getItem('hivestack_token')
      const res = await fetch(`/api/models/${name}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        let d = res.statusText
        try {
          d = (await res.json()).detail ?? d
        } catch { /* ignore */ }
        throw new Error(d)
      }
    })
  }
  async function addPrompt() {
    await guard('add-prompt', async () => {
      await post('/api/prompts', { name: pName, system: pSystem })
      setPName('')
      setPSystem('')
    })
  }
  async function deletePrompt(name: string) {
    await guard(`dp:${name}`, async () => {
      const token = localStorage.getItem('hivestack_token')
      const res = await fetch(`/api/prompts/${encodeURIComponent(name)}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        let d = res.statusText
        try {
          d = (await res.json()).detail ?? d
        } catch { /* ignore */ }
        throw new Error(d)
      }
    })
  }
  async function mcpConnect(name: string) {
    await guard(`mcp:${name}`, async () => {
      const r = await post<{ tools: string[] }>(`/api/mcp/servers/${name}/connect`, {})
      setNotice(`connected ${name}: ${r.tools.length} tools`)
    })
  }
  async function mcpDisconnect(name: string) {
    await guard(`mcp:${name}`, () => post(`/api/mcp/servers/${name}/disconnect`, {}))
    setNotice(`disconnected ${name}`)
  }

  async function pullModel() {
    const id = pullId.trim()
    if (!id) return
    setPullProgress('starting…')
    setBusy('pull')
    try {
      await post('/api/models/pull', { provider: 'ollama', model_id: id })
      // poll status
      for (let i = 0; i < 600; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const st = await get<{ state: string; progress?: string; error?: string }>(
          `/api/models/pull/status?provider=ollama&model_id=${encodeURIComponent(id)}`,
        )
        setPullProgress(st.progress ?? st.state)
        if (st.state === 'done' || st.state === 'error') {
          setNotice(st.state === 'done' ? `pulled ${id}` : `pull failed: ${st.error}`)
          setPullProgress('')
          break
        }
      }
      await reload()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'pull failed')
      setPullProgress('')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="page">
      <h1>Settings</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Provider gate</h3>
        <div className="row">
          <span className="muted">offline mode</span>
          <button
            disabled={busy === 'offline'}
            onClick={() => toggleOffline(!(sys?.offline_mode ?? true))}
            className={sys?.offline_mode ? 'toggle-on' : 'toggle-off'}
          >
            {sys?.offline_mode ? 'ON — local only' : 'OFF — cloud allowed'}
          </button>
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">Providers</h3>
        <table className="table">
          <thead>
            <tr>
              <th>name</th>
              <th>type</th>
              <th>key</th>
              <th>allowed</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.name}>
                <td>{p.name}</td>
                <td>{p.type}</td>
                <td>{p.has_key ? 'present' : p.type === 'local' ? 'n/a' : 'missing'}</td>
                <td>{String(p.allowed)}</td>
                <td>
                  <button disabled={busy === `provider:${p.name}`} onClick={() => toggleProvider(p.name, !p.enabled)}>
                    {p.enabled ? 'disable' : 'enable'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3 className="card-title">Models</h3>
        <table className="table">
          <thead>
            <tr>
              <th>name</th>
              <th>provider</th>
              <th>model_id</th>
              <th>ctx</th>
              <th>state</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.name}>
                <td>
                  {m.name}
                  {m.is_default ? ' ⭐' : ''}
                </td>
                <td>{m.provider}</td>
                <td>{m.model_id}</td>
                <td>{m.context}</td>
                <td>{m.enabled ? 'on' : 'off'}</td>
                <td className="actions">
                  <button disabled={busy === `m:${m.name}`} onClick={() => toggleModel(m.name, !m.enabled)}>
                    {m.enabled ? 'disable' : 'enable'}
                  </button>
                  <button disabled={busy === 'default'} onClick={() => setDefault(m.name, m.provider)}>
                    default
                  </button>
                  <button disabled={busy === `t:${m.name}`} onClick={() => testModel(m.name)}>
                    test
                  </button>
                  <button disabled={busy === `rm:${m.name}`} onClick={() => removeModel(m.name)}>
                    delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="form-row">
          <input placeholder="name" value={mName} onChange={(e) => setMName(e.target.value)} />
          <select value={mProvider} onChange={(e) => setMProvider(e.target.value)}>
            {providers.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
          <input placeholder="model_id (defaults to name)" value={mModelId} onChange={(e) => setMModelId(e.target.value)} />
          <button disabled={busy === 'add-model' || !mName} onClick={addModel}>
            register
          </button>
        </div>
        <div className="form-row pull-row">
          <input placeholder="pull model e.g. qwen2.5:7b" value={pullId} onChange={(e) => setPullId(e.target.value)} />
          <button disabled={busy === 'pull' || !pullId.trim()} onClick={pullModel}>
            {pullProgress ? 'pulling…' : 'pull (ollama)'}
          </button>
          {pullProgress && <span className="muted small">{pullProgress}</span>}
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">Prompts</h3>
        {prompts.length > 0 && (
          <table className="table">
            <tbody>
              {prompts.map((p) => (
                <tr key={p.name}>
                  <td className="prompt-name">{p.name}</td>
                  <td className="prompt-desc">{p.system.slice(0, 90)}</td>
                  <td>
                    <button disabled={busy === `dp:${p.name}`} onClick={() => deletePrompt(p.name)}>
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="form-row">
          <input placeholder="prompt name" value={pName} onChange={(e) => setPName(e.target.value)} />
          <textarea
            placeholder="system prompt text"
            value={pSystem}
            onChange={(e) => setPSystem(e.target.value)}
            rows={2}
          />
          <button disabled={busy === 'add-prompt' || !pName} onClick={addPrompt}>
            add prompt
          </button>
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">MCP servers</h3>
        <table className="table">
          <tbody>
            {(mcpServers ?? []).map((s) => (
              <tr key={s.name}>
                <td className="prompt-name">{s.name}</td>
                <td className="prompt-desc">{s.url ? s.url : `${s.command || ''} ${(s.args || []).join(' ')}`}</td>
                <td>{s.connected ? 'connected' : '—'}</td>
                <td>
                  {s.connected ? (
                    <button disabled={busy === `mcp:${s.name}`} onClick={() => mcpDisconnect(s.name)}>
                      disconnect
                    </button>
                  ) : (
                    <button disabled={busy === `mcp:${s.name}`} onClick={() => mcpConnect(s.name)}>
                      connect
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {mcpServers.length === 0 && (
              <tr>
                <td className="prompt-desc" colSpan={4}>
                  No MCP servers configured — add an entry to <code>mcp_servers</code> in config.yaml, then connect here.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {(mcpConnected.length > 0 || mcpToolsCount > 0) && (
          <p className="muted small">
            Connected: {mcpConnected.map((c) => `${c.name}(${c.tools.length})`).join(', ') || '—'}
          </p>
        )}
      </section>

      <section className="card">
        <h3 className="card-title">Feature modules</h3>
        <table className="table">
          <tbody>
            {Object.entries(modules).map(([name, enabled]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{enabled ? 'on' : 'off'}</td>
                <td>
                  <button disabled={busy === `module:${name}`} onClick={() => toggleModule(name, !enabled)}>
                    {enabled ? 'disable' : 'enable'}
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