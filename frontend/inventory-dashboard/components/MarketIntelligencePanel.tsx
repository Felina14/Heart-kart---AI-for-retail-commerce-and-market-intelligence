'use client'

import { useState, useEffect } from 'react'
import { getApiBaseUrl } from '../lib/apiBaseUrl'

interface CompetitorProduct {
  sku: string
  name: string
  our_price: number
  avg_competitor_price: number
  price_difference: number
  price_difference_pct: number
  competitiveness: 'UNDERPRICED' | 'OVERPRICED' | 'COMPETITIVE'
  trend: 'UP' | 'DOWN' | 'STABLE'
}

interface CompetitorData {
  category: string
  total_products_analyzed: number
  avg_our_price: number
  avg_competitor_price: number
  market_position: 'COMPETITIVE' | 'UNDERPRICED' | 'OVERPRICED'
  products: CompetitorProduct[]
}

interface RegionalTrend {
  region: string
  overall_demand_index: number
  trend: 'INCREASING' | 'DECREASING' | 'STABLE'
  categories: Record<string, {
    demand_index: number
    trend: string
    growth_rate: number
  }>
}

interface CategoryTrend {
  category: string
  product_count: number
  avg_price: number
  low_stock_products: number
  trend_signal: 'TRENDING_UP' | 'TRENDING_DOWN' | 'STABLE'
  demand_velocity: number
  opportunity_score: number
}

interface MarketIntelligenceReport {
  status: string
  report_date: string
  market_signals: {
    competitor_prices: CompetitorData
    regional_trends: {
      regions: RegionalTrend[]
      timestamp: string
      analysis_period: string
    }
    category_signals: {
      total_categories: number
      trending_up: CategoryTrend[]
      trending_down: CategoryTrend[]
      opportunities: CategoryTrend[]
      all_categories: CategoryTrend[]
    }
  }
  ai_insights: string
  key_metrics: {
    competitor_analysis: {
      market_position: string
      products_analyzed: number
    }
    regional_insights: {
      regions_analyzed: number
      trending_regions: string[]
    }
    category_opportunities: {
      trending_categories: number
      top_opportunities: CategoryTrend[]
    }
  }
  recommendations: {
    pricing: string[]
    inventory: string[]
    marketing: string[]
  }
}

const API_BASE_URL = getApiBaseUrl()

