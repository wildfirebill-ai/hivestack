import { useEffect, useState } from 'react'
import { get, GpuInfo, SystemInfo, UsageResponse } from '../api'

export default function Dashboard() {
  const [sys, setSys] = useState<SystemInfo | null>(null)
  const [gpu, setGpu] = useState<GpuInfo | null>(null)
  const [mods, setMods] = useState<Record<string, boolean> | null>(null)
  const [providers, setProviders] = useState<number>(0)
  const [usage, setUsage] = useState<UsageResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      get<SystemInfo>('/api/system'),
      get<GpuInfo>('/api/system/gpu'),
      get<{ modules: Record<string, boolean> }>('/api/system/modules'),
      get<{ providers: unknown[] }>('/api/system/providers'),
      get<UsageResponse>('/api/system/usage'),
    ])
      .then(([s, g, m, p, u]) => {
        setSys(s)
        setGpu(g)
        setMods(m.modules)
        setProviders(p.providers.length)
        setUsage(u)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'failed to load'))
  }, [])

  const gpuDev = gpu?.gpus?.[0]
  const gpuDetail = gpu?.present
    ? `${gpuDev?.name ?? 'GPU'} · ${Math.round((gpuDev?.memory_total_mib ?? 0) / 1024)} GiB · CC ${gpuDev?.compute_capability ?? '?'} · driver ${gpuDev?.driver_version ?? '?'}`
    : gpu?.reason ?? 'unknown'
  const enabledMods = mods ? Object.entries(mods).filter(([, v]) => v).map(([k]) => k) : []

  return (
    <div className="page">
      <h1>Dashboard</h1>
      {error && <div className="error">{error}</div>}
      <div className="cards">
        <Card title="Core">
          <Row label="name" value={sys?.name ?? '…'} />
          <Row label="version" value={sys?.version ?? '…'} />
          <Row label="offline mode" value={sys ? (sys.offline_mode ? 'on (local-only)' : 'off') : '…'} />
        </Card>
        <Card title={`GPU${gpu?.present ? '' : ' (CPU only)'}`}>
          <Row label="state" value={gpu?.present ? 'detected' : 'not present'} />
          <div className="row">
            <span className="muted">detail</span>
            <span>{gpuDetail}</span>
          </div>
          <Row label="ollama cc5+ ok" value={gpu?.ollama_supported === undefined ? '—' : String(gpu.ollama_supported)} />
        </Card>
        <Card title="Modules">
          <Row label="enabled" value={enabledMods.length ? enabledMods.join(', ') : 'none yet'} />
          <Row label="provider slots" value={String(providers)} />
        </Card>
        <Card title="Usage">
          <Row label="calls" value={String(usage?.totals.calls ?? 0)} />
          <Row label="tokens in / out" value={`${usage?.totals.in_tok ?? 0} / ${usage?.totals.out_tok ?? 0}`} />
          <Row
            label="top provider"
            value={usage?.breakdown[0] ? `${usage.breakdown[0].provider}:${usage.breakdown[0].calls}` : '—'}
          />
        </Card>
      </div>
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h3 className="card-title">{title}</h3>
      <div className="stack">{children}</div>
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