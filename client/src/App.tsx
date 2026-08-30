import { useState } from 'react'

export default function App() {
  const [roomId, setRoomId] = useState('')
  const [joined, setJoined] = useState(false)

  if (joined) {
    return <div style={{ padding: 24 }}>Room: {roomId} — editor coming soon</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 12 }}>
      <h1 style={{ fontSize: 24, margin: 0 }}>Collaborative Code Platform</h1>
      <input
        value={roomId}
        onChange={e => setRoomId(e.target.value)}
        placeholder="Room ID"
        style={{ padding: '8px 12px', fontSize: 16, borderRadius: 6, border: '1px solid #555', background: '#2d2d2d', color: '#d4d4d4', width: 240 }}
      />
      <button
        onClick={() => roomId.trim() && setJoined(true)}
        style={{ padding: '8px 24px', fontSize: 16, borderRadius: 6, border: 'none', background: '#0078d4', color: '#fff', cursor: 'pointer' }}
      >
        Join Room
      </button>
    </div>
  )
}
