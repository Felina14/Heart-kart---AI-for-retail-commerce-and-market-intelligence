'use client'

import { useState, useEffect, useRef } from 'react'
import { getApiBaseUrl } from '../lib/apiBaseUrl'

const API_BASE_URL = getApiBaseUrl()

interface POItem {
  sku: string
  name: string
  quantity: number
  unit_price: number
}

interface POData {
  po_number: string
  vendor_name: string
  vendor_phone: string
  contact_person: string
  items: POItem[]
  total_amount: number
  delivery_date: string
}

interface CallVendorModalProps {
  isOpen: boolean
  onClose: () => void
  onOrderPlaced: (skus: string[]) => void
  onNotificationCreated?: () => void
  poData: POData
}

type CallStatus = 'idle' | 'calling' | 'in-progress' | 'completed' | 'failed'

export function CallVendorModal({ isOpen, onClose, onOrderPlaced, onNotificationCreated, poData }: CallVendorModalProps) {
  const [callStatus, setCallStatus] = useState<CallStatus>('idle')
  const [callSid, setCallSid] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState('')
  const [transcript, setTranscript] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const initiateCall = async () => {
    setCallStatus('calling')
    setError(null)
    setStatusMessage('Initiating AI call to vendor...')

    try {
      const res = await fetch(`${API_BASE_URL}/api/call-vendor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vendor_name: poData.vendor_name,
          vendor_phone: poData.vendor_phone,
          contact_person: poData.contact_person,
          product_name: poData.items.map(i => i.name).join(', '),
          quantity: poData.items.reduce((s, i) => s + i.quantity, 0),
          po_number: poData.po_number,
          items: poData.items,
          total_amount: poData.total_amount,
          delivery_date: poData.delivery_date,
        })
      })

      const data = await res.json()

      if (data.success && data.call_sid) {
        setCallSid(data.call_sid)
        setCallStatus('in-progress')
        setStatusMessage('Call connected. AI agent is speaking with vendor...')
        startPolling(data.call_sid)
      } else {
        setCallStatus('failed')
        setError(data.error || 'Failed to initiate call')
        setStatusMessage('')
      }
    } catch (err: any) {
      setCallStatus('failed')
      setError(err.message || 'Network error')
      setStatusMessage('')
    }
  }

  const startPolling = (sid: string) => {
    if (pollRef.current) clearInterval(pollRef.current)

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/get-call-status/${sid}`)
        const data = await res.json()

        if (data.status === 'completed' || data.final_status === 'completed') {
          setCallStatus('completed')
          setStatusMessage('Call completed! Checking vendor decision...')
          if (pollRef.current) clearInterval(pollRef.current)
          // Fetch transcript + notification; onOrderPlaced is called
          // inside only if the vendor said YES
          fetchTranscriptAndNotification(sid)
        } else if (data.status === 'failed' || data.status === 'busy' || data.status === 'no-answer') {
          setCallStatus('failed')
          setStatusMessage(`Call ended: ${data.status}`)
          if (pollRef.current) clearInterval(pollRef.current)
        } else {
          if (data.fallback_info) {
            const prev = data.fallback_info.previous_vendor_rejected
            const attempt = data.fallback_info.attempt
            setStatusMessage(`${prev} rejected. Calling next vendor (attempt ${attempt})...`)
          } else {
            setStatusMessage(`Call status: ${data.status || 'in-progress'}...`)
          }
        }
      } catch {
        // polling error, keep trying
      }
    }, 3000)
  }

  const saveNotification = (notif: any) => {
    const stored = localStorage.getItem('pendingNotifications')
    const existing: any[] = stored ? JSON.parse(stored) : []
    const isDuplicate = existing.some((n: any) => n.id === notif.id)
    if (!isDuplicate) {
      existing.push(notif)
      localStorage.setItem('pendingNotifications', JSON.stringify(existing))
      console.log('Saved notification to localStorage:', notif.type, notif.vendor_name)
    }
  }

  const fetchTranscriptAndNotification = async (sid: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/get-transcript/${sid}`)
      const data = await res.json()
      if (data.transcript) {
        setTranscript(typeof data.transcript === 'string' ? data.transcript : JSON.stringify(data.transcript, null, 2))
      }

      // Save notification to localStorage if the backend returned one
      if (data.notification) {
        saveNotification(data.notification)
      }

      // If fallback is in progress, resume polling for the next vendor's result
      if (data.fallback_in_progress) {
        setCallStatus('in-progress')
        setStatusMessage('Vendor rejected. Calling next vendor...')
        if (onNotificationCreated) onNotificationCreated()
        startPolling(sid)
        return
      }

      // Only mark order as placed if vendor said YES
      const decision = data.decision || data.notification?.type
      if (decision === 'YES' || data.notification?.type === 'vendor_call_success') {
        onOrderPlaced(poData.items.map(i => i.sku))
      }

      if (onNotificationCreated) onNotificationCreated()
    } catch {
      // transcript not available
    }
  }

  if (!isOpen) return null

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center',
      justifyContent: 'center', zIndex: 9999
    }}>
      <div style={{
        background: '#1a1a2e', borderRadius: '16px', padding: '32px',
        width: '560px', maxHeight: '80vh', overflowY: 'auto',
        border: '1px solid rgba(255,255,255,0.1)', color: 'white'
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h2 style={{ margin: 0, fontSize: '20px' }}>Call Vendor</h2>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: '#999', fontSize: '24px', cursor: 'pointer'
          }}>&times;</button>
        </div>

        {/* PO Summary */}
        <div style={{
          background: 'rgba(255,255,255,0.05)', borderRadius: '12px',
          padding: '16px', marginBottom: '20px'
        }}>
          <div style={{ fontSize: '14px', color: '#aaa', marginBottom: '8px' }}>Purchase Order</div>
          <div style={{ fontWeight: 600, marginBottom: '4px' }}>{poData.po_number}</div>
          <div style={{ fontSize: '14px', color: '#ccc' }}>
            Vendor: {poData.vendor_name} &middot; {poData.items.length} item{poData.items.length !== 1 ? 's' : ''}
          </div>
          <div style={{ fontSize: '14px', color: '#ccc', marginTop: '4px' }}>
            Total: Rs. {poData.total_amount.toFixed(2)}
          </div>
        </div>

        {/* Items list */}
        <div style={{ marginBottom: '20px' }}>
          {poData.items.slice(0, 5).map((item, i) => (
            <div key={item.sku} style={{
              display: 'flex', justifyContent: 'space-between', padding: '8px 0',
              borderBottom: i < Math.min(poData.items.length, 5) - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
              fontSize: '13px'
            }}>
              <span style={{ color: '#ccc' }}>{item.name}</span>
              <span style={{ color: '#aaa' }}>x{item.quantity}</span>
            </div>
          ))}
          {poData.items.length > 5 && (
            <div style={{ fontSize: '12px', color: '#888', marginTop: '4px' }}>
              +{poData.items.length - 5} more items
            </div>
          )}
        </div>

        {/* Status area */}
        {statusMessage && (
          <div style={{
            background: callStatus === 'completed' ? 'rgba(16,185,129,0.1)' :
                         callStatus === 'failed' ? 'rgba(239,68,68,0.1)' :
                         'rgba(59,130,246,0.1)',
            borderRadius: '8px', padding: '12px', marginBottom: '16px',
            fontSize: '14px',
            color: callStatus === 'completed' ? '#10B981' :
                   callStatus === 'failed' ? '#EF4444' : '#60A5FA'
          }}>
            {callStatus === 'in-progress' && (
              <span style={{ marginRight: '8px', display: 'inline-block', animation: 'spin 1s linear infinite' }}>&#9742;</span>
            )}
            {statusMessage}
          </div>
        )}

        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.1)', borderRadius: '8px',
            padding: '12px', marginBottom: '16px', fontSize: '14px', color: '#EF4444'
          }}>
            {error}
          </div>
        )}

        {/* Transcript */}
        {transcript && (
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>Call Transcript</div>
            <div style={{
              background: 'rgba(255,255,255,0.03)', borderRadius: '8px',
              padding: '12px', fontSize: '13px', color: '#ccc',
              maxHeight: '200px', overflowY: 'auto', whiteSpace: 'pre-wrap'
            }}>
              {transcript}
            </div>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          {callStatus === 'idle' && (
            <button onClick={initiateCall} style={{
              background: 'linear-gradient(135deg, #10B981, #059669)',
              color: 'white', border: 'none', borderRadius: '8px',
              padding: '10px 24px', cursor: 'pointer', fontWeight: 600, fontSize: '14px'
            }}>
              Call Vendor
            </button>
          )}
          {callStatus === 'calling' && (
            <button disabled style={{
              background: '#333', color: '#999', border: 'none', borderRadius: '8px',
              padding: '10px 24px', fontSize: '14px'
            }}>
              Connecting...
            </button>
          )}
          {(callStatus === 'completed' || callStatus === 'failed') && (
            <button onClick={onClose} style={{
              background: 'linear-gradient(135deg, #3B82F6, #2563EB)',
              color: 'white', border: 'none', borderRadius: '8px',
              padding: '10px 24px', cursor: 'pointer', fontWeight: 600, fontSize: '14px'
            }}>
              Done
            </button>
          )}
          {callStatus !== 'calling' && callStatus !== 'in-progress' && (
            <button onClick={onClose} style={{
              background: 'rgba(255,255,255,0.1)', color: '#ccc', border: 'none',
              borderRadius: '8px', padding: '10px 24px', cursor: 'pointer', fontSize: '14px'
            }}>
              {callStatus === 'idle' ? 'Cancel' : 'Close'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
