'use client'

import { useState, useEffect, useRef } from 'react'
import { getApiBaseUrl } from '../lib/apiBaseUrl'

interface ReplenishmentItem {
  sku: string
  name: string
  category: string
  current_stock: number
  reorder_point: number
  sales_velocity: number
  days_until_stockout: number
  predicted_stockout_date: string
  urgency: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  recommended_order_qty: number
  vendor: string
  lead_time_days: number
  moq: number
  vendor_on_time_rate: string
  estimated_cost: number
  reason: string
}

interface ReplenishmentPlan {
  status: string
  generated_at: string
  summary: {
    total_products_needing_reorder: number
    critical_urgency: number
    high_urgency: number
    total_estimated_cost: number
    average_days_until_stockout: number
  }
  ai_analysis: string
  recommendations: ReplenishmentItem[]
}

const API_BASE_URL = getApiBaseUrl()
// Prices are stored in INR — no conversion needed
const usdToInr = (amount: number) => {
  if (!amount || !Number.isFinite(amount)) return 0
  return Math.round(amount * 100) / 100
}

const parseAIAnalysis = (text: string) => {
  if (!text || !text.trim()) {
    return <div style={{ padding: '20px', color: '#6B7280', textAlign: 'center' }}>No AI analysis available</div>
  }
  
  // Split by markdown headers (###)
  // Filter out any text before the first ### header (intro text)
  const trimmedText = text.trim()
  const firstHeaderIndex = trimmedText.indexOf('###')
  
  // If there's text before the first header, skip it
  const textToParse = firstHeaderIndex >= 0 ? trimmedText.substring(firstHeaderIndex) : trimmedText
  
  const sections = textToParse.split(/###\s+/).filter(Boolean)
  
  // Filter out sections that are too short or don't have proper content
  const validSections = sections.filter(section => {
    const lines = section.trim().split('\n')
    const title = lines[0].trim()
    const content = lines.slice(1).join('\n').trim()
    
    // Skip if title is empty or too long (likely not a header - headers should be concise)
    if (!title || title.length > 80) return false
    
    // Skip if content is empty or just a single character
    if (!content || content === '#' || content.length <= 1) return false
    
    // Skip sections with titles that look like they're not proper markdown headers
    // Filter out "Inventory Reorder Strategy for Valentine Products" - this seems to be an unwanted section
    if (title.toLowerCase().includes('inventory reorder strategy for valentine products')) {
      return false
    }
    
    // Only include sections that look like proper analysis sections
    const validSectionKeywords = [
      'priority', 'ranking', 'risk', 'assessment', 'budget', 'optimization',
      'vendor', 'supplier', 'seasonal', 'consideration', 'action', 'step',
      'recommendation', 'summary', 'analysis', 'strategy', 'immediate',
      'urgency', 'overview', 'insight', 'forecast', 'stockout'
    ]
    
    const titleLower = title.toLowerCase()
    const hasValidKeyword = validSectionKeywords.some(keyword => titleLower.includes(keyword))
    
    // If title doesn't contain any valid keywords and is longer than 30 chars, likely not a proper section
    if (!hasValidKeyword && title.length > 30) {
      return false
    }
    
    return true
  })
  
  if (validSections.length === 0) {
    // Fallback: show the raw text if no ### sections were found
    return (
      <div style={{ padding: '20px', fontSize: '14px', lineHeight: '1.8', color: '#374151', whiteSpace: 'pre-wrap' }}>
        {text}
      </div>
    )
  }
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {validSections.map((section, index) => {
        const lines = section.trim().split('\n')
        const title = lines[0].trim()
        const content = lines.slice(1).join('\n').trim()
        
        // Skip if content is empty or just "#"
        if (!content || content === '#' || content.length <= 1) {
          return null
        }
        
        // Determine icon and color based on section title
        let icon = '📊'
        let iconBg = 'linear-gradient(135deg, #6B7280 0%, #4B5563 100%)'
        let bgGradient = 'linear-gradient(135deg, #F9FAFB 0%, #F3F4F6 100%)'
        let accentColor = '#6B7280'
        
        if (title.toLowerCase().includes('priority') || title.toLowerCase().includes('ranking')) {
          icon = '🎯'
          iconBg = 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)'
          bgGradient = 'linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%)'
          accentColor = '#DC143C'
        } else if (title.toLowerCase().includes('risk')) {
          icon = '⚠️'
          iconBg = 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)'
          bgGradient = 'linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%)'
          accentColor = '#F59E0B'
        } else if (title.toLowerCase().includes('budget') || title.toLowerCase().includes('optimization')) {
          icon = '💰'
          iconBg = 'linear-gradient(135deg, #10B981 0%, #059669 100%)'
          bgGradient = 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)'
          accentColor = '#10B981'
        } else if (title.toLowerCase().includes('vendor') || title.toLowerCase().includes('supplier') || title.toLowerCase().includes('strategy')) {
          icon = '🏢'
          iconBg = 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)'
          bgGradient = 'linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%)'
          accentColor = '#3B82F6'
        } else if (title.toLowerCase().includes('seasonal') || title.toLowerCase().includes('consideration')) {
          icon = '📊'
          iconBg = 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)'
          bgGradient = 'linear-gradient(135deg, #F5F3FF 0%, #EDE9FE 100%)'
          accentColor = '#8B5CF6'
        } else if (title.toLowerCase().includes('action') || title.toLowerCase().includes('step')) {
          icon = '✅'
          iconBg = 'linear-gradient(135deg, #059669 0%, #047857 100%)'
          bgGradient = 'linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%)'
          accentColor = '#059669'
        }
        
        return (
          <div 
            key={index}
            style={{
              background: bgGradient,
              borderRadius: '16px',
              padding: '24px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
              border: '1px solid rgba(0,0,0,0.05)',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)'
              e.currentTarget.style.transform = 'translateY(-2px)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)'
              e.currentTarget.style.transform = 'translateY(0)'
            }}
          >
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '14px', 
              marginBottom: '18px'
            }}>
              <div style={{
                width: '44px',
                height: '44px',
                background: iconBg,
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '22px',
                boxShadow: `0 4px 12px ${accentColor}40`,
                flexShrink: 0
              }}>
                {icon}
              </div>
              <h3 style={{ 
                margin: 0, 
                fontSize: '18px', 
                fontWeight: '700',
                color: '#111827',
                letterSpacing: '-0.2px',
                flex: 1
              }}>
                {title}
              </h3>
            </div>
            <div style={{ 
              fontSize: '14px', 
              lineHeight: '1.8', 
              color: '#374151'
            }}>
              {formatContent(content, accentColor)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const formatContent = (content: string, accentColor: string) => {
  // Parse numbered lists and bullet points
  const lines = content.split('\n')
  
  return lines.map((line, idx) => {
    const trimmed = line.trim()
    
    // Skip empty lines
    if (!trimmed) return <div key={idx} style={{ height: '8px' }} />
    
    // Numbered list items (e.g., "1. Item" or "**ITEM**")
    if (/^\d+\./.test(trimmed) || trimmed.startsWith('**')) {
      const cleanLine = trimmed.replace(/^\d+\.\s*/, '').replace(/\*\*/g, '')
      return (
        <div key={idx} style={{ 
          display: 'flex', 
          gap: '12px', 
          marginBottom: '10px',
          alignItems: 'flex-start'
        }}>
          <div style={{
            width: '24px',
            height: '24px',
            background: accentColor,
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            marginTop: '2px'
          }}>
            <span style={{ 
              color: 'white', 
              fontWeight: '700',
              fontSize: '12px'
            }}>
              •
            </span>
          </div>
          <span style={{ 
            flex: 1,
            fontWeight: '500',
            color: '#1F2937'
          }}>
            {cleanLine}
          </span>
        </div>
      )
    }
    
    // Bullet points (sub-items)
    if (trimmed.startsWith('-') || trimmed.startsWith('•')) {
      const cleanLine = trimmed.replace(/^[-•]\s*/, '').replace(/\*\*/g, '')
      return (
        <div key={idx} style={{ 
          display: 'flex', 
          gap: '10px', 
          marginBottom: '8px',
          paddingLeft: '36px',
          alignItems: 'flex-start'
        }}>
          <span style={{ 
            color: accentColor,
            minWidth: '6px',
            height: '6px',
            background: accentColor,
            borderRadius: '50%',
            marginTop: '8px',
            flexShrink: 0
          }} />
          <span style={{ 
            flex: 1, 
            fontSize: '13px',
            color: '#4B5563',
            lineHeight: '1.6'
          }}>
            {cleanLine}
          </span>
        </div>
      )
    }
    
    // Regular paragraph
    return (
      <div key={idx} style={{ 
        marginBottom: '12px',
        color: '#4B5563',
        lineHeight: '1.7'
      }}>
        {trimmed}
      </div>
    )
  })
}

interface ReplenishmentPanelProps {
  onSwitchToNotifications?: () => void;
  onNotificationCreated?: () => void;
}

export default function ReplenishmentPanel({ onSwitchToNotifications, onNotificationCreated }: ReplenishmentPanelProps) {
  const [plan, setPlan] = useState<ReplenishmentPlan | null>(null)
  const [orderedSkus, setOrderedSkus] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'all' | 'urgent' | 'vendor'>('all')
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set())
  const [exporting, setExporting] = useState(false)
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [hasLoaded, setHasLoaded] = useState(false)
  const [callingVendor, setCallingVendor] = useState(false)
  const pollRef = useRef<NodeJS.Timeout | null>(null)
  const [allVendors, setAllVendors] = useState<{ name: string; phone: string; email?: string; priority?: number }[]>([])

  useEffect(() => {
    // Only fetch on first mount if not already loaded
    if (!hasLoaded) {
      fetchReplenishmentPlan()
    }
  }, [])

  // Load full vendor directory for the Vendors view so we can display all vendor names
  useEffect(() => {
    const fetchAllVendors = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000'
        const resp = await fetch(`${apiUrl}/api/vendors/all`)
        const data = await resp.json()
        if (data.success && Array.isArray(data.vendors)) {
          setAllVendors(data.vendors)
        }
      } catch (err) {
        console.error('Error fetching vendor directory:', err)
      }
    }

    // Only fetch once, when we first switch into vendor mode
    if (viewMode === 'vendor' && allVendors.length === 0) {
      fetchAllVendors()
    }
  }, [viewMode, allVendors.length])

  const fetchReplenishmentPlan = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/api/replenishment/plan`)
      const data = await response.json()
      setPlan(data)
      setError(null)
      setHasLoaded(true)
    } catch (err) {
      setError('Failed to load replenishment plan. Make sure the API is running.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const getUrgencyColor = (urgency: string) => {
    switch (urgency) {
      case 'CRITICAL': return '#EF4444'
      case 'HIGH': return '#F59E0B'
      case 'MEDIUM': return '#EAB308'
      case 'LOW': return '#10B981'
      default: return '#6B7280'
    }
  }

  const getUrgencyEmoji = (urgency: string) => {
    switch (urgency) {
      case 'CRITICAL': return '🔴'
      case 'HIGH': return '🟠'
      case 'MEDIUM': return '🟡'
      case 'LOW': return '🟢'
      default: return '⚪'
    }
  }

  const toggleItemSelection = (sku: string) => {
    const newSelected = new Set(selectedItems)
    if (newSelected.has(sku)) {
      newSelected.delete(sku)
    } else {
      newSelected.add(sku)
    }
    setSelectedItems(newSelected)
  }

  const exportPurchaseOrder = async () => {
    if (selectedItems.size === 0) {
      alert('Please select items to export')
      return
    }

    setExporting(true)

    try {
      const response = await fetch(`${API_BASE_URL}/api/replenishment/export-po`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skus: Array.from(selectedItems) })
      })
      
      // Check content type first
      const contentType = response.headers.get('content-type') || ''
      
      if (!response.ok) {
        // Try to get error message from JSON response
        try {
          const errorData = await response.json()
          throw new Error(errorData.error || 'Failed to generate purchase order')
        } catch (jsonErr) {
          throw new Error(`HTTP ${response.status}: Failed to generate purchase order`)
        }
      }
      
      // Check if response is PDF (application/pdf) or base64-encoded PDF
      const isBinaryContent = response.headers.get('x-binary-content') === 'true'
      
      if (contentType.includes('application/pdf') || isBinaryContent) {
        let pdfBlob: Blob
        
        if (isBinaryContent) {
          // API Gateway returns base64-encoded PDF
          const base64Data = await response.text()
          const binaryString = atob(base64Data)
          const bytes = new Uint8Array(binaryString.length)
          for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i)
          }
          pdfBlob = new Blob([bytes], { type: 'application/pdf' })
        } else {
          // Direct binary response
          pdfBlob = await response.blob()
        }
        
        // Extract filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('content-disposition') || ''
        const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
        const filename = filenameMatch 
          ? filenameMatch[1].replace(/['"]/g, '')
          : `PO-${new Date().toISOString().split('T')[0]}.pdf`
        
        // Create download link
        const url = URL.createObjectURL(pdfBlob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        
        // Show success modal
        setShowSuccessModal(true)
        setTimeout(() => setShowSuccessModal(false), 3000)
      } else {
        // Fallback: try to parse as JSON (for error messages)
        const data = await response.json()
        throw new Error(data.error || 'Invalid response from server')
      }
      
    } catch (err: any) {
      alert(`❌ Failed to export purchase order: ${err.message || 'Unknown error'}`)
      console.error(err)
    } finally {
      setExporting(false)
    }
  }

  // Show empty state on first load
  if (!hasLoaded && !loading && !error) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '20px' }}>🤖</div>
        <div style={{ fontSize: '18px', color: '#6B7280', marginBottom: '20px' }}>
          Ready to generate replenishment plan
        </div>
        <button
          onClick={fetchReplenishmentPlan}
          style={{
            padding: '12px 32px',
            background: 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)',
            color: 'white',
            border: 'none',
            borderRadius: '12px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '16px',
            boxShadow: '0 4px 12px rgba(220, 20, 60, 0.3)'
          }}
        >
          Generate Plan
        </button>
      </div>
    )
  }

  if (loading) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '20px' }}>🔄</div>
        <div style={{ fontSize: '18px', color: '#6B7280' }}>Generating replenishment plan...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '20px' }}>⚠️</div>
        <div style={{ fontSize: '18px', color: '#EF4444', marginBottom: '10px' }}>{error}</div>
        <button
          onClick={fetchReplenishmentPlan}
          style={{
            padding: '10px 20px',
            background: '#DC143C',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer'
          }}
        >
          Retry
        </button>
      </div>
    )
  }

  const handleOrderPlaced = (skus: string[]) => {
    console.log('Marking SKUs as ordered:', skus);
    setOrderedSkus(prev => new Set([...prev, ...skus]));
    setSelectedItems(new Set());
  };

  const initiateCallDirectly = async (poData: any) => {
    setCallingVendor(true)
    console.log('[CallVendor] Initiating call to', poData.vendor_name)
    try {
      const res = await fetch(`${API_BASE_URL}/api/call-vendor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vendor_name: poData.vendor_name,
          vendor_phone: poData.vendor_phone,
          contact_person: poData.contact_person,
          product_name: poData.items.map((i: any) => i.name).join(', '),
          quantity: poData.items.reduce((s: number, i: any) => s + i.quantity, 0),
          po_number: poData.po_number,
          items: poData.items,
          total_amount: poData.total_amount,
          delivery_date: poData.delivery_date,
        })
      })
      const data = await res.json()
      console.log('[CallVendor] Response:', JSON.stringify(data).slice(0, 200))
      if (data.call_sid) {
        startCallPolling(data.call_sid, poData)
      } else {
        console.error('[CallVendor] No call_sid returned:', data)
        setCallingVendor(false)
      }
    } catch (err: any) {
      console.error('[CallVendor] Error:', err)
      setCallingVendor(false)
    }
  }

  const startCallPolling = (sid: string, poData: any) => {
    if (pollRef.current) clearInterval(pollRef.current)
    let pollCount = 0
    pollRef.current = setInterval(async () => {
      pollCount++
      try {
        const res = await fetch(`${API_BASE_URL}/api/get-call-status/${sid}`)
        const data = await res.json()
        console.log(`[CallPoll #${pollCount}] Status:`, data.status, data.final_status || '')
        if (data.status === 'completed' || data.final_status === 'completed') {
          if (pollRef.current) clearInterval(pollRef.current)
          fetchResultAndNotify(sid, poData, 0)
        } else if (data.status === 'failed' || data.status === 'busy' || data.status === 'no-answer') {
          if (pollRef.current) clearInterval(pollRef.current)
          setCallingVendor(false)
        }
      } catch { /* keep polling */ }
    }, 3000)
  }

  const fetchResultAndNotify = async (sid: string, poData: any, retryCount: number) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/get-transcript/${sid}`)
      const data = await res.json()
      console.log('[Transcript] Response:', JSON.stringify(data).slice(0, 300))

      // If no transcript yet and we haven't retried too many times, wait and retry
      if (!data.transcript && !data.notification && retryCount < 5) {
        console.log(`[Transcript] No data yet, retry ${retryCount + 1}/5 in 3s...`)
        setTimeout(() => fetchResultAndNotify(sid, poData, retryCount + 1), 3000)
        return
      }

      // Save notification(s) to localStorage
      const stored = localStorage.getItem('pendingNotifications')
      const existing: any[] = stored ? JSON.parse(stored) : []
      const existingIds = new Set(existing.map((n: any) => n.id))
      let changed = false
      if (data.notification && !existingIds.has(data.notification.id)) {
        existing.push(data.notification)
        existingIds.add(data.notification.id)
        changed = true
        console.log('[Notification] Saved:', data.notification.type, data.notification.vendor_name)
      }
      if (data.extra_notifications && Array.isArray(data.extra_notifications)) {
        for (const en of data.extra_notifications) {
          if (!existingIds.has(en.id)) {
            existing.push(en)
            existingIds.add(en.id)
            changed = true
            console.log('[Notification] Saved extra:', en.type, en.vendor_name)
          }
        }
      }
      if (changed) {
        localStorage.setItem('pendingNotifications', JSON.stringify(existing))
      }
      // If fallback in progress, keep polling
      if (data.fallback_in_progress) {
        if (onNotificationCreated) onNotificationCreated()
        startCallPolling(sid, poData)
        return
      }
      // Mark order placed if YES
      const decision = data.decision || data.notification?.type
      if (decision === 'YES' || data.notification?.type === 'vendor_call_success') {
        handleOrderPlaced(poData.items.map((i: any) => i.sku))
      }
      if (onNotificationCreated) onNotificationCreated()
    } catch (err) {
      console.error('[Transcript] Error:', err)
    }
    setCallingVendor(false)
  }

  if (!plan) return null

  // Filter out ordered items
  const activeRecommendations = plan.recommendations.filter(r => !orderedSkus.has(r.sku));
  
  // Recalculate summary based on active recommendations
  const activeSummary = {
    total_products_needing_reorder: activeRecommendations.length,
    critical_urgency: activeRecommendations.filter(r => r.urgency === 'CRITICAL').length,
    high_urgency: activeRecommendations.filter(r => r.urgency === 'HIGH').length,
    total_estimated_cost: activeRecommendations.reduce((sum, r) => sum + r.estimated_cost, 0),
    average_days_until_stockout: activeRecommendations.length > 0
      ? activeRecommendations.reduce((sum, r) => sum + r.days_until_stockout, 0) / activeRecommendations.length
      : 0
  };

  const { ai_analysis } = plan
  const summary = activeSummary
  const recommendations = activeRecommendations

  return (
    <div style={{ 
      padding: '32px',
      background: 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)',
      minHeight: '100%'
    }}>
      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '56px',
              height: '56px',
              background: 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)',
              borderRadius: '16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '28px',
              boxShadow: '0 4px 12px rgba(220, 20, 60, 0.3)'
            }}>
              🤖
            </div>
            <div>
              <h1 style={{ 
                fontSize: '32px', 
                fontWeight: '700', 
                margin: 0,
                background: 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                letterSpacing: '-0.5px'
              }}>
                Replenishment Planner
              </h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px' }}>
                <span style={{ 
                  fontSize: '13px', 
                  color: '#6B7280',
                  background: 'white',
                  padding: '4px 12px',
                  borderRadius: '6px',
                  fontWeight: '500'
                }}>
                  ⚡ Powered by Amazon Nova
                </span>
                <span style={{ fontSize: '13px', color: '#9CA3AF' }}>
                  •
                </span>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>
                  Last updated: {new Date(plan.generated_at).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
          
          {/* Refresh Button */}
          <button
            onClick={fetchReplenishmentPlan}
            style={{
              padding: '12px 24px',
              background: 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontWeight: '600',
              fontSize: '14px',
              transition: 'all 0.2s',
              boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = '0 6px 16px rgba(59, 130, 246, 0.4)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(59, 130, 246, 0.3)'
            }}
          >
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        <div style={{ 
          background: 'linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(220, 20, 60, 0.1)',
          transition: 'transform 0.2s, box-shadow 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-4px)'
          e.currentTarget.style.boxShadow = '0 8px 24px rgba(220, 20, 60, 0.15)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Products to Reorder</div>
          <div style={{ fontSize: '40px', fontWeight: '800', color: '#DC143C', lineHeight: '1' }}>
            {summary.total_products_needing_reorder}
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>items need attention</div>
        </div>

        <div style={{ 
          background: 'linear-gradient(135deg, #ffffff 0%, #fef2f2 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(239, 68, 68, 0.1)',
          transition: 'transform 0.2s, box-shadow 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-4px)'
          e.currentTarget.style.boxShadow = '0 8px 24px rgba(239, 68, 68, 0.15)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Critical Urgency</div>
          <div style={{ fontSize: '40px', fontWeight: '800', color: '#EF4444', lineHeight: '1' }}>
            {summary.critical_urgency}
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>immediate action needed</div>
        </div>

        <div style={{ 
          background: 'linear-gradient(135deg, #ffffff 0%, #fffbeb 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(245, 158, 11, 0.1)',
          transition: 'transform 0.2s, box-shadow 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-4px)'
          e.currentTarget.style.boxShadow = '0 8px 24px rgba(245, 158, 11, 0.15)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>High Urgency</div>
          <div style={{ fontSize: '40px', fontWeight: '800', color: '#F59E0B', lineHeight: '1' }}>
            {summary.high_urgency}
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>reorder within 1 week</div>
        </div>

        <div style={{ 
          background: 'linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(16, 185, 129, 0.1)',
          transition: 'transform 0.2s, box-shadow 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-4px)'
          e.currentTarget.style.boxShadow = '0 8px 24px rgba(16, 185, 129, 0.15)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total Cost</div>
          <div style={{ fontSize: '36px', fontWeight: '800', color: '#10B981', lineHeight: '1' }}>
            ₹{(usdToInr(summary.total_estimated_cost) / 1000).toFixed(1)}K
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>
            ₹{usdToInr(summary.total_estimated_cost).toLocaleString()} total
          </div>
        </div>

        <div style={{ 
          background: 'linear-gradient(135deg, #ffffff 0%, #eff6ff 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(59, 130, 246, 0.1)',
          transition: 'transform 0.2s, box-shadow 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-4px)'
          e.currentTarget.style.boxShadow = '0 8px 24px rgba(59, 130, 246, 0.15)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Avg Days to Stockout</div>
          <div style={{ fontSize: '40px', fontWeight: '800', color: '#3B82F6', lineHeight: '1' }}>
            {summary.average_days_until_stockout.toFixed(0)}
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>days average runway</div>
        </div>
      </div>

      {/* AI Analysis */}
      <div style={{ 
        background: 'white', 
        padding: '28px', 
        borderRadius: '20px', 
        boxShadow: '0 4px 16px rgba(0,0,0,0.08)', 
        marginBottom: '32px',
        border: '2px solid #FEE2E2'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
          <div style={{
            width: '48px',
            height: '48px',
            background: 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)',
            borderRadius: '14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '24px',
            boxShadow: '0 4px 12px rgba(220, 20, 60, 0.3)'
          }}>
            🤖
          </div>
          <h2 style={{ 
            fontSize: '22px', 
            fontWeight: '700', 
            margin: 0,
            color: '#1F2937',
            letterSpacing: '-0.3px'
          }}>
            AI Analysis
          </h2>
          <span style={{
            marginLeft: 'auto',
            padding: '6px 14px',
            background: 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)',
            color: 'white',
            borderRadius: '8px',
            fontSize: '12px',
            fontWeight: '600',
            boxShadow: '0 2px 8px rgba(220, 20, 60, 0.2)'
          }}>
            ⚡ Amazon Nova
          </span>
        </div>
        {parseAIAnalysis(ai_analysis)}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          onClick={() => setViewMode('all')}
          style={{
            padding: '12px 24px',
            background: viewMode === 'all' ? 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)' : 'white',
            color: viewMode === 'all' ? 'white' : '#374151',
            border: viewMode === 'all' ? 'none' : '2px solid #E5E7EB',
            borderRadius: '12px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '14px',
            transition: 'all 0.2s',
            boxShadow: viewMode === 'all' ? '0 4px 12px rgba(220, 20, 60, 0.3)' : '0 2px 4px rgba(0,0,0,0.05)'
          }}
          onMouseEnter={(e) => {
            if (viewMode !== 'all') {
              e.currentTarget.style.borderColor = '#DC143C'
              e.currentTarget.style.color = '#DC143C'
            }
          }}
          onMouseLeave={(e) => {
            if (viewMode !== 'all') {
              e.currentTarget.style.borderColor = '#E5E7EB'
              e.currentTarget.style.color = '#374151'
            }
          }}
        >
          All Items ({recommendations.length})
        </button>

        <button
          onClick={() => setViewMode('urgent')}
          style={{
            padding: '12px 24px',
            background: viewMode === 'urgent' ? 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)' : 'white',
            color: viewMode === 'urgent' ? 'white' : '#374151',
            border: viewMode === 'urgent' ? 'none' : '2px solid #E5E7EB',
            borderRadius: '12px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '14px',
            transition: 'all 0.2s',
            boxShadow: viewMode === 'urgent' ? '0 4px 12px rgba(220, 20, 60, 0.3)' : '0 2px 4px rgba(0,0,0,0.05)'
          }}
          onMouseEnter={(e) => {
            if (viewMode !== 'urgent') {
              e.currentTarget.style.borderColor = '#DC143C'
              e.currentTarget.style.color = '#DC143C'
            }
          }}
          onMouseLeave={(e) => {
            if (viewMode !== 'urgent') {
              e.currentTarget.style.borderColor = '#E5E7EB'
              e.currentTarget.style.color = '#374151'
            }
          }}
        >
          🔥 Urgent Only ({summary.critical_urgency + summary.high_urgency})
        </button>

        <button
          onClick={() => setViewMode('vendor')}
          style={{
            padding: '12px 24px',
            background: viewMode === 'vendor' ? 'linear-gradient(135deg, #DC143C 0%, #A00F2B 100%)' : 'white',
            color: viewMode === 'vendor' ? 'white' : '#374151',
            border: viewMode === 'vendor' ? 'none' : '2px solid #E5E7EB',
            borderRadius: '12px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '14px',
            transition: 'all 0.2s',
            boxShadow: viewMode === 'vendor' ? '0 4px 12px rgba(220, 20, 60, 0.3)' : '0 2px 4px rgba(0,0,0,0.05)'
          }}
          onMouseEnter={(e) => {
            if (viewMode !== 'vendor') {
              e.currentTarget.style.borderColor = '#DC143C'
              e.currentTarget.style.color = '#DC143C'
            }
          }}
          onMouseLeave={(e) => {
            if (viewMode !== 'vendor') {
              e.currentTarget.style.borderColor = '#E5E7EB'
              e.currentTarget.style.color = '#374151'
            }
          }}
        >
          🏢 Vendors
        </button>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: '12px' }}>
          

          <button
            onClick={() => {
              if (selectedItems.size > 0 && plan && !callingVendor) {
                const selectedRecs = plan.recommendations.filter(r => selectedItems.has(r.sku))
                const vendor = selectedRecs[0]?.vendor || 'Vendor'
                const poData = {
                  po_number: `PO-${Date.now()}`,
                  vendor_name: vendor,
                  vendor_phone: process.env.NEXT_PUBLIC_TEST_PHONE || '',
                  contact_person: 'there',
                  items: selectedRecs.map(r => ({
                    sku: r.sku,
                    name: r.name,
                    quantity: r.recommended_order_qty,
                    unit_price: r.estimated_cost / r.recommended_order_qty
                  })),
                  total_amount: selectedRecs.reduce((sum, r) => sum + r.estimated_cost, 0),
                  delivery_date: 'as soon as possible'
                }
                initiateCallDirectly(poData)
              }
            }}
            disabled={selectedItems.size === 0 || callingVendor}
            style={{
              padding: '14px 24px',
              background: selectedItems.size === 0 ? '#E5E7EB' : 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '12px',
              fontSize: '14px',
              fontWeight: '600',
              cursor: selectedItems.size === 0 ? 'not-allowed' : 'pointer',
              boxShadow: selectedItems.size === 0 ? 'none' : '0 4px 12px rgba(16, 185, 129, 0.3)',
              opacity: selectedItems.size === 0 ? 0.5 : 1,
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            {callingVendor ? '📞 Calling...' : `📞 Call Vendor (${selectedItems.size})`}
          </button>

        </div>
      </div>

      {/* Vendor Cards or Recommendations Table */}
      {viewMode === 'vendor' ? (
        // Vendor Cards View
        <>
          {/* Flat vendor directory (all vendors known to the system) */}
          {allVendors.length > 0 && (
            <div style={{
              marginBottom: '20px',
              background: 'white',
              borderRadius: '16px',
              padding: '16px 20px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
              border: '1px solid #E5E7EB'
            }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#6B7280', marginBottom: '8px' }}>
                All Vendors in System ({allVendors.length})
              </div>
              <div style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '8px'
              }}>
                {allVendors.map((v) => (
                  <span
                    key={v.name + v.phone}
                    style={{
                      padding: '6px 10px',
                      borderRadius: '999px',
                      background: '#F3F4F6',
                      border: '1px solid #E5E7EB',
                      fontSize: '11px',
                      color: '#4B5563',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}
                  >
                    <span style={{ fontSize: '13px' }}>🏢</span>
                    <span style={{ fontWeight: 600 }}>{v.name}</span>
                    {v.phone && (
                      <span style={{ fontSize: '10px', color: '#9CA3AF' }}>
                        {v.phone}
                      </span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Vendor cards driven by current replenishment recommendations */}
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', 
            gap: '20px' 
          }}>
          {(() => {
            // Group items by vendor
            const vendorMap: Record<string, ReplenishmentItem[]> = {}
            recommendations.forEach(item => {
              if (!vendorMap[item.vendor]) vendorMap[item.vendor] = []
              vendorMap[item.vendor].push(item)
            })
            
            return Object.entries(vendorMap).map(([vendorName, items]) => {
              // Check if all items from this vendor are selected
              const allVendorItemsSelected = items.every(item => selectedItems.has(item.sku))
              const someVendorItemsSelected = items.some(item => selectedItems.has(item.sku))
              
              return (
              <div 
                key={vendorName}
                style={{
                  background: allVendorItemsSelected 
                    ? 'linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%)' 
                    : 'white',
                  borderRadius: '16px',
                  padding: '24px',
                  boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
                  border: allVendorItemsSelected 
                    ? '2px solid #DC143C' 
                    : '2px solid #E5E7EB',
                  transition: 'all 0.3s',
                  cursor: 'pointer'
                }}
                onClick={() => {
                  // Toggle selection of all items from this vendor
                  const newSelected = new Set(selectedItems)
                  if (allVendorItemsSelected) {
                    // Deselect all items from this vendor
                    items.forEach(item => newSelected.delete(item.sku))
                  } else {
                    // Select all items from this vendor
                    items.forEach(item => newSelected.add(item.sku))
                  }
                  setSelectedItems(newSelected)
                }}
                onMouseEnter={(e) => {
                  if (!allVendorItemsSelected) {
                    e.currentTarget.style.transform = 'translateY(-4px)'
                    e.currentTarget.style.boxShadow = '0 8px 24px rgba(59, 130, 246, 0.15)'
                    e.currentTarget.style.borderColor = '#3B82F6'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!allVendorItemsSelected) {
                    e.currentTarget.style.transform = 'translateY(0)'
                    e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.08)'
                    e.currentTarget.style.borderColor = '#E5E7EB'
                  }
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                  <input
                    type="checkbox"
                    checked={allVendorItemsSelected}
                    onChange={(e) => {
                      e.stopPropagation()
                      const newSelected = new Set(selectedItems)
                      if (allVendorItemsSelected) {
                        items.forEach(item => newSelected.delete(item.sku))
                      } else {
                        items.forEach(item => newSelected.add(item.sku))
                      }
                      setSelectedItems(newSelected)
                    }}
                    style={{
                      width: '20px',
                      height: '20px',
                      cursor: 'pointer',
                      accentColor: '#DC143C',
                      flexShrink: 0
                    }}
                  />
                  <div style={{
                    width: '48px',
                    height: '48px',
                    background: 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '24px',
                    boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)'
                  }}>
                    🏢
                  </div>
                  <div style={{ flex: 1 }}>
                    <h3 style={{ fontSize: '18px', fontWeight: '700', margin: 0, color: '#1F2937' }}>
                      {vendorName}
                    </h3>
                    <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '4px' }}>
                      Supplier
                    </div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                  <div style={{ background: 'linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%)', padding: '12px', borderRadius: '10px' }}>
                    <div style={{ fontSize: '11px', color: '#9CA3AF', marginBottom: '4px' }}>Items</div>
                    <div style={{ fontSize: '24px', fontWeight: '700', color: '#DC143C' }}>{items.length}</div>
                  </div>
                  <div style={{ background: 'linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%)', padding: '12px', borderRadius: '10px' }}>
                    <div style={{ fontSize: '11px', color: '#9CA3AF', marginBottom: '4px' }}>Total Cost</div>
                    <div style={{ fontSize: '24px', fontWeight: '700', color: '#10B981' }}>
                      ₹{(usdToInr(items.reduce((sum, i) => sum + i.estimated_cost, 0)) / 1000).toFixed(1)}K
                    </div>
                  </div>
                </div>

                <div style={{ borderTop: '1px solid #E5E7EB', paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span style={{ color: '#6B7280' }}>Avg Lead Time:</span>
                    <span style={{ fontWeight: '600', color: '#374151' }}>
                      {(items.reduce((sum, i) => sum + i.lead_time_days, 0) / items.length).toFixed(0)} days
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span style={{ color: '#6B7280' }}>On-Time Rate:</span>
                    <span style={{ fontWeight: '600', color: '#10B981' }}>
                      {items[0]?.vendor_on_time_rate || '95%'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span style={{ color: '#6B7280' }}>Urgent Items:</span>
                    <span style={{ fontWeight: '600', color: '#DC143C' }}>
                      {items.filter(i => ['CRITICAL', 'HIGH'].includes(i.urgency)).length}
                    </span>
                  </div>
                </div>
              </div>
            )})
          })()}
        </div>
        </>
      ) : (
        // Table View
        <div style={{ 
          background: 'white', 
          borderRadius: '16px', 
          boxShadow: '0 4px 16px rgba(0,0,0,0.08)', 
          overflow: 'hidden',
          border: '1px solid #E5E7EB'
        }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ 
              background: 'linear-gradient(135deg, #F9FAFB 0%, #F3F4F6 100%)', 
              borderBottom: '2px solid #E5E7EB' 
            }}>
              <th style={{ 
                padding: '16px', 
                textAlign: 'left', 
                fontSize: '11px', 
                fontWeight: '700', 
                color: '#6B7280',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}>
                <input 
                  type="checkbox" 
                  style={{
                    width: '18px',
                    height: '18px',
                    cursor: 'pointer',
                    accentColor: '#DC143C'
                  }}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedItems(new Set(recommendations.map(r => r.sku)))
                    } else {
                      setSelectedItems(new Set())
                    }
                  }} 
                />
              </th>
              <th style={{ padding: '16px', textAlign: 'left', fontSize: '11px', fontWeight: '700', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Product</th>
              <th style={{ padding: '16px', textAlign: 'left', fontSize: '11px', fontWeight: '700', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Urgency</th>
              <th style={{ padding: '16px', textAlign: 'right', fontSize: '11px', fontWeight: '700', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Stock</th>
              <th style={{ padding: '16px', textAlign: 'right', fontSize: '11px', fontWeight: '700', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Velocity</th>
              <th style={{ padding: '16px', textAlign: 'right', fontSize: '11px', fontWeight: '700', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Stockout</th>
              <th style={{ padding: '16px', textAlign: 'right', fontSize: '11px', fontWeight: '700', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Order Qty</th>
              <th style={{ padding: '16px', textAlign: 'left', fontSize: '11px', fontWeight: '700', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Vendor</th>
              <th style={{ padding: '16px', textAlign: 'right', fontSize: '11px', fontWeight: '700', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Cost</th>
              
            </tr>
          </thead>
          <tbody>
            {recommendations
              .filter(item => viewMode === 'all' || (viewMode === 'urgent' && ['CRITICAL', 'HIGH'].includes(item.urgency)))
              .map((item, index) => (
                <tr
                  key={item.sku}
                  style={{
                    borderBottom: '1px solid #F3F4F6',
                    background: selectedItems.has(item.sku) 
                      ? 'linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%)' 
                      : 'white',
                    transition: 'all 0.2s',
                    cursor: 'pointer'
                  }}
                  onMouseEnter={(e) => {
                    if (!selectedItems.has(item.sku)) {
                      e.currentTarget.style.background = '#F9FAFB'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!selectedItems.has(item.sku)) {
                      e.currentTarget.style.background = 'white'
                    }
                  }}
                >
                  <td style={{ padding: '16px' }}>
                    <input
                      type="checkbox"
                      checked={selectedItems.has(item.sku)}
                      onChange={() => toggleItemSelection(item.sku)}
                      style={{
                        width: '18px',
                        height: '18px',
                        cursor: 'pointer',
                        accentColor: '#DC143C'
                      }}
                    />
                  </td>
                  <td style={{ padding: '16px' }}>
                    <div style={{ fontWeight: '600', color: '#111827', fontSize: '14px', marginBottom: '4px' }}>
                      {item.name}
                    </div>
                    <div style={{ 
                      fontSize: '12px', 
                      color: '#9CA3AF',
                      fontFamily: 'ui-monospace, monospace',
                      background: '#F9FAFB',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      display: 'inline-block'
                    }}>
                      {item.sku}
                    </div>
                  </td>
                  <td style={{ padding: '16px' }}>
                    <span style={{
                      padding: '6px 12px',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: '600',
                      background: `${getUrgencyColor(item.urgency)}15`,
                      color: getUrgencyColor(item.urgency),
                      border: `1.5px solid ${getUrgencyColor(item.urgency)}30`,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}>
                      <span style={{ fontSize: '14px' }}>{getUrgencyEmoji(item.urgency)}</span>
                      {item.urgency}
                    </span>
                  </td>
                  <td style={{ padding: '16px', textAlign: 'right' }}>
                    <div style={{
                      fontWeight: '600',
                      color: '#374151',
                      fontSize: '15px'
                    }}>
                      {item.current_stock}
                    </div>
                  </td>
                  <td style={{ padding: '16px', textAlign: 'right' }}>
                    <div style={{
                      fontWeight: '500',
                      color: '#6B7280',
                      fontSize: '14px'
                    }}>
                      {item.sales_velocity}
                      <span style={{ fontSize: '12px', color: '#9CA3AF' }}>/day</span>
                    </div>
                  </td>
                  <td style={{ padding: '16px', textAlign: 'right' }}>
                    <div style={{ 
                      fontWeight: '600', 
                      color: item.days_until_stockout < 7 ? '#EF4444' : item.days_until_stockout < 14 ? '#F59E0B' : '#374151',
                      fontSize: '15px',
                      marginBottom: '2px'
                    }}>
                      {item.days_until_stockout} days
                    </div>
                    <div style={{ fontSize: '11px', color: '#9CA3AF' }}>
                      {item.predicted_stockout_date}
                    </div>
                  </td>
                  <td style={{ padding: '16px', textAlign: 'right' }}>
                    <div style={{
                      fontWeight: '700',
                      color: '#DC143C',
                      fontSize: '16px',
                      background: '#FEF2F2',
                      padding: '6px 12px',
                      borderRadius: '8px',
                      display: 'inline-block',
                      border: '1px solid #FEE2E2'
                    }}>
                      {item.recommended_order_qty}
                    </div>
                  </td>
                  <td style={{ padding: '16px' }}>
                    <div style={{ 
                      fontSize: '13px', 
                      color: '#374151',
                      fontWeight: '500',
                      marginBottom: '4px'
                    }}>
                      {item.vendor}
                    </div>
                    <div style={{ 
                      fontSize: '11px', 
                      color: '#9CA3AF',
                      background: '#F9FAFB',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      display: 'inline-block'
                    }}>
                      🚚 {item.lead_time_days}d lead time
                    </div>
                  </td>
                  <td style={{ padding: '16px', textAlign: 'right' }}>
                    <div style={{ 
                      fontWeight: '700', 
                      color: '#10B981',
                      fontSize: '16px'
                    }}>
                      ₹{usdToInr(item.estimated_cost).toLocaleString()}
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      )}

      {/* Success Modal */}
      {showSuccessModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          animation: 'fadeIn 0.2s ease-in'
        }}>
          <div style={{
            background: 'white',
            borderRadius: '20px',
            padding: '40px',
            boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)',
            maxWidth: '400px',
            textAlign: 'center',
            animation: 'slideUp 0.3s ease-out'
          }}>
            <div style={{
              width: '80px',
              height: '80px',
              background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 20px',
              fontSize: '40px',
              boxShadow: '0 8px 24px rgba(16, 185, 129, 0.4)'
            }}>
              ✓
            </div>
            <h2 style={{
              fontSize: '24px',
              fontWeight: '700',
              color: '#1F2937',
              margin: '0 0 12px 0'
            }}>
              Purchase Order Created!
            </h2>
            <p style={{
              fontSize: '16px',
              color: '#6B7280',
              margin: '0 0 8px 0'
            }}>
              PDF generated for {selectedItems.size} item{selectedItems.size !== 1 ? 's' : ''}
            </p>
            <p style={{
              fontSize: '14px',
              color: '#9CA3AF',
              margin: 0
            }}>
              Check your downloads folder
            </p>
          </div>
        </div>
      )}

      {/* CSS Animations */}
      <style jsx>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>



      <style jsx>{`
        @keyframes slideInUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  )
}
