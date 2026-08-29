const TOKEN_KEY = 'hivestack_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    ...((init.headers as Record<string, string>) || {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(path, { ...init, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status)
  }
  return res.json() as Promise<T>
}

export const get = <T,>(path: string) => request<T>(path)
export const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })

// ---- shared types ---------------------------------------------------------
export interface SystemInfo {
  name: string
  version: string
  offline_mode: boolean
}

export interface ProviderInfo {
  name: string
  type: string
  enabled: boolean
  base_url?: string
  key_env?: string
  allowed?: boolean
  has_key?: boolean
}

export interface GpuDevice {
  name: string
  memory_total_mib: number
  memory_used_mib: number
  driver_version: string
  compute_capability: string
}

export interface GpuInfo {
  present: boolean
  reason?: string
  gpus?: GpuDevice[]
  ollama_supported?: boolean
  vllm_supported?: boolean
}

export interface ChatReply {
  reply: string
  model: string | null
  provider: string | null
  usage: Usage
}

export interface Usage {
  input_tokens: number
  output_tokens: number
}

export interface ModelInfo {
  name: string
  provider: string
  model_id: string
  family?: string
  context?: number
  enabled: boolean
  notes?: string
  provider_allowed?: boolean
  is_default?: boolean
}

export interface ProvidersResponse {
  offline_mode: boolean
  providers: ProviderInfo[]
}

export interface ModelsResponse {
  models: ModelInfo[]
  default_provider: string
  default_model: string
  providers: ProviderInfo[]
}

export interface PromptInfo {
  name: string
  system: string
}

export interface UsageRow {
  provider: string
  model: string
  calls: number
  in_tok: number
  out_tok: number
}

export interface UsageResponse {
  breakdown: UsageRow[]
  totals: { calls: number; in_tok: number; out_tok: number }
}

export interface McpServerInfo {
  name: string
  url?: string
  command?: string
  args?: string[]
  connected?: boolean
}

export interface McpConnected {
  name: string
  tools: string[]
}

export async function streamChat(
  body: {
    message: string
    provider?: string | null
    model?: string | null
    prompt?: string | null
  },
  handlers: {
    onDelta: (t: string) => void
    onDone: (info: { model?: string | null; provider?: string | null; usage?: Usage }) => void
    onError: (m: string) => void
  },
): Promise<void> {
  const token = getToken()
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    handlers.onError(res.statusText)
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let doneInfo: { model?: string | null; provider?: string | null; usage?: Usage } = {}
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n')
    buf = parts.pop() ?? ''
    for (const line of parts) {
      const t = line.trim()
      if (!t.startsWith('data:')) continue
      const payload = t.slice(5).trim()
      if (!payload) continue
      try {
        const evt = JSON.parse(payload)
        if (evt.error) handlers.onError(evt.error)
        else if (evt.delta !== undefined) handlers.onDelta(evt.delta)
        else if (evt.done) doneInfo = { model: evt.model, provider: evt.provider, usage: evt.usage }
      } catch {
        /* ignore malformed frames */
      }
    }
  }
  handlers.onDone(doneInfo)
}