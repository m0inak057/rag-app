import { useState, useRef, useEffect } from 'react'
import api from '../services/api'

/**
 * Chat component.
 *
 * Props:
 *   documentId  (number | null)  — the document to chat with
 *   documentTitle (string)       — display name
 */
export default function Chat({ documentId, documentTitle }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [reasoning, setReasoning] = useState([])
  const [showReasoning, setShowReasoning] = useState(false)
  const messagesEndRef = useRef(null)
  const abortRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Reset chat when document changes
  useEffect(() => {
    setMessages([])
    setReasoning([])
    setError('')
  }, [documentId])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!input.trim() || !documentId) return

    const userMessage = input.trim()
    setInput('')
    setError('')
    setReasoning([])
    setShowReasoning(false)

    setMessages((prev) => [...prev, { type: 'user', content: userMessage }])
    setLoading(true)

    // Abort any previous in-flight request
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const token = localStorage.getItem('token')

      // Use fetch instead of EventSource so we can POST with a JSON body.
      // The backend streams back Server-Sent Events via StreamingHttpResponse.
      const response = await fetch('/api/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question: userMessage,
          document_id: documentId,
        }),
        signal: controller.signal,
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        throw new Error(errData.error || `Server error ${response.status}`)
      }

      // Read the SSE stream line-by-line
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let assistantContent = ''
      let currentReasoning = []
      let sourcesFromServer = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // SSE lines are separated by double-newline
        const parts = buffer.split('\n\n')
        buffer = parts.pop() // keep incomplete chunk

        for (const part of parts) {
          // Each SSE event looks like: "data: <json>"
          const dataLine = part.split('\n').find((l) => l.startsWith('data: '))
          if (!dataLine) continue

          try {
            const payload = JSON.parse(dataLine.slice(6)) // strip "data: "

            if (payload.type === 'reasoning') {
              currentReasoning = [...currentReasoning, payload.content]
              setReasoning(currentReasoning)
            } else if (payload.type === 'answer') {
              assistantContent = payload.content
            } else if (payload.type === 'complete') {
              // Stream finished — nothing extra needed, message added below
            } else if (payload.type === 'error') {
              throw new Error(payload.content)
            }
          } catch (parseErr) {
            console.warn('SSE parse error:', parseErr)
          }
        }
      }

      // Add the final AI message once streaming is done
      if (assistantContent) {
        setMessages((prev) => [
          ...prev,
          {
            type: 'assistant',
            content: assistantContent,
            sources: sourcesFromServer,
          },
        ])
      } else {
        setError('No answer received from the agent.')
      }
    } catch (err) {
      if (err.name === 'AbortError') return // user navigated away
      setError(err.message || 'Failed to send message')
    } finally {
      setLoading(false)
    }
  }

  // Guard: no document selected
  if (!documentId) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-center p-8">
        <p className="text-gray-500 text-lg mb-2">No document selected</p>
        <p className="text-gray-400 text-sm">
          Go to <span className="font-medium">Documents</span> tab, select a ready document, then come back here to chat.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Header */}
      <div className="border-b border-gray-200 p-6">
        <h2 className="text-2xl font-bold text-gray-900">Chat with your Document</h2>
        <p className="text-gray-600 text-sm mt-1">
          Chatting with: <span className="font-medium text-blue-600">{documentTitle || `Document #${documentId}`}</span>
        </p>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-gray-500 text-lg mb-2">No messages yet</p>
              <p className="text-gray-400">Start by asking a question about your document</p>
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-2xl ${
                    msg.type === 'user'
                      ? 'bg-blue-600 text-white rounded-lg rounded-tr-none'
                      : 'bg-gray-100 text-gray-900 rounded-lg rounded-tl-none'
                  } p-4`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>

                  {/* Sources */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-gray-300">
                      <p className="font-semibold text-sm mb-2">Sources used:</p>
                      <ul className="space-y-1">
                        {msg.sources.map((source, sidx) => (
                          <li key={sidx} className="text-sm opacity-75">
                            • {source.text ? source.text.slice(0, 80) + '…' : `Chunk #${source.id}`}
                            {source.score !== undefined && (
                              <span className="ml-1 text-xs">({(source.score * 100).toFixed(0)}%)</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-lg rounded-tl-none p-4">
                  <div className="flex gap-2">
                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Reasoning Panel */}
      {reasoning.length > 0 && (
        <div className="border-t border-gray-200 bg-gray-50 p-4">
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            className="flex items-center gap-2 text-gray-700 hover:text-gray-900 font-medium"
          >
            {showReasoning ? '▼' : '▶'} Agent Reasoning ({reasoning.length} steps)
          </button>
          {showReasoning && (
            <div className="mt-3 space-y-2 max-h-40 overflow-y-auto">
              {reasoning.map((step, idx) => (
                <div key={idx} className="text-sm text-gray-700 bg-white p-2 rounded border border-gray-200 font-mono">
                  {step}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="border-t border-red-200 bg-red-50 p-4">
          <p className="text-red-700 text-sm">⚠ {error}</p>
        </div>
      )}

      {/* Input Area */}
      <div className="border-t border-gray-200 p-6 bg-white">
        <form onSubmit={handleSubmit} className="flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            placeholder="Ask a question about your document..."
            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:bg-gray-100"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400 transition"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
