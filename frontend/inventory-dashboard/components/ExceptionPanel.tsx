'use client'

import { useState, useEffect } from 'react'
import { getApiBaseUrl } from '../lib/apiBaseUrl'

interface Anomaly {
  sku: string
  name: string
  anomaly_type: 'DEMAND_SURGE' | 'DEMAND_DROP' | 'STAGNANT'
  severity: 'HIGH' | 'MEDIUM'
  z_score: number
  recent_avg_daily: number
  historical_avg_daily: number
  total_sales: number
  stock_quantity: number
  price: number
  category: string
  vendor_name: string
}

interface Summary {
  total_anomalies: number
  by_type: Record<string, number>
  by_severity: Record<string, number>
  date_range_days: number
  total_orders_analyzed: number
}

interface ExceptionData {
  status: string
  anomalies: Anomaly[]
  summary: Summary
  insights: string
  generated_at: string
}

const API_BASE_URL = getApiBaseUrl()

export default function ExceptionPanel() {
  const [data, setData] = useState<ExceptionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'ALL' | 'DEMAND_SURGE' | 'DEMAND_DROP' | 'STAGNANT'>('ALL')
  const [days, setDays] = useState(30)

  // Prices are stored in INR — no conversion needed
  const usdToInr = (amount: number) => {
    if (!amount || !Number.isFinite(amount)) return 0
    return Math.round(amount * 100) / 100
  }

  useEffect(() => {
    fetchExceptions()
  }, [days])

  const fetchExceptions = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/exceptions/investigate?days=${days}`)
      const result = await response.json()
      setData(result)
    } catch (error) {
      console.error('Failed to fetch exceptions:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleRefresh = () => {
    fetchExceptions()
  }

  const getAnomalyIcon = (type: string) => {
    switch (type) {
      case 'DEMAND_SURGE': return '🚀'
      case 'DEMAND_DROP': return '📉'
      case 'STAGNANT': return '💤'
      default: return '⚠️'
    }
  }

  const getAnomalyColor = (type: string) => {
    switch (type) {
      case 'DEMAND_SURGE': return '#10B981'
      case 'DEMAND_DROP': return '#F59E0B'
      case 'STAGNANT': return '#6B7280'
      default: return '#EF4444'
    }
  }

  const getSeverityColor = (severity: string) => {
    return severity === 'HIGH' ? '#EF4444' : '#F59E0B'
  }

  const getProductInsight = (anomaly: Anomaly): string => {
    const daysOfStock = anomaly.recent_avg_daily > 0 
      ? Math.floor(anomaly.stock_quantity / anomaly.recent_avg_daily) 
      : 999
    
    const unitChange = anomaly.recent_avg_daily - anomaly.historical_avg_daily
    const absUnitChange = Math.abs(unitChange).toFixed(1)
    
    // Calculate percentage only if historical avg is meaningful (> 0.5 units/day)
    let changeDescription = ''
    if (anomaly.historical_avg_daily > 0.5) {
      const changePercent = Math.abs((unitChange / anomaly.historical_avg_daily) * 100)
      if (changePercent < 200) {
        changeDescription = `${changePercent.toFixed(0)}%`
      } else {
        changeDescription = `${absUnitChange} units/day`
      }
    } else {
      changeDescription = `${absUnitChange} units/day`
    }
    
    switch (anomaly.anomaly_type) {
      case 'DEMAND_SURGE':
        if (daysOfStock < 7) {
          return `⚠️ Sales surging (+${changeDescription}) but only ${daysOfStock} days of stock left. Urgent reorder needed.`
        } else if (daysOfStock < 14) {
          return `📈 Strong demand increase (+${changeDescription}). Stock running low - consider reordering soon.`
        }
        return `🚀 Significant sales growth (+${changeDescription}). Consider increasing stock levels to capitalize on demand.`
      
      case 'DEMAND_DROP':
        if (anomaly.recent_avg_daily < 0.5 && anomaly.stock_quantity > 50) {
          return `📦 Sales nearly stopped with ${anomaly.stock_quantity} units in stock. Consider promotions or clearance.`
        } else if (daysOfStock > 60) {
          return `📉 Sales declining (-${changeDescription}) with ${daysOfStock} days of excess inventory. Review pricing strategy.`
        }
        return `⚠️ Sales dropped by ${changeDescription}. Monitor trend and adjust inventory planning accordingly.`
      
      case 'STAGNANT':
        if (anomaly.stock_quantity > 100) {
          return `💤 No recent sales activity. ${anomaly.stock_quantity} units sitting idle. Consider clearance or bundle deals.`
        } else if (anomaly.stock_quantity > 50) {
          return `⏸️ Minimal sales movement with ${anomaly.stock_quantity} units in stock. Review product positioning.`
        }
        return `🔍 Low sales velocity detected. Consider marketing push or product review.`
      
      default:
        return `🔍 Unusual pattern detected. Review sales history and market conditions.`
    }
  }

  const filteredAnomalies = data?.anomalies.filter(a => 
    filter === 'ALL' || a.anomaly_type === filter
  ) || []

  if (loading) {
    return (
      <div style={{ padding: '32px', background: 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)', minHeight: '100%' }}>
        <div style={{ fontSize: '18px', color: '#6B7280' }}>Loading exceptions...</div>
      </div>
    )
  }

  if (!data || data.status !== 'success') {
    return (
      <div style={{ padding: '32px', background: 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)', minHeight: '100%' }}>
        <div style={{ fontSize: '18px', color: '#EF4444' }}>Failed to load exception data</div>
      </div>
    )
  }

  return (
    <div style={{ 
      padding: '32px',
      background: 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)',
      minHeight: '100%'
    }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '56px',
              height: '56px',
              background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
              borderRadius: '16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '28px',
              boxShadow: '0 4px 12px rgba(245, 158, 11, 0.3)'
            }}>
              🔍
            </div>
            <div>
              <h1 style={{ 
                fontSize: '32px', 
                fontWeight: '700', 
                margin: 0,
                background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                letterSpacing: '-0.5px'
              }}>
                Exception Investigator
              </h1>
              <div style={{ fontSize: '13px', color: '#6B7280', marginTop: '4px' }}>
                Anomaly detection and sales pattern analysis
              </div>
            </div>
          </div>
          <button
            onClick={handleRefresh}
            disabled={loading}
            style={{
              padding: '12px 24px',
              background: loading ? '#E5E7EB' : 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '12px',
              fontSize: '14px',
              fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: loading ? 'none' : '0 4px 12px rgba(245, 158, 11, 0.3)',
              transition: 'all 0.2s'
            }}
          >
            <span style={{ fontSize: '16px' }}>🔄</span>
            {loading ? 'Analyzing...' : 'Refresh Analysis'}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', 
        gap: '16px',
        marginBottom: '24px'
      }}>
        <div style={{
          background: 'white',
          padding: '20px',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '32px', fontWeight: '700', color: '#1F2937', marginBottom: '4px' }}>
            {data.summary.total_anomalies}
          </div>
          <div style={{ fontSize: '13px', color: '#6B7280' }}>Total Anomalies</div>
        </div>

        <div style={{
          background: 'white',
          padding: '20px',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '32px', fontWeight: '700', color: '#10B981', marginBottom: '4px' }}>
            {data.summary.by_type.DEMAND_SURGE || 0}
          </div>
          <div style={{ fontSize: '13px', color: '#6B7280' }}>🚀 Demand Surges</div>
        </div>

        <div style={{
          background: 'white',
          padding: '20px',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '32px', fontWeight: '700', color: '#F59E0B', marginBottom: '4px' }}>
            {data.summary.by_type.DEMAND_DROP || 0}
          </div>
          <div style={{ fontSize: '13px', color: '#6B7280' }}>📉 Demand Drops</div>
        </div>

        <div style={{
          background: 'white',
          padding: '20px',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
        }}>
          <div style={{ fontSize: '32px', fontWeight: '700', color: '#6B7280', marginBottom: '4px' }}>
            {data.summary.by_type.STAGNANT || 0}
          </div>
          <div style={{ fontSize: '13px', color: '#6B7280' }}>💤 Stagnant</div>
        </div>
      </div>

      {/* Controls */}
      <div style={{ 
        display: 'flex', 
        gap: '12px', 
        marginBottom: '24px',
        flexWrap: 'wrap',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          {(['ALL', 'DEMAND_SURGE', 'DEMAND_DROP', 'STAGNANT'] as const).map(type => (
            <button
              key={type}
              onClick={() => setFilter(type)}
              style={{
                padding: '8px 16px',
                background: filter === type ? 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)' : 'white',
                color: filter === type ? 'white' : '#6B7280',
                border: filter === type ? 'none' : '1px solid #E5E7EB',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: '600',
                transition: 'all 0.2s'
              }}
            >
              {type === 'ALL' ? 'All' : type.replace('_', ' ')}
            </button>
          ))}
        </div>

        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          style={{
            padding: '8px 16px',
            background: 'white',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: '600',
            color: '#6B7280',
            cursor: 'pointer'
          }}
        >
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={60}>Last 60 days</option>
        </select>

        <button
          onClick={fetchExceptions}
          style={{
            padding: '8px 16px',
            background: 'white',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '13px',
            fontWeight: '600',
            color: '#6B7280'
          }}
        >
          🔄 Refresh
        </button>
      </div>

      {/* AI Insights */}
      {data.insights && (
        <div style={{
          background: 'white',
          padding: '20px',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          marginBottom: '24px'
        }}>
          <div style={{ fontSize: '16px', fontWeight: '700', marginBottom: '16px', color: '#1F2937' }}>
            💡 AI Insights
          </div>
          <div style={{ fontSize: '14px', color: '#4B5563', lineHeight: '1.8' }}>
            {data.insights.split('\n').map((line, i) => {
              // Headers
              if (line.startsWith('### **')) {
                const text = line.replace(/###\s*\*\*|\*\*/g, '').trim()
                return (
                  <div key={i} style={{ 
                    fontSize: '16px', 
                    fontWeight: '700', 
                    color: '#1F2937',
                    marginTop: i > 0 ? '20px' : '0',
                    marginBottom: '12px'
                  }}>
                    {text}
                  </div>
                )
              }
              // Numbered items
              if (/^\d+\.\s\*\*/.test(line)) {
                const text = line.replace(/\*\*/g, '').trim()
                return (
                  <div key={i} style={{ 
                    fontWeight: '600',
                    color: '#374151',
                    marginTop: '12px',
                    marginBottom: '8px'
                  }}>
                    {text}
                  </div>
                )
              }
              // Bullet points with bold
              if (line.trim().startsWith('- **')) {
                const text = line.replace(/^-\s*\*\*|\*\*/g, '').trim()
                return (
                  <div key={i} style={{ 
                    paddingLeft: '20px',
                    marginTop: '6px',
                    color: '#4B5563'
                  }}>
                    • {text}
                  </div>
                )
              }
              // Regular bullet points
              if (line.trim().startsWith('-')) {
                const text = line.replace(/^-\s*/, '').trim()
                return (
                  <div key={i} style={{ 
                    paddingLeft: '20px',
                    marginTop: '4px',
                    color: '#6B7280'
                  }}>
                    • {text}
                  </div>
                )
              }
              // Bold text
              if (line.includes('**')) {
                const parts = line.split('**')
                return (
                  <div key={i} style={{ marginTop: '8px' }}>
                    {parts.map((part, j) => 
                      j % 2 === 1 ? 
                        <span key={j} style={{ fontWeight: '600', color: '#374151' }}>{part}</span> : 
                        <span key={j}>{part}</span>
                    )}
                  </div>
                )
              }
              // Empty lines
              if (line.trim() === '') {
                return <div key={i} style={{ height: '8px' }} />
              }
              // Regular text
              return (
                <div key={i} style={{ marginTop: '4px', color: '#6B7280' }}>
                  {line}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Anomalies List */}
      <div style={{
        background: 'white',
        borderRadius: '12px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        overflow: 'hidden'
      }}>
        <div style={{ 
          padding: '20px', 
          borderBottom: '1px solid #E5E7EB',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div style={{ fontSize: '18px', fontWeight: '700', color: '#1F2937' }}>
            Detected Anomalies ({filteredAnomalies.length})
          </div>
        </div>

        {filteredAnomalies.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#6B7280' }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>✅</div>
            <div style={{ fontSize: '16px', fontWeight: '600', marginBottom: '8px' }}>
              No Anomalies Detected
            </div>
            <div style={{ fontSize: '14px' }}>
              Sales patterns are within normal ranges
            </div>
          </div>
        ) : (
          <div style={{ maxHeight: '600px', overflowY: 'auto' }}>
            {filteredAnomalies.map((anomaly, index) => (
              <div
                key={anomaly.sku}
                style={{
                  padding: '20px',
                  borderBottom: index < filteredAnomalies.length - 1 ? '1px solid #E5E7EB' : 'none',
                  transition: 'background 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#F9FAFB'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'white'}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                      <span style={{ fontSize: '24px' }}>{getAnomalyIcon(anomaly.anomaly_type)}</span>
                      <div>
                        <div style={{ fontSize: '16px', fontWeight: '700', color: '#1F2937' }}>
                          {anomaly.name}
                        </div>
                        <div style={{ fontSize: '12px', color: '#6B7280', marginTop: '2px' }}>
                          SKU: {anomaly.sku} • {anomaly.category}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginTop: '12px' }}>
                      <div style={{
                        padding: '6px 12px',
                        background: getAnomalyColor(anomaly.anomaly_type) + '20',
                        color: getAnomalyColor(anomaly.anomaly_type),
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '600'
                      }}>
                        {anomaly.anomaly_type.replace('_', ' ')}
                      </div>
                      <div style={{
                        padding: '6px 12px',
                        background: getSeverityColor(anomaly.severity) + '20',
                        color: getSeverityColor(anomaly.severity),
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '600'
                      }}>
                        {anomaly.severity} SEVERITY
                      </div>
                      <div style={{
                        padding: '6px 12px',
                        background: '#F3F4F6',
                        color: '#4B5563',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '600'
                      }}>
                        Z-Score: {anomaly.z_score.toFixed(2)}
                      </div>
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '24px', fontWeight: '700', color: '#1F2937' }}>
                    ₹{usdToInr(anomaly.price).toFixed(2)}
                    </div>
                    <div style={{ fontSize: '12px', color: '#6B7280', marginTop: '4px' }}>
                      Stock: {anomaly.stock_quantity}
                    </div>
                  </div>
                </div>

                {/* Product Insight */}
                <div style={{
                  marginTop: '12px',
                  padding: '12px 16px',
                  background: 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
                  borderLeft: '3px solid #F59E0B',
                  borderRadius: '8px',
                  fontSize: '13px',
                  color: '#92400E',
                  lineHeight: '1.6',
                  fontWeight: '500'
                }}>
                  {getProductInsight(anomaly)}
                </div>

                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', 
                  gap: '12px',
                  marginTop: '12px',
                  padding: '12px',
                  background: '#F9FAFB',
                  borderRadius: '8px'
                }}>
                  <div>
                    <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '4px' }}>Recent Avg (3d)</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#1F2937' }}>
                      {anomaly.recent_avg_daily.toFixed(1)}/day
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '4px' }}>Historical Avg</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#1F2937' }}>
                      {anomaly.historical_avg_daily.toFixed(1)}/day
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '4px' }}>Total Sales</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#1F2937' }}>
                      {anomaly.total_sales} units
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '4px' }}>Vendor</div>
                    <div style={{ fontSize: '13px', fontWeight: '600', color: '#4B5563' }}>
                      {anomaly.vendor_name}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{ marginTop: '16px', fontSize: '12px', color: '#9CA3AF', textAlign: 'center' }}>
        Last updated: {new Date(data.generated_at).toLocaleString()} • 
        Analyzed {data.summary.total_orders_analyzed} orders over {data.summary.date_range_days} days
      </div>
    </div>
  )
}
