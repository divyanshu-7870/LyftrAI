import React, { useState, useEffect, useRef } from 'react'

// Generate new session ID on each page load
const generateSessionId = () => {
  return 's-' + Math.random().toString(36).substring(2, 10)
}

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

export default function App() {
  const [sessionId] = useState(() => generateSessionId())
  const [systemPrompt, setSystemPrompt] = useState('')
  const [inputMessage, setInputMessage] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault()
    const trimmed = inputMessage.trim()
    if (!trimmed || loading) return

    // 1. Add user message locally
    const userTurn = { role: 'user', content: trimmed }
    setMessages((prev) => [...prev, userTurn])

    // 2. Clear input immediately as required
    setInputMessage('')
    setLoading(true)

    try {
      const payload = {
        session_id: sessionId,
        message: trimmed,
      }
      if (systemPrompt.trim()) {
        payload.system_prompt = systemPrompt.trim()
      }

      const response = await fetch(`${BACKEND_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      const data = await response.json()

      if (!response.ok) {
        // Readable error in chat without blank screen/crash
        const errorDetail =
          typeof data.detail === 'string'
            ? data.detail
            : JSON.stringify(data.detail || 'Request failed')
        setMessages((prev) => [
          ...prev,
          {
            role: 'error',
            content: `Error (${response.status}): ${errorDetail}`,
          },
        ])
      } else {
        // Assistant message with exact metadata
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: data.reply,
            metadata: data.metadata,
          },
        ])
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'error',
          content: `Network / Connection error: ${err.message}`,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  return (
    <div className="chat-container">
      <header className="chat-header">
        <div className="chat-title-row">
          <h1 className="chat-title">
            <span>🤖</span> Lyftr AI Assistant
          </h1>
          <div className="session-badge" title="Active Session ID">
            Session: {sessionId}
          </div>
        </div>

        <div className="system-prompt-wrapper">
          <label className="system-prompt-label" htmlFor="system-prompt-input">
            System Prompt (Optional)
          </label>
          <input
            id="system-prompt-input"
            data-testid="system-prompt-input"
            className="system-prompt-input"
            type="text"
            placeholder="Customize system behavior for this session..."
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
        </div>
      </header>

      <div className="messages-list">
        {messages.map((msg, index) => {
          if (msg.role === 'user') {
            return (
              <div key={index} className="message-row user">
                <div className="user-bubble">{msg.content}</div>
              </div>
            )
          }

          if (msg.role === 'error') {
            return (
              <div key={index} className="error-message">
                {msg.content}
              </div>
            )
          }

          // Assistant message with exact required data-testid elements
          return (
            <div
              key={index}
              className="message-row assistant"
              data-testid="assistant-message"
            >
              <div className="assistant-bubble">
                <div className="reply-content">{msg.content}</div>

                {msg.metadata && (
                  <div className="metadata-panel">
                    <span
                      data-testid="meta-source"
                      className={`meta-badge ${
                        msg.metadata.resolution_source === 'LLM_CACHE'
                          ? 'source-cache'
                          : 'source-live'
                      }`}
                    >
                      {msg.metadata.resolution_source}
                    </span>

                    <div className="meta-item">
                      <span className="meta-label">Model:</span>
                      <span data-testid="meta-model" className="meta-val">
                        {msg.metadata.model}
                      </span>
                    </div>

                    <div className="meta-item">
                      <span className="meta-label">Latency:</span>
                      <span data-testid="meta-latency" className="meta-val">
                        {msg.metadata.latency_ms} ms
                      </span>
                    </div>

                    <div className="meta-item">
                      <span className="meta-label">Tokens:</span>
                      <span>in:</span>
                      <span
                        data-testid="meta-input-tokens"
                        className="meta-val"
                      >
                        {msg.metadata.input_tokens}
                      </span>
                      <span>/ out:</span>
                      <span
                        data-testid="meta-output-tokens"
                        className="meta-val"
                      >
                        {msg.metadata.output_tokens}
                      </span>
                    </div>

                    {msg.metadata.key_id && (
                      <div className="meta-item">
                        <span className="meta-label">Key:</span>
                        <span className="meta-val">{msg.metadata.key_id}</span>
                      </div>
                    )}

                    {msg.metadata.fallback_attempts > 0 && (
                      <div className="meta-item">
                        <span className="meta-label">Fallbacks:</span>
                        <span className="meta-val">
                          {msg.metadata.fallback_attempts}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {loading && (
          <div className="message-row assistant">
            <div className="assistant-bubble">Thinking...</div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-form" onSubmit={handleSendMessage}>
        <input
          data-testid="chat-input"
          className="chat-input"
          type="text"
          placeholder="Ask a question..."
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          data-testid="send-button"
          className="send-button"
          type="submit"
          disabled={!inputMessage.trim() || loading}
        >
          Send
        </button>
      </form>
    </div>
  )
}
