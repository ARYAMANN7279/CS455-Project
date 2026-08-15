import express from 'express'
import cors from 'cors'
import { createServer } from 'http'
import { WebSocketServer } from 'ws'
import 'dotenv/config'

const app = express()
app.use(cors())
app.use(express.json())

app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() })
})

const httpServer = createServer(app)
const wss = new WebSocketServer({ server: httpServer, path: '/ws' })

wss.on('connection', (socket, req) => {
  const roomId = new URL(req.url ?? '/', `http://localhost`).searchParams.get('room') ?? 'default'
  console.log(`[ws] client connected to room: ${roomId}`)

  socket.on('message', (data) => {
    // Broadcast to everyone else in the same room
    wss.clients.forEach((client) => {
      if (client !== socket && client.readyState === client.OPEN) {
        client.send(data)
      }
    })
  })

  socket.on('close', () => {
    console.log(`[ws] client disconnected from room: ${roomId}`)
  })
})

const PORT = process.env.PORT ?? 3001
httpServer.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`)
})