export default function MarketIntelligencePanel() {
  const [report, setReport] = useState<MarketIntelligenceReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeView, setActiveView] = useState<'overview' | 'competitor' | 'regional' | 'category'>('overview')
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [hasLoaded, setHasLoaded] = useState(false)

  useEffect(() => {
    if (!hasLoaded) {
      fetchMarketIntelligence()
    }
  }, [])

  const fetchMarketIntelligence = async (reportType: string = 'full', forceRefresh: boolean = false) => {
    try {
      setLoading(true)
      setError(null)
      
      // Add cache-busting parameter if forcing refresh
      const cacheBuster = forceRefresh ? `&_t=${Date.now()}` : ''
      const url = reportType === 'full' 
        ? `${API_BASE_URL}/api/market-intelligence${cacheBuster}`
        : `${API_BASE_URL}/api/market-intelligence?report_type=${reportType}${selectedCategory ? `&category=${selectedCategory}` : ''}${cacheBuster}`
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      })
      const result = await response.json()
      
      if (result.success && result.data) {
        setReport(result.data)
        setHasLoaded(true)
      } else {
        setError(result.error || 'Failed to load market intelligence data')
      }
    } catch (err) {
      setError('Failed to connect to API. Make sure the backend is running.')
      console.error('Error fetching market intelligence:', err)
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount)
  }

  const getTrendColor = (trend: string) => {
    if (trend.includes('UP') || trend === 'INCREASING') return '#10B981'
    if (trend.includes('DOWN') || trend === 'DECREASING') return '#EF4444'
    return '#6B7280'
  }

  const getCompetitivenessColor = (competitiveness: string) => {
    if (competitiveness === 'UNDERPRICED') return '#EF4444'
    if (competitiveness === 'OVERPRICED') return '#10B981'
    return '#6B7280'
  }

  if (loading && !report) {
    return (
      <div style={{
        padding: '60px 20px',
        textAlign: 'center',
        background: 'white',
        borderRadius: '16px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.08)'
      }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>📊</div>
        <div style={{ fontSize: '18px', color: '#6B7280', fontWeight: '600' }}>
          Loading Market Intelligence...
        </div>
      </div>
    )
  }

  if (error && !report) {
    return (
      <div style={{
        padding: '40px 20px',
        textAlign: 'center',
        background: 'white',
        borderRadius: '16px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.08)'
      }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>⚠️</div>
        <div style={{ fontSize: '18px', color: '#EF4444', fontWeight: '600', marginBottom: '16px' }}>
          {error}
        </div>
        <button
          onClick={() => fetchMarketIntelligence()}
          style={{
            padding: '12px 24px',
            background: 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)',
            color: 'white',
            border: 'none',
            borderRadius: '12px',
            cursor: 'pointer',
            fontSize: '15px',
            fontWeight: '600',
            boxShadow: '0 4px 12px rgba(220, 20, 60, 0.3)'
          }}
        >
          Retry
        </button>
      </div>
    )
  }

  if (!report) {
    return null
  }

  const competitorData = report.market_signals?.competitor_prices
  const regionalData = report.market_signals?.regional_trends
  const categoryData = report.market_signals?.category_signals

  return (
    <div style={{
      background: 'white',
      borderRadius: '16px',
      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
      padding: '32px'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '32px',
        paddingBottom: '24px',
        borderBottom: '2px solid #F3F4F6'
      }}>
        <div>
          <h1 style={{
            fontSize: '28px',
            fontWeight: '800',
            color: '#111827',
            margin: '0 0 8px 0'
          }}>
            📊 Market Intelligence
          </h1>
          <p style={{
            fontSize: '14px',
            color: '#6B7280',
            margin: 0
          }}>
            Competitor analysis, regional trends, and category signals
          </p>
        </div>
        <button
          onClick={() => {
            setHasLoaded(false) // Reset to force refresh
            fetchMarketIntelligence('full', true)
          }}
          disabled={loading}
          style={{
            padding: '12px 24px',
            background: loading ? '#9CA3AF' : 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)',
            color: 'white',
            border: 'none',
            borderRadius: '12px',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '15px',
            fontWeight: '600',
            boxShadow: loading ? 'none' : '0 4px 12px rgba(220, 20, 60, 0.3)',
            transition: 'transform 0.2s',
            opacity: loading ? 0.6 : 1
          }}
          onMouseEnter={(e) => {
            if (!loading) e.currentTarget.style.transform = 'translateY(-2px)'
          }}
          onMouseLeave={(e) => {
            if (!loading) e.currentTarget.style.transform = 'translateY(0)'
          }}
        >
          {loading ? '⏳ Refreshing...' : '🔄 Refresh'}
        </button>
      </div>

      {/* View Tabs */}
      <div style={{
        display: 'flex',
        gap: '8px',
        marginBottom: '32px',
        borderBottom: '2px solid #F3F4F6',
        paddingBottom: '16px'
      }}>
        {[
          { id: 'overview', label: '📈 Overview', icon: '📈' },
          { id: 'competitor', label: '💰 Competitor Prices', icon: '💰' },
          { id: 'regional', label: '🌍 Regional Trends', icon: '🌍' },
          { id: 'category', label: '📂 Category Signals', icon: '📂' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveView(tab.id as any)}
            style={{
              padding: '12px 20px',
              background: activeView === tab.id
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)'
                : 'transparent',
              color: activeView === tab.id ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '10px',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: '600',
              transition: 'all 0.2s'
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview View */}
      {activeView === 'overview' && (
        <div>
          {/* Key Metrics Cards */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
            gap: '20px',
            marginBottom: '32px'
          }}>
            <div style={{
              background: 'linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%)',
              padding: '24px',
              borderRadius: '12px',
              border: '1px solid #BAE6FD'
            }}>
              <div style={{ fontSize: '14px', color: '#0369A1', fontWeight: '600', marginBottom: '8px' }}>
                Market Position
              </div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#0C4A6E' }}>
                {competitorData?.market_position || 'N/A'}
              </div>
            </div>

            <div style={{
              background: 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)',
              padding: '24px',
              borderRadius: '12px',
              border: '1px solid #86EFAC'
            }}>
              <div style={{ fontSize: '14px', color: '#166534', fontWeight: '600', marginBottom: '8px' }}>
                Products Analyzed
              </div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#14532D' }}>
                {competitorData?.total_products_analyzed || 0}
              </div>
            </div>

            <div style={{
              background: 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
              padding: '24px',
              borderRadius: '12px',
              border: '1px solid #FCD34D'
            }}>
              <div style={{ fontSize: '14px', color: '#92400E', fontWeight: '600', marginBottom: '8px' }}>
                Trending Categories
              </div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#78350F' }}>
                {categoryData?.trending_up?.length || 0}
              </div>
            </div>

            <div style={{
              background: 'linear-gradient(135deg, #FDF2F8 0%, #FCE7F3 100%)',
              padding: '24px',
              borderRadius: '12px',
              border: '1px solid #F9A8D4'
            }}>
              <div style={{ fontSize: '14px', color: '#9F1239', fontWeight: '600', marginBottom: '8px' }}>
                Regions Analyzed
              </div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#831843' }}>
                {regionalData?.regions?.length || 0}
              </div>
            </div>
          </div>

          {/* AI Insights */}
          {report.ai_insights && (
            <div style={{
              background: '#F9FAFB',
              padding: '24px',
              borderRadius: '12px',
              marginBottom: '32px',
              border: '1px solid #E5E7EB'
            }}>
              <h3 style={{
                fontSize: '18px',
                fontWeight: '700',
                color: '#111827',
                margin: '0 0 16px 0'
              }}>
                🤖 AI Insights
              </h3>
              <div style={{
                fontSize: '15px',
                color: '#374151',
                lineHeight: '1.8'
              }}>
                {report.ai_insights.split('\n').map((line, idx) => {
                  const trimmed = line.trim()
                  if (trimmed.startsWith('###')) {
                    const text = trimmed.replace(/^###+\s*/, '')
                    return (
                      <h4 key={idx} style={{
                        fontSize: '16px',
                        fontWeight: '700',
                        color: '#111827',
                        margin: '24px 0 12px 0',
                        paddingBottom: '8px',
                        borderBottom: '1px solid #E5E7EB'
                      }}>
                        {text}
                      </h4>
                    )
                  }
                  if (trimmed.startsWith('**') && trimmed.endsWith('**')) {
                    const text = trimmed.replace(/\*\*/g, '')
                    return (
                      <div key={idx} style={{ margin: '8px 0', fontWeight: '700', color: '#111827' }}>
                        {text}
                      </div>
                    )
                  }
                  if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                    const text = trimmed.replace(/^[-*]\s+/, '')
                    return (
                      <div key={idx} style={{ margin: '6px 0 6px 20px', color: '#374151' }}>
                        • {text.split(/(\*\*.+?\*\*)/).map((part, pidx) => {
                          if (part.startsWith('**') && part.endsWith('**')) {
                            return <strong key={pidx} style={{ fontWeight: '700', color: '#111827' }}>{part.replace(/\*\*/g, '')}</strong>
                          }
                          return <span key={pidx}>{part}</span>
                        })}
                      </div>
                    )
                  }
                  if (trimmed.match(/^\d+\.\s+/)) {
                    const match = trimmed.match(/^(\d+\.)\s+(.+)$/)
                    if (match) {
                      const num = match[1]
                      const text = match[2]
                      return (
                        <div key={idx} style={{ margin: '6px 0 6px 20px', color: '#374151' }}>
                          {num} {text.split(/(\*\*.+?\*\*)/).map((part, pidx) => {
                            if (part.startsWith('**') && part.endsWith('**')) {
                              return <strong key={pidx} style={{ fontWeight: '700', color: '#111827' }}>{part.replace(/\*\*/g, '')}</strong>
                            }
                            return <span key={pidx}>{part}</span>
                          })}
                        </div>
                      )
                    }
                  }
                  if (trimmed.length > 0) {
                    return (
                      <p key={idx} style={{ margin: '12px 0', color: '#374151' }}>
                        {trimmed.split(/(\*\*.+?\*\*)/).map((part, pidx) => {
                          if (part.startsWith('**') && part.endsWith('**')) {
                            return <strong key={pidx} style={{ fontWeight: '700', color: '#111827' }}>{part.replace(/\*\*/g, '')}</strong>
                          }
                          return <span key={pidx}>{part}</span>
                        })}
                      </p>
                    )
                  }
                  return <br key={idx} />
                })}
              </div>
            </div>
          )}

          {/* Recommendations */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '20px'
          }}>
            {report.recommendations?.pricing?.length > 0 && (
              <div style={{
                background: 'white',
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid #E5E7EB'
              }}>
                <h4 style={{ fontSize: '16px', fontWeight: '700', color: '#111827', marginBottom: '12px' }}>
                  💰 Pricing Recommendations
                </h4>
                <ul style={{ margin: 0, paddingLeft: '20px', color: '#374151' }}>
                  {report.recommendations.pricing.map((rec, i) => (
                    <li key={i} style={{ marginBottom: '8px' }}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}

            {report.recommendations?.inventory?.length > 0 && (
              <div style={{
                background: 'white',
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid #E5E7EB'
              }}>
                <h4 style={{ fontSize: '16px', fontWeight: '700', color: '#111827', marginBottom: '12px' }}>
                  📦 Inventory Recommendations
                </h4>
                <ul style={{ margin: 0, paddingLeft: '20px', color: '#374151' }}>
                  {report.recommendations.inventory.map((rec, i) => (
                    <li key={i} style={{ marginBottom: '8px' }}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}

            {report.recommendations?.marketing?.length > 0 && (
              <div style={{
                background: 'white',
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid #E5E7EB'
              }}>
                <h4 style={{ fontSize: '16px', fontWeight: '700', color: '#111827', marginBottom: '12px' }}>
                  📢 Marketing Recommendations
                </h4>
                <ul style={{ margin: 0, paddingLeft: '20px', color: '#374151' }}>
                  {report.recommendations.marketing.map((rec, i) => (
                    <li key={i} style={{ marginBottom: '8px' }}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Competitor Prices View */}
      {activeView === 'competitor' && competitorData && (
        <div>
          <div style={{
            background: 'linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%)',
            padding: '20px',
            borderRadius: '12px',
            marginBottom: '24px',
            border: '1px solid #BAE6FD'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '14px', color: '#0369A1', fontWeight: '600', marginBottom: '4px' }}>
                  Market Position
                </div>
                <div style={{ fontSize: '20px', fontWeight: '800', color: '#0C4A6E' }}>
                  {competitorData.market_position}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '14px', color: '#0369A1', fontWeight: '600', marginBottom: '4px' }}>
                  Avg Our Price
                </div>
                <div style={{ fontSize: '20px', fontWeight: '800', color: '#0C4A6E' }}>
                  {formatCurrency(competitorData.avg_our_price)}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '14px', color: '#0369A1', fontWeight: '600', marginBottom: '4px' }}>
                  Avg Competitor Price
                </div>
                <div style={{ fontSize: '20px', fontWeight: '800', color: '#0C4A6E' }}>
                  {formatCurrency(competitorData.avg_competitor_price)}
                </div>
              </div>
            </div>
          </div>

          <div style={{
            overflowX: 'auto',
            borderRadius: '12px',
            border: '1px solid #E5E7EB'
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#F9FAFB', borderBottom: '2px solid #E5E7EB' }}>
                  <th style={{ padding: '12px', textAlign: 'left', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Product</th>
                  <th style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Our Price</th>
                  <th style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Competitor Avg</th>
                  <th style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Difference</th>
                  <th style={{ padding: '12px', textAlign: 'center', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Status</th>
                  <th style={{ padding: '12px', textAlign: 'center', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Trend</th>
                </tr>
              </thead>
              <tbody>
                {competitorData.products?.slice(0, 20).map((product, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #F3F4F6' }}>
                    <td style={{ padding: '12px', fontSize: '14px', color: '#111827' }}>
                      <div style={{ fontWeight: '600' }}>{product.name}</div>
                      <div style={{ fontSize: '12px', color: '#6B7280' }}>{product.sku}</div>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                      {formatCurrency(product.our_price)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right', fontSize: '14px', color: '#6B7280' }}>
                      {formatCurrency(product.avg_competitor_price)}
                    </td>
                    <td style={{
                      padding: '12px',
                      textAlign: 'right',
                      fontSize: '14px',
                      fontWeight: '600',
                      color: product.price_difference > 0 ? '#EF4444' : '#10B981'
                    }}>
                      {product.price_difference > 0 ? '+' : ''}{formatCurrency(product.price_difference)}
                      <div style={{ fontSize: '12px', color: '#6B7280' }}>
                        ({product.price_difference_pct > 0 ? '+' : ''}{product.price_difference_pct.toFixed(1)}%)
                      </div>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <span style={{
                        padding: '4px 12px',
                        borderRadius: '8px',
                        fontSize: '12px',
                        fontWeight: '600',
                        background: getCompetitivenessColor(product.competitiveness) === '#EF4444' ? '#FEE2E2' :
                                   getCompetitivenessColor(product.competitiveness) === '#10B981' ? '#D1FAE5' : '#F3F4F6',
                        color: getCompetitivenessColor(product.competitiveness)
                      }}>
                        {product.competitiveness}
                      </span>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <span style={{
                        padding: '4px 12px',
                        borderRadius: '8px',
                        fontSize: '12px',
                        fontWeight: '600',
                        background: getTrendColor(product.trend) === '#10B981' ? '#D1FAE5' :
                                   getTrendColor(product.trend) === '#EF4444' ? '#FEE2E2' : '#F3F4F6',
                        color: getTrendColor(product.trend)
                      }}>
                        {product.trend}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Regional Trends View */}
      {activeView === 'regional' && regionalData && (
        <div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '20px'
          }}>
            {regionalData.regions?.map((region, i) => (
              <div key={i} style={{
                background: 'white',
                padding: '24px',
                borderRadius: '12px',
                border: '1px solid #E5E7EB',
                boxShadow: '0 2px 8px rgba(0,0,0,0.04)'
              }}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '16px'
                }}>
                  <h3 style={{
                    fontSize: '18px',
                    fontWeight: '700',
                    color: '#111827',
                    margin: 0
                  }}>
                    {region.region}
                  </h3>
                  <span style={{
                    padding: '6px 12px',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: '600',
                    background: getTrendColor(region.trend) === '#10B981' ? '#D1FAE5' :
                               getTrendColor(region.trend) === '#EF4444' ? '#FEE2E2' : '#F3F4F6',
                    color: getTrendColor(region.trend)
                  }}>
                    {region.trend}
                  </span>
                </div>
                <div style={{
                  fontSize: '24px',
                  fontWeight: '800',
                  color: '#111827',
                  marginBottom: '16px'
                }}>
                  Demand Index: {region.overall_demand_index.toFixed(2)}
                </div>
                <div style={{
                  fontSize: '14px',
                  color: '#6B7280',
                  marginTop: '16px',
                  paddingTop: '16px',
                  borderTop: '1px solid #F3F4F6'
                }}>
                  <strong>Top Categories:</strong>
                  <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px' }}>
                    {Object.entries(region.categories || {}).slice(0, 5).map(([cat, data]: [string, any]) => (
                      <li key={cat} style={{ marginBottom: '4px', fontSize: '13px' }}>
                        {cat}: {data.demand_index.toFixed(2)} ({data.trend})
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Category Signals View */}
      {activeView === 'category' && categoryData && (
        <div>
          {/* Trending Up */}
          <div style={{ marginBottom: '32px' }}>
            <h3 style={{
              fontSize: '20px',
              fontWeight: '700',
              color: '#111827',
              marginBottom: '16px'
            }}>
              📈 Trending Up ({categoryData.trending_up?.length || 0})
            </h3>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '16px'
            }}>
              {categoryData.trending_up?.slice(0, 10).map((cat, i) => (
                <div key={i} style={{
                  background: 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)',
                  padding: '20px',
                  borderRadius: '12px',
                  border: '1px solid #86EFAC'
                }}>
                  <div style={{
                    fontSize: '16px',
                    fontWeight: '700',
                    color: '#14532D',
                    marginBottom: '12px'
                  }}>
                    {cat.category}
                  </div>
                  <div style={{ display: 'flex', gap: '16px', fontSize: '14px', color: '#166534' }}>
                    <div>
                      <div style={{ fontWeight: '600' }}>Products</div>
                      <div>{cat.product_count}</div>
                    </div>
                    <div>
                      <div style={{ fontWeight: '600' }}>Avg Price</div>
                      <div>{formatCurrency(cat.avg_price)}</div>
                    </div>
                    <div>
                      <div style={{ fontWeight: '600' }}>Opportunity</div>
                      <div>{cat.opportunity_score.toFixed(2)}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Opportunities */}
          <div>
            <h3 style={{
              fontSize: '20px',
              fontWeight: '700',
              color: '#111827',
              marginBottom: '16px'
            }}>
              🎯 Top Opportunities ({categoryData.opportunities?.length || 0})
            </h3>
            <div style={{
              overflowX: 'auto',
              borderRadius: '12px',
              border: '1px solid #E5E7EB'
            }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#F9FAFB', borderBottom: '2px solid #E5E7EB' }}>
                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Category</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Products</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Avg Price</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Low Stock</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Demand Velocity</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#374151' }}>Opportunity Score</th>
                  </tr>
                </thead>
                <tbody>
                  {categoryData.opportunities?.slice(0, 20).map((cat, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #F3F4F6' }}>
                      <td style={{ padding: '12px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                        {cat.category}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontSize: '14px', color: '#374151' }}>
                        {cat.product_count}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontSize: '14px', color: '#374151' }}>
                        {formatCurrency(cat.avg_price)}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontSize: '14px', color: cat.low_stock_products > 0 ? '#EF4444' : '#6B7280' }}>
                        {cat.low_stock_products}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontSize: '14px', color: '#374151' }}>
                        {cat.demand_velocity.toFixed(2)}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontSize: '14px', fontWeight: '700', color: '#10B981' }}>
                        {cat.opportunity_score.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
