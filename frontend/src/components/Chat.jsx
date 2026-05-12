import { useState, useRef, useEffect, Fragment } from 'react'
import api from '../services/api'

export default function Chat({ documentId, documentTitle, collectionId, collectionTitle }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [reasoning, setReasoning] = useState([])
  const [showReasoning, setShowReasoning] = useState(false)
  const [activeSource, setActiveSource] = useState(null)
  const messagesEndRef = useRef(null)
  const abortRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    setMessages([])
    setReasoning([])
    setError('')
    setActiveSource(null)
  }, [documentId, collectionId])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!input.trim()) return
    if (!documentId && !collectionId) return

    const userMessage = input.trim()
    setInput('')
    setError('')
    setReasoning([])
    setShowReasoning(false)
    setActiveSource(null)

    setMessages((prev) => [...prev, { type: 'user', content: userMessage }])
    setLoading(true)

    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const token = localStorage.getItem('token')
      
      const requestBody = { question: userMessage }
      if (documentId) requestBody.document_id = documentId
      if (collectionId) requestBody.collection_id = collectionId

      const response = await fetch('/api/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        throw new Error(errData.error || `Server error ${response.status}`)
      }

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
        const parts = buffer.split('\n\n')
        buffer = parts.pop()

        for (const part of parts) {
          const dataLine = part.split('\n').find((l) => l.startsWith('data: '))
          if (!dataLine) continue

          try {
            const payload = JSON.parse(dataLine.slice(6))
            if (payload.type === 'reasoning') {
              currentReasoning = [...currentReasoning, payload.content]
              setReasoning(currentReasoning)
            } else if (payload.type === 'answer') {
              assistantContent = payload.content
              sourcesFromServer = payload.sources || sourcesFromServer
            } else if (payload.type === 'complete') {
              sourcesFromServer = payload.sources || sourcesFromServer
            } else if (payload.type === 'error') {
              throw new Error(payload.content)
            }
          } catch (parseErr) {
            console.warn('SSE parse error:', parseErr)
          }
        }
      }

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
      if (err.name === 'AbortError') return
      setError(err.message || 'Failed to send message')
    } finally {
      setLoading(false)
    }
  }

  if (!documentId && !collectionId) {
    return (
      <div className="flex flex-col h-[500px] items-center justify-center text-center p-8 text-gray-500">
        <p className="text-lg mb-2">No context selected</p>
        <p className="text-sm">Select a Document or Collection to start chatting.</p>
      </div>
    )
  }

  const renderMessageContent = (text, sources) => {
    // splits based on [number] capturing group
    const parts = text.split(/(\[\d+\])/g)
    return parts.map((part, i) => {
      const match = part.match(/^\[(\d+)\]$/)
      if (match) {
        const citationNum = parseInt(match[1], 10)
        const sourceObj = sources?.find(s => s.citation_number === citationNum)
        if (sourceObj) {
          return (
            <button
              key={i}
              onClick={() => setActiveSource(sourceObj)}
              className="inline-flex items-center justify-center mx-1 px-1.5 py-0.5 bg-blue-100 text-blue-700 hover:bg-blue-200 text-xs font-semibold rounded cursor-pointer transition-colors"
              title={`View Source ${citationNum}`}
            >
              {part}
            </button>
          )
        }
      }
      return <Fragment key={i}>{part}</Fragment>
    })
  }

  return (
    <div className="flex h-[calc(100vh-180px)] bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden">
      <div className={`flex flex-col flex-1 border-r border-gray-200 transition-all ${activeSource ? 'w-2/3' : 'w-full'}`}>
        <div className="border-b border-gray-200 p-4 flex flex-col">
          <h2 className="text-2xl font-bold text-gray-900">Chat</h2>
          <p className="text-gray-600 text-sm mt-1">
            Context: <span className="font-medium text-blue-600">
              {collectionTitle ? `Collection - ${collectionTitle}` : `Document - ${documentTitle}`}
            </span>
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
          {messages.length === 0 ? (
            <div className="flex h-full items-center justify-center text-gray-500">
              Ask a question to search your knowledge base...
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] p-4 shadow-sm ${msg.type === 'user' ? 'bg-blue-600 text-white rounded-l-lg rounded-br-lg' : 'bg-white text-gray-900 rounded-r-lg rounded-bl-lg border border-gray-200'}`}>
                  <p className="whitespace-pre-wrap leading-relaxed">
                    {msg.type === 'assistant' ? renderMessageContent(msg.content, msg.sources) : msg.content}
                  </p>
                  
                  {msg.sources && msg.sources.length > 0 && msg.type === 'assistant' && (
                    <div className="mt-4 pt-3 border-t border-gray-100 text-xs text-gray-500 flex flex-wrap gap-2">
                       <span className="font-medium text-gray-700">Sources:</span>
                       {msg.sources.map((src, i) => (
                         <div key={i} className="bg-gray-100 px-2 py-1 rounded">
                           [{src.citation_number}] {src.document_title} (Page {src.page_number ?? 'N/A'})
                         </div>
                       ))}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-r-lg rounded-bl-lg p-4 shadow-sm text-gray-500 italic">
                Agent is typing...
              </div>
            </div>
          )}
          {error && <div className="text-red-600 text-center text-sm p-2">{error}</div>}
          <div ref={messagesEndRef} />
        </div>
        
        {reasoning.length > 0 && (
          <div className="border-t border-gray-200 bg-white p-2">
             <button onClick={() => setShowReasoning(!showReasoning)} className="text-sm font-medium text-gray-600 hover:text-gray-900 flex items-center px-2">
               {showReasoning ? '▼ Hide' : '▶ Show'} Agent Trace ({reasoning.length})
             </button>
             {showReasoning && (
               <div className="text-xs font-mono mt-2 p-2 mx-2 bg-gray-50 rounded max-h-32 overflow-y-auto space-y-1 border border-gray-200">
                 {reasoning.map((r, i) => <div key={i}>{r}</div>)}
               </div>
             )}
          </div>
        )}

        <form onSubmit={handleSubmit} className="border-t border-gray-200 p-4 bg-white flex gap-3">
           <input type="text" value={input} onChange={e => setInput(e.target.value)} disabled={loading} placeholder="Ask a question..." className="flex-1 p-3 border border-gray-300 rounded-lg outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500" />
           <button type="submit" disabled={loading || !input.trim()} className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg disabled:opacity-50 transition-colors">Send</button>
        </form>
      </div>

      {activeSource && (
        <div className="w-1/3 bg-gray-50 flex flex-col border-l border-gray-200 shadow-inner overflow-hidden">
           <div className="p-4 border-b border-gray-200 bg-white flex justify-between items-center shadow-sm">
             <h3 className="font-bold text-gray-800">Source Viewer</h3>
             <button onClick={() => setActiveSource(null)} className="text-gray-500 hover:bg-gray-100 rounded-full w-8 h-8 flex items-center justify-center transition-colors" title="Close Panel">
               ✕
             </button>
           </div>
           <div className="p-6 overflow-y-auto flex-1">
             <div className="mb-6 pb-4 border-b border-gray-200">
               <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-1">Document</h4>
               <p className="text-lg text-gray-900 font-medium leading-tight">{activeSource.document_title || `Document #${activeSource.document_id}`}</p>
             </div>
             <div className="mb-6 pb-4 border-b border-gray-200 flex justify-between">
               <div>
                 <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-1">Page</h4>
                 <p className="text-xl text-blue-600 font-bold">{activeSource.page_number || 'N/A'}</p>
               </div>
               {activeSource.score !== undefined && (
                 <div className="text-right">
                   <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-1">Relevance</h4>
                   <p className="text-xl text-green-600 font-bold">{Math.round(activeSource.score * 100)}%</p>
                 </div>
               )}
             </div>
             <div>
               <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">Extracted Snippet</h4>
               <div className="bg-white border border-gray-200 rounded-lg p-4 font-serif text-sm leading-relaxed text-gray-800 shadow-sm relative overflow-hidden">
                 <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500"></div>
                 {activeSource.text_preview || activeSource.text}
               </div>
             </div>
           </div>
        </div>
      )}
    </div>
  )
}