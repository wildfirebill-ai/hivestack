import { FormEvent, useCallback, useEffect, useState } from 'react'
import { get, post } from '../api'

interface Channel {
  name: string
  platform: string
  enabled: boolean
  token_present?: boolean
  offline_blocked?: boolean
  trigger_workflow?: string
}

interface MailMsg {
  id: number
  channel: string
  direction: string
  from_id: string
  text: string
  reply: string
  created_at?: string
}

interface SecretRow {
  name: string
  updated_at?: string
}

export default function Comms() {
  const [channels, setChannels] = useState<Channel[]>([])
  const [mailbox, setMailbox] = useState<MailMsg[]>([])
  const [secrets, setSecrets] = useState<SecretRow[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  // webhook tester
  const [msg, setMsg] = useState('')
  const [reply, setReply] = useState('')
  // vault
  const [sName, setSName] = useState('')
  const [sVal, setSVal] = useState('')
  const [sGet, setSGet] = useState('')
  // voice
  const [vTrans, setVTrans] = useState('')
  const [vOut, setVOut] = useState('')

  const refresh = useCallback(async () => {
    const [c, mb, sec] = await Promise.all([
      get<{ channels: Channel[] }>('/api/channels'),
      get<{ messages: MailMsg[] }>('/api/channels/messages'),
      get<{ secrets: SecretRow[] }>('/api/vault'),
    ])
    setChannels(c.channels)
    setMailbox(mb.messages)
    setSecrets(sec.secrets)
  }, [])

  useEffect(() => {
    refresh().catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [refresh])

  async function sendWebhook(e: FormEvent) {
    e.preventDefault()
    if (!msg.trim()) return
    try {
      const r = await post<{ reply: string; source: string }>('/api/channels/webhook/ingest', {
        text: msg,
        from_id: 'ui',
      })
      setReply(`[${r.source}] ${r.reply}`)
      await refresh()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'send failed')
    }
  }

  async function vaultSet() {
    if (!sName || !sVal) return
    try {
      await post('/api/vault', { name: sName, value: sVal })
      setSVal('')
      await refresh()
      setNotice(`secret '${sName}' stored`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'vault write failed')
    }
  }

  async function vaultRead() {
    if (!sGet) return
    try {
      const r = await post<{ value: string }>('/api/vault/get', { name: sGet })
      setNotice(`${sGet} = ${r.value}`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'vault read failed')
    }
  }

  async function runVoice() {
    if (!vTrans.trim()) return
    try {
      const r = await post<{ activated: boolean; transcript: string; reply: string; source: string }>(
        '/api/voice/activate',
        { transcript: vTrans },
      )
      setVOut(r.activated ? `[${r.source}] ${r.reply}` : `(no wake word) ${r.transcript}`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'voice failed')
    }
  }

  function delSecret(name: string) {
    const token = localStorage.getItem('hivestack_token')
    return fetch(`/api/vault/${name}`, { method: 'DELETE', headers: token ? { Authorization: `Bearer ${token}` } : {} }).then(() => refresh())
  }

  return (
    <div className="page">
      <h1>Comms</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Channels</h3>
        <table className="table">
          <tbody>
            {channels.map((c) => (
              <tr key={c.name}>
                <td className="prompt-name">{c.name}</td>
                <td>{c.platform}</td>
                <td>{c.enabled ? 'on' : 'off'}</td>
                <td className="prompt-desc">
                  {c.offline_blocked ? 'offline-blocked' : c.token_present ? 'token present' : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form className="form-row" onSubmit={sendWebhook}>
          <input placeholder="message to the off-line agent (webhook)" value={msg} onChange={(e) => setMsg(e.target.value)} style={{ flex: 1 }} />
          <button type="submit">send</button>
        </form>
        {reply && <div className="bubble-text" style={{ marginTop: 8 }}>{reply}</div>}
      </section>

      <section className="card">
        <h3 className="card-title">Mailbox (audit log)</h3>
        <table className="table">
          <tbody>
            {mailbox.slice(0, 15).map((m) => (
              <tr key={m.id}>
                <td className="prompt-name">{m.channel}</td>
                <td>{m.direction}</td>
                <td className="prompt-desc">{m.text?.slice(0, 40)}</td>
                <td className="prompt-desc">{m.reply?.slice(0, 40)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3 className="card-title">Encrypted vault</h3>
        <div className="form-row">
          <input placeholder="secret name" value={sName} onChange={(e) => setSName(e.target.value)} />
          <input placeholder="secret value" value={sVal} onChange={(e) => setSVal(e.target.value)} style={{ flex: 1 }} />
          <button onClick={vaultSet}>store</button>
        </div>
        <div className="form-row">
          <input placeholder="read name" value={sGet} onChange={(e) => setSGet(e.target.value)} style={{ flex: 1 }} />
          <button onClick={vaultRead}>read</button>
        </div>
        <p className="muted small">
          {secrets.map((s) => `${s.name}`).join(' · ') || 'no secrets'}
        </p>
        {secrets.map((s) => (
          <span key={s.name}>
            <button className="muted small" style={{ marginRight: 6 }} onClick={() => delSecret(s.name)}>
              del {s.name}
            </button>
          </span>
        ))}
      </section>

      <section className="card">
        <h3 className="card-title">Voice (wake-word → agent)</h3>
        <form className="form-row" onSubmit={(e) => { e.preventDefault(); runVoice() }}>
          <input placeholder="e.g. hey hivestack what gpu runs here?" value={vTrans} onChange={(e) => setVTrans(e.target.value)} style={{ flex: 1 }} />
          <button type="submit">activate</button>
        </form>
        {vOut && <div className="bubble-text" style={{ marginTop: 8 }}>{vOut}</div>}
        <p className="muted small">Real STT/TTS need optional backends (faster-whisper / piper) — the text path verifies the whole loop offline.</p>
      </section>
    </div>
  )
}