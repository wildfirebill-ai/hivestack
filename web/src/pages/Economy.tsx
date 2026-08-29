import { useEffect, useState } from 'react'
import { get, post } from '../api'

interface Account {
  name: string
  kind: string
  balance: number
  reputation: number
}

interface Gig {
  id: string
  title: string
  reward: number
  owner: string
  status: string
  performer?: string
}

interface LedgerRow {
  id: number
  src: string
  dst: string
  amount: number
  note: string
}

export default function Economy() {
  const [enabled, setEnabled] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [gigs, setGigs] = useState<Gig[]>([])
  const [ledger, setLedger] = useState<LedgerRow[]>([])
  const [peers, setPeers] = useState<{ name: string; url: string }[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  // forms
  const [accName, setAccName] = useState('')
  const [gigTitle, setGigTitle] = useState('')
  const [gigReward, setGigReward] = useState('10')
  const [gigOwner, setGigOwner] = useState('alice')
  const [perp, setPerp] = useState('agent-1')
  const [idName, setIdName] = useState('node1')
  const [proof, setProof] = useState('')
  const [peerName, setPeerName] = useState('self')
  const [peerUrl, setPeerUrl] = useState('')
  const [pingRes, setPingRes] = useState('')
  const [tick, setTick] = useState(0)

  useEffect(() => {
    get<{ modules: Record<string, boolean> }>('/api/system/modules')
      .then((m) => setEnabled(!!m.modules.economy))
      .catch(() => undefined)
    if (!enabled) return
    Promise.all([
      get<{ accounts: Account[] }>('/api/economy/accounts'),
      get<{ gigs: Gig[] }>('/api/economy/gigs'),
      get<{ ledger: LedgerRow[] }>('/api/economy/ledger'),
      get<{ peers: { name: string; url: string }[] }>('/api/economy/peers'),
    ])
      .then(([a, g, l, p]) => {
        setAccounts(a.accounts)
        setGigs(g.gigs)
        setLedger(l.ledger)
        setPeers(p.peers)
      })
      .catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [enabled, tick])

  async function toggle(on: boolean) {
    try {
      await post('/api/system/modules/economy', { enabled: on })
      setEnabled(on)
      setTick((x) => x + 1)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'toggle failed')
    }
  }

  const act = async (path: string, body: Record<string, unknown> = {}) => {
    try {
      await post(path, body)
      setTick((x) => x + 1)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'action failed')
    }
  }

  async function prove() {
    setProof(null as unknown as string)
    try {
      const ch = await post<{ nonce: string }>('/api/economy/identity/challenge', { name: idName })
      const sg = await post<{ signature: string }>('/api/economy/identity/sign', { name: idName, nonce: ch.nonce })
      const v = await post<{ ok: boolean; reason: string }>('/api/economy/identity/verify', {
        name: idName,
        nonce: ch.nonce,
        signature: sg.signature,
      })
      setProof(`1st verify: ${v.ok} (${v.reason})`)
      const v2 = await post<{ ok: boolean; reason: string }>('/api/economy/identity/verify', {
        name: idName,
        nonce: ch.nonce,
        signature: sg.signature,
      })
      setProof((p) => `${p}\nreplay verify: ${v2.ok} (${v2.reason}) — expected false/detected`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'prove failed')
    }
  }

  async function ping(name: string) {
    try {
      const r = await post<{ response?: { ok: boolean }; error?: string }>(`/api/economy/peers/${name}/ping`, {})
      setPingRes(r.response ? `verified by ${name} (ok=${r.response.ok})` : `peer error: ${r.error}`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'ping failed')
    }
  }

  return (
    <div className="page">
      <h1>Economy <span className="muted" style={{ fontSize: 13 }}>experimental</span></h1>
      {notice && <div className="notice">{notice}</div>}
      <div className="muted small" style={{ marginBottom: 12 }}>
        module: {enabled ? 'enabled' : 'disabled (opt-in)'}{' '}
        <button onClick={() => toggle(!enabled)}>{enabled ? 'disable' : 'enable'}</button>
      </div>
      {enabled && (
        <>
          <section className="card">
            <h3 className="card-title">Accounts &amp; balances</h3>
            <table className="table">
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.name}>
                    <td className="prompt-name">{a.name} <span className="muted">{a.kind}</span></td>
                    <td>balance: {a.balance}</td>
                    <td>rep: {a.reputation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="form-row">
              <input placeholder="account name" value={accName} onChange={(e) => setAccName(e.target.value)} />
              <button onClick={() => act('/api/economy/accounts', { name: accName, kind: 'agent', seed: 0 })}>create</button>
            </div>
          </section>

          <section className="card">
            <h3 className="card-title">Gig marketplace (escrow)</h3>
            <form
              className="form-row"
              onSubmit={(e) => {
                e.preventDefault()
                act('/api/economy/gigs', { title: gigTitle, reward: Number(gigReward), owner: gigOwner })
                setGigTitle('')
              }}
            >
              <input placeholder="title" value={gigTitle} onChange={(e) => setGigTitle(e.target.value)} style={{ flex: 1 }} />
              <input placeholder="reward" value={gigReward} onChange={(e) => setGigReward(e.target.value)} style={{ width: 80 }} />
              <input placeholder="owner" value={gigOwner} onChange={(e) => setGigOwner(e.target.value)} style={{ width: 110 }} />
              <button type="submit">post gig</button>
            </form>
            <table className="table">
              <tbody>
                {gigs.map((g) => (
                  <tr key={g.id}>
                    <td className="prompt-name">{g.title}</td>
                    <td>{g.reward} → {g.owner}</td>
                    <td>{g.status}{g.performer ? ` by ${g.performer}` : ''}</td>
                    <td className="actions">
                      {g.status === 'open' && <button onClick={() => act(`/api/economy/gigs/${g.id}/claim`, { performer: perp })}>claim</button>}
                      {g.status === 'claimed' && <button onClick={() => act(`/api/economy/gigs/${g.id}/complete`)}>complete</button>}
                      {(g.status === 'completed' || g.status === 'claimed') && (
                        <button onClick={() => act(`/api/economy/gigs/${g.id}/settle`, { approver: g.owner })}>settle</button>
                      )}
                    </td>
                  </tr>
                ))}
                {gigs.length === 0 && <tr><td className="prompt-desc">no gigs</td></tr>}
              </tbody>
            </table>
          </section>

          <section className="card">
            <h3 className="card-title">Ledger</h3>
            <div className="event-list">
              {ledger.map((l) => (
                <div key={l.id} className="event-row">
                  <span className="prompt-name">{l.src} → {l.dst}</span>
                  <span>+{l.amount}</span>
                  <span className="prompt-desc">{l.note}</span>
                </div>
              ))}
              {ledger.length === 0 && <span className="muted small">empty</span>}
            </div>
          </section>

          <section className="card">
            <h3 className="card-title">Identity (signature challenge)</h3>
            <div className="form-row">
              <input placeholder="identity name" value={idName} onChange={(e) => setIdName(e.target.value)} />
              <button onClick={() => act('/api/economy/identity/issue', { name: idName })}>issue</button>
              <button onClick={prove}>challenge → sign → verify (incl. replay)</button>
            </div>
            {proof && <div className="bubble-text" style={{ marginTop: 8 }}>{proof}</div>}
          </section>

          <section className="card">
            <h3 className="card-title">Federation (signed pings)</h3>
            <div className="form-row">
              <input placeholder="peer name" value={peerName} onChange={(e) => setPeerName(e.target.value)} />
              <input placeholder="peer url" value={peerUrl} onChange={(e) => setPeerUrl(e.target.value)} style={{ flex: 1 }} />
              <button onClick={() => act('/api/economy/peers', { name: peerName, url: peerUrl })}>add peer</button>
            </div>
            <p className="muted small">
              {peers.map((p) => `${p.name} (${p.url})`).join(' · ') || 'no peers'}
            </p>
            {peers.map((p) => (
              <button key={p.name} style={{ marginRight: 6 }} onClick={() => ping(p.name)}>
                ping {p.name}
              </button>
            ))}
            {pingRes && <div className="muted small" style={{ marginTop: 6 }}>{pingRes}</div>}
          </section>
        </>
      )}
    </div>
  )
}