'use client'

import { useState, useEffect, useRef } from 'react'
import { getApiBaseUrl } from '../lib/apiBaseUrl'

interface Product {
  sku: string
  name: string
  category: string
  color: string
  price: number
  stock_quantity: number
  in_stock: boolean
  rating: number
  vendor_name: string
  description: string
  sales_count?: number
}

interface QueryResult {
  status: string
  query: string
  total_results: number
  returned_results: number
  summary: string
  products: Product[]
  timestamp: string
}

interface Message {
  type: 'user' | 'assistant'
  content: string
  result?: QueryResult
  timestamp: Date
}

const API_BASE_URL = getApiBaseUrl()

// Format markdown-style content to React elements
const formatMessageContent = (content: string) => {
  const lines = content.split('\n')
  return lines.map((line, i) => {
    // Headers
    if (line.startsWith('### ')) {
      return <div key={i} style={{ fontSize: '16px', fontWeight: '700', marginTop: i > 0 ? '16px' : '0', marginBottom: '8px', color: '#1F2937' }}>{line.replace('### ', '')}</div>
    }
    if (line.startsWith('## ')) {
      return <div key={i} style={{ fontSize: '18px', fontWeight: '700', marginTop: i > 0 ? '20px' : '0', marginBottom: '10px', color: '#1F2937' }}>{line.replace('## ', '')}</div>
    }
    
    // Bold text with **
    if (line.includes('**')) {
      const parts = line.split('**')
      return (
        <div key={i} style={{ marginBottom: '4px' }}>
          {parts.map((part, j) => 
            j % 2 === 1 ? <strong key={j}>{part}</strong> : <span key={j}>{part}</span>
          )}
        </div>
      )
    }
    
    // Bullet points
    if (line.trim().startsWith('- ')) {
      return <div key={i} style={{ marginLeft: '16px', marginBottom: '4px' }}>• {line.trim().substring(2)}</div>
    }
    
    // Numbered lists
    if (/^\d+\.\s/.test(line.trim())) {
      return <div key={i} style={{ marginLeft: '16px', marginBottom: '4px' }}>{line.trim()}</div>
    }
    
    // Empty lines
    if (line.trim() === '') {
      return <div key={i} style={{ height: '8px' }} />
    }
    
    // Regular text
    return <div key={i} style={{ marginBottom: '4px' }}>{line}</div>
  })
}

export default function CopilotPanel() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [expandedMessages, setExpandedMessages] = useState<Set<number>>(new Set())
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Prices are stored in INR — no conversion needed
  const usdToInr = (amount: number) => {
    if (!amount || !Number.isFinite(amount)) return 0
    return Math.round(amount * 100) / 100
  }

  useEffect(() => {
    fetchSuggestions()
    // Add welcome message
    setMessages([{
      type: 'assistant',
      content: 'Hi! I\'m your Inventory Copilot. Ask me anything about our inventory.',
      timestamp: new Date()
    }])
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const fetchSuggestions = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/copilot/suggestions`)
      const data = await response.json()
      if (data.status === 'success') {
        setSuggestions(data.suggestions)
      }
    } catch (err) {
      console.error('Failed to fetch suggestions:', err)
    }
  }

  const handleSubmit = async (query?: string) => {
    const queryText = query || input
    if (!queryText.trim()) return

    // Add user message
    const userMessage: Message = {
      type: 'user',
      content: queryText,
      timestamp: new Date()
    }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await fetch(`${API_BASE_URL}/api/copilot/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: queryText })
      })
      const data = await response.json()

      // Add assistant response
      const assistantMessage: Message = {
        type: 'assistant',
        content: data.summary || 'Here are the results:',
        result: data.status === 'success' ? data : undefined,
        timestamp: new Date()
      }
      setMessages(prev => [...prev, assistantMessage])
    } catch (err) {
      const errorMessage: Message = {
        type: 'assistant',
        content: 'Sorry, I encountered an error processing your query. Please try again.',
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ 
      padding: '32px',
      background: 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)',
      minHeight: '100%',
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{
            width: '56px',
            height: '56px',
            background: 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)',
            borderRadius: '16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '28px',
            boxShadow: '0 4px 12px rgba(139, 92, 246, 0.3)'
          }}>
            💬
          </div>
          <div>
            <h1 style={{ 
              fontSize: '32px', 
              fontWeight: '700', 
              margin: 0,
              background: 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              letterSpacing: '-0.5px'
            }}>
              Inventory Copilot
            </h1>
            <div style={{ fontSize: '13px', color: '#6B7280', marginTop: '4px' }}>
              Ask questions in natural language
            </div>
          </div>
        </div>
      </div>

      {/* Chat Container */}
      <div style={{
        flex: 1,
        background: 'white',
        borderRadius: '16px',
        boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        minHeight: '600px'
      }}>
        {/* Messages */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          {messages.map((message, index) => (
            <div key={index} style={{
              display: 'flex',
              justifyContent: message.type === 'user' ? 'flex-end' : 'flex-start'
            }}>
              <div style={{
                maxWidth: '80%',
                background: message.type === 'user' 
                  ? 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)'
                  : '#F9FAFB',
                color: message.type === 'user' ? 'white' : '#1F2937',
                padding: '16px',
                borderRadius: '16px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
              }}>
                <div style={{ fontSize: '14px', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
                  {formatMessageContent(message.content)}
                </div>

                {/* Results */}
                {message.result && message.result.products && (
                  <div style={{ marginTop: '16px' }}>
                    <div style={{
                      fontSize: '12px',
                      color: '#6B7280',
                      marginBottom: '12px',
                      paddingBottom: '8px',
                      borderBottom: '1px solid #E5E7EB',
                      fontWeight: '600'
                    }}>
                      📦 {message.result.total_results} {message.result.total_results === 1 ? 'product' : 'products'} found
                    </div>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {message.result.products.slice(0, expandedMessages.has(index) ? message.result.products.length : 5).map((product) => (
                        <div key={product.sku} style={{
                          background: 'white',
                          padding: '12px',
                          borderRadius: '8px',
                          border: '1px solid #E5E7EB'
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '4px' }}>
                            <div style={{ fontWeight: '600', fontSize: '13px', color: '#1F2937' }}>
                              {product.name}
                            </div>
                            <div style={{ fontWeight: '700', fontSize: '14px', color: '#8B5CF6' }}>
                              ₹{usdToInr(product.price).toFixed(2)}
                            </div>
                          </div>
                          <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '6px' }}>
                            {product.category} • {product.color} • SKU: {product.sku}
                          </div>
                          <div style={{ display: 'flex', gap: '12px', fontSize: '11px', flexWrap: 'wrap' }}>
                            <span style={{ 
                              color: product.stock_quantity < 10 ? '#EF4444' : '#10B981',
                              fontWeight: '600'
                            }}>
                              Stock: {product.stock_quantity}
                            </span>
                            {product.sales_count !== undefined && (
                              <>
                                <span style={{ color: '#9CA3AF' }}>•</span>
                                <span style={{ color: '#8B5CF6', fontWeight: '600' }}>
                                  📊 Sold: {product.sales_count}
                                </span>
                              </>
                            )}
                            <span style={{ color: '#9CA3AF' }}>•</span>
                            <span style={{ color: '#6B7280' }}>
                              ⭐ {product.rating?.toFixed(1) || 'N/A'}
                            </span>
                            <span style={{ color: '#9CA3AF' }}>•</span>
                            <span style={{ color: '#6B7280' }}>
                              {product.vendor_name}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {message.result.returned_results > 5 && (
                      <button
                        onClick={() => {
                          setExpandedMessages(prev => {
                            const newSet = new Set(prev)
                            if (newSet.has(index)) {
                              newSet.delete(index)
                            } else {
                              newSet.add(index)
                            }
                            return newSet
                          })
                        }}
                        style={{
                          marginTop: '8px',
                          padding: '8px 16px',
                          background: 'white',
                          border: '1px solid #E5E7EB',
                          borderRadius: '8px',
                          fontSize: '12px',
                          color: '#8B5CF6',
                          cursor: 'pointer',
                          fontWeight: '600',
                          transition: 'all 0.2s',
                          width: '100%'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = '#F3F4F6'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'white'
                        }}
                      >
                        {expandedMessages.has(index) 
                          ? '▲ Show less' 
                          : `▼ Show ${message.result.returned_results - 5} more products`}
                      </button>
                    )}
                  </div>
                )}

                <div style={{
                  fontSize: '11px',
                  color: message.type === 'user' ? 'rgba(255,255,255,0.7)' : '#9CA3AF',
                  marginTop: '8px'
                }}>
                  {message.timestamp.toLocaleTimeString()}
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{
                background: '#F9FAFB',
                padding: '16px',
                borderRadius: '16px',
                display: 'flex',
                gap: '8px',
                alignItems: 'center'
              }}>
                <div style={{
                  width: '8px',
                  height: '8px',
                  background: '#8B5CF6',
                  borderRadius: '50%',
                  animation: 'pulse 1.5s ease-in-out infinite'
                }} />
                <div style={{
                  width: '8px',
                  height: '8px',
                  background: '#8B5CF6',
                  borderRadius: '50%',
                  animation: 'pulse 1.5s ease-in-out 0.2s infinite'
                }} />
                <div style={{
                  width: '8px',
                  height: '8px',
                  background: '#8B5CF6',
                  borderRadius: '50%',
                  animation: 'pulse 1.5s ease-in-out 0.4s infinite'
                }} />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div style={{
          padding: '20px',
          borderTop: '1px solid #E5E7EB',
          background: '#F9FAFB'
        }}>
          {/* Suggestions */}
          {messages.length <= 1 && suggestions.length > 0 && (
            <div style={{ marginBottom: '12px' }}>
              <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '8px' }}>
                Try these examples:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {suggestions.slice(0, 3).map((suggestion, index) => (
                  <button
                    key={index}
                    onClick={() => handleSubmit(suggestion)}
                    style={{
                      padding: '6px 12px',
                      background: 'white',
                      border: '1px solid #E5E7EB',
                      borderRadius: '8px',
                      fontSize: '12px',
                      color: '#6B7280',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = '#8B5CF6'
                      e.currentTarget.style.color = '#8B5CF6'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = '#E5E7EB'
                      e.currentTarget.style.color = '#6B7280'
                    }}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: '12px' }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !loading && handleSubmit()}
              placeholder="Ask about your inventory..."
              disabled={loading}
              style={{
                flex: 1,
                padding: '12px 16px',
                border: '2px solid #E5E7EB',
                borderRadius: '12px',
                fontSize: '14px',
                outline: 'none',
                transition: 'border-color 0.2s',
                background: 'white',
                color: '#000000'
              }}
              onFocus={(e) => e.currentTarget.style.borderColor = '#8B5CF6'}
              onBlur={(e) => e.currentTarget.style.borderColor = '#E5E7EB'}
            />
            <button
              onClick={() => handleSubmit()}
              disabled={loading || !input.trim()}
              style={{
                padding: '12px 24px',
                background: loading || !input.trim() 
                  ? '#E5E7EB' 
                  : 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)',
                color: 'white',
                border: 'none',
                borderRadius: '12px',
                cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                fontWeight: '600',
                fontSize: '14px',
                transition: 'all 0.2s',
                boxShadow: loading || !input.trim() ? 'none' : '0 4px 12px rgba(139, 92, 246, 0.3)'
              }}
            >
              {loading ? 'Thinking...' : 'Send'}
            </button>
          </div>
        </div>
      </div>

      {/* CSS Animation */}
      <style jsx>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}
