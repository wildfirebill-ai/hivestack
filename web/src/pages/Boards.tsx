import { FormEvent, useCallback, useEffect, useState } from 'react'
import { get, post } from '../api'

interface BoardInfo {
  id: string
  name: string
  cards: number
}

interface Card {
  id: string
  title: string
  body?: string
  run_id?: string
}

interface Column {
  id: string
  name: string
  cards: Card[]
}

interface BoardDetail extends BoardInfo {
  columns: Column[]
}

export default function Boards() {
  const [boards, setBoards] = useState<BoardInfo[]>([])
  const [current, setCurrent] = useState<BoardDetail | null>(null)
  const [bid, setBid] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [cardTitle, setCardTitle] = useState('')

  const refreshBoards = useCallback(async () => {
    const r = await get<{ boards: BoardInfo[] }>('/api/boards')
    setBoards(r.boards)
    if (r.boards.length && !r.boards.some((b) => b.id === bid)) {
      setBid(r.boards[0].id)
    }
  }, [bid])

  useEffect(() => {
    refreshBoards().catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
  }, [refreshBoards])

  useEffect(() => {
    if (bid) {
      get<BoardDetail>(`/api/boards/${bid}`)
        .then(setCurrent)
        .catch((err) => setNotice(err instanceof Error ? err.message : 'load failed'))
    }
  }, [bid])

  function del(path: string) {
    const token = localStorage.getItem('hivestack_token')
    return fetch(path, { method: 'DELETE', headers: token ? { Authorization: `Bearer ${token}` } : {} })
  }

  async function createBoard(e: FormEvent) {
    e.preventDefault()
    const input = (document.getElementById('boardName') as HTMLInputElement)?.value ?? ''
    if (!input.trim()) return
    const r = await post<{ id: string }>('/api/boards', { name: input })
    setBid(r.id)
    await refreshBoards()
  }

  async function addCard(e: FormEvent) {
    e.preventDefault()
    if (!current || !cardTitle.trim()) return
    await post(`/api/boards/${current.id}/cards`, { column: 'Todo', title: cardTitle, body: '' })
    setCardTitle('')
    setCurrent(await get<BoardDetail>(`/api/boards/${current.id}`))
  }

  async function move(cardId: string, targetColId: string) {
    if (!current) return
    try {
      await post('/api/boards/cards/' + cardId + '/move', { column_id: targetColId })
      setCurrent(await get<BoardDetail>(`/api/boards/${current.id}`))
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'move failed')
    }
  }

  return (
    <div className="page">
      <h1>Boards</h1>
      {notice && <div className="notice">{notice}</div>}

      <section className="card">
        <h3 className="card-title">Boards</h3>
        <div className="form-row">
          <input id="boardName" placeholder="new board name" />
          <button onClick={createBoard}>create board</button>
        </div>
        <div className="form-row">
          <select value={bid} onChange={(e) => setBid(e.target.value)}>
            {boards.length === 0 && <option value="">no boards</option>}
            {boards.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name} ({b.cards})
              </option>
            ))}
          </select>
          {current && (
            <button className="scope-off" onClick={() => del(`/api/boards/${current.id}`).then(() => { setCurrent(null); setBid(''); refreshBoards() })}>
              delete board
            </button>
          )}
        </div>
        <form className="form-row" onSubmit={addCard}>
          <input placeholder="new card title" value={cardTitle} onChange={(e) => setCardTitle(e.target.value)} />
          <button type="submit">add to Todo</button>
        </form>
      </section>

      {current && (
        <div className="board">
          {current.columns.map((col, ci) => (
            <div key={col.id} className="board-col">
              <h3 className="muted">{col.name} · {col.cards.length}</h3>
              {col.cards.map((c) => (
                <div key={c.id} className="board-card">
                  <div className="row">
                    <span className="board-card-title">{c.title}</span>
                    <span>
                      {ci > 0 && (
                        <button title="move left" onClick={() => move(c.id, current.columns[ci - 1].id)}>◀</button>
                      )}
                      {ci < current.columns.length - 1 && (
                        <button title="move right" onClick={() => move(c.id, current.columns[ci + 1].id)}>▶</button>
                      )}
                      <button title="delete" onClick={() => del(`/api/boards/cards/${c.id}`).then(async () => setCurrent(await get<BoardDetail>(`/api/boards/${current.id}`)))}>
                        ✕
                      </button>
                    </span>
                  </div>
                  {c.body && <div className="prompt-desc">{c.body.slice(0, 80)}</div>}
                </div>
              ))}
              {col.cards.length === 0 && <div className="prompt-desc small">empty</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}