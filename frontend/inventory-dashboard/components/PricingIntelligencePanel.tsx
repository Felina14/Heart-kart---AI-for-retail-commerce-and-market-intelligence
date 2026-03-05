'use client'

import { useState, useEffect } from 'react'
import { getApiBaseUrl } from '../lib/apiBaseUrl'

interface PriceRange {
  min_price: number
  optimal_price: number
  max_price: number
}

interface PriceRecommendation {
  action: 'INCREASE_PRICE' | 'DECREASE_PRICE' | 'MAINTAIN_PRICE' | 'CONSIDER_INCREASE' | 'CONSIDER_DECREASE'
  reason: string
  suggested_price: number
  price_change: number
  price_change_percent: number
}

interface PriceRangeData {
  sku: string
  product_name: string
  category: string
  current_price: number
  cost_price: number
  current_margin_percent: number
  competitor_price: number
  price_range: PriceRange
  guardrails: {
    min_margin_percent: number
    max_discount_percent: number
    competitive_price_tolerance: number
  }
  recommendation: PriceRecommendation
}

interface CompetitorEntry {
  platform: string
  price: number
  price_difference: number
  price_difference_pct: number
  rating: number
  delivery: string
  in_stock: boolean
  price_trend: 'UP' | 'DOWN' | 'STABLE'
  price_trend_pct: number
  last_checked: string
}

interface CategoryProduct {
  sku: string
  name: string
  our_price: number
  avg_competitor_price: number
  price_difference: number
  price_difference_pct: number
  competitiveness: string
}

interface CompetitorComparison {
  sku?: string
  product_name?: string
  category?: string
  our_price: number
  avg_competitor_price: number
  lowest_competitor_price?: number
  highest_competitor_price?: number
  price_difference: number
  price_difference_pct: number
  competitiveness: 'UNDERPRICED' | 'OVERPRICED' | 'COMPETITIVE'
  market_insight?: string
  competitors?: CompetitorEntry[]
  category_products?: CategoryProduct[]
  trend: 'UP' | 'DOWN' | 'STABLE'
  products?: Array<{
    sku: string
    name: string
    our_price: number
    avg_competitor_price: number
    price_difference: number
    price_difference_pct: number
    competitiveness: string
  }>
}

interface DemandScenario {
  new_price: number
  price_change_pct: number
  label: string
  is_current: boolean
  expected_velocity: number
  demand_change_pct: number
  expected_revenue: number
  revenue_change: number
  revenue_change_pct: number
  expected_margin: number
  margin_change: number
  margin_change_pct: number
  recommendation: string
}

interface DemandImpact {
  sku: string
  product_name: string
  category?: string
  price_segment?: string
  current_price: number
  cost_price?: number
  new_price: number
  price_change_pct: number
  elasticity?: number
  demand_impact: {
    current_velocity: number
    expected_velocity: number
    demand_change_pct: number
  }
  revenue_impact: {
    current_revenue: number
    expected_revenue: number
    revenue_change: number
    revenue_change_pct: number
  }
  margin_impact: {
    current_margin: number
    expected_margin: number
    margin_change: number
    margin_change_pct: number
  }
  scenarios?: DemandScenario[]
  best_revenue_scenario?: DemandScenario
  best_margin_scenario?: DemandScenario
  recommendation: {
    action: string
    reason: string
  }
}

interface OptimizationRecommendation {
  sku: string
  product_name: string
  category: string
  current_price: number
  recommended_price: number
  price_change: number
  price_change_pct: number
  current_margin: number
  competitiveness: string
  expected_revenue_change_pct: number
  expected_margin_change_pct: number
  recommendation: string
  priority_score: number
  reason: string
}

interface RelatedProductRange {
  sku: string
  product_name: string
  current_price: number
  optimal_price: number
  competitor_price: number
  current_margin_percent: number
  action: string
  price_change_pct?: number
}

interface DemandProduct {
  sku: string
  product_name: string
  current_price: number
  category: string
  action: string
}

interface PricingIntelligenceReport {
  status: string
  report_date: string
  analysis_type: string
  guardrails?: {
    guardrails: {
      min_margin_percent: number
      max_discount_percent: number
      competitive_price_tolerance: number
    }
  }
  price_range?: PriceRangeData
  related_products?: RelatedProductRange[]
  competitor_comparison?: CompetitorComparison
  demand_impact?: DemandImpact
  demand_products?: DemandProduct[]
  optimization_recommendations?: {
    category: string
    total_recommendations: number
    summary: {
      increase_price: number
      decrease_price: number
      maintain_price: number
      avg_price_change_pct: number
      total_revenue_impact_pct: number
    }
    recommendations: OptimizationRecommendation[]
  }
  ai_insights?: string
}

const API_BASE_URL = getApiBaseUrl()

export default function PricingIntelligencePanel() {
  const [report, setReport] = useState<PricingIntelligenceReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeView, setActiveView] = useState<'overview' | 'price_range' | 'competitor' | 'demand' | 'optimization'>('overview')
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [selectedSku, setSelectedSku] = useState<string>('')
  const [hasLoaded, setHasLoaded] = useState(false)

  useEffect(() => {
    if (!hasLoaded) {
      fetchPricingIntelligence()
    }
  }, [])

  const fetchPricingIntelligence = async (analysisType: string = 'full', sku?: string, category?: string, forceRefresh: boolean = false) => {
    try {
      setLoading(true)
      setError(null)
      
      // Add cache-busting parameter if forcing refresh
      const cacheBuster = forceRefresh ? `&_t=${Date.now()}` : ''
      let url = `${API_BASE_URL}/api/pricing-intelligence?analysis_type=${analysisType}${cacheBuster}`
      if (sku) url += `&sku=${sku}`
      if (category) url += `&category=${category}`
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      })
      const result = await response.json()
      
      if (result.success && result.data) {
        // For sub-tab queries (price_range, competitor_comparison, demand_impact),
        // merge the new data into the existing report so we don't lose other tab data
        if (analysisType !== 'full' && report) {
          setReport(prev => prev ? { ...prev, ...result.data } : result.data)
        } else {
        setReport(result.data)
        }
        setHasLoaded(true)
      } else {
        setError(result.error || 'Failed to load pricing intelligence data')
      }
    } catch (err) {
      setError('Failed to connect to API. Make sure the backend is running.')
      console.error('Error fetching pricing intelligence:', err)
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

  const getActionColor = (action: string) => {
    if (action.includes('INCREASE')) return '#10B981'
    if (action.includes('DECREASE')) return '#EF4444'
    if (action === 'MAINTAIN_PRICE') return '#6B7280'
    return '#F59E0B'
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
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>💰</div>
        <div style={{ fontSize: '18px', color: '#6B7280', fontWeight: '600' }}>
          Loading Pricing Intelligence...
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
          onClick={() => fetchPricingIntelligence()}
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
            💰 Pricing Intelligence
          </h1>
          <p style={{
            fontSize: '14px',
            color: '#6B7280',
            margin: 0
          }}>
            Price recommendations, competitor comparisons, and demand impact analysis
          </p>
        </div>
        <button
          onClick={() => {
            setHasLoaded(false) // Reset to force refresh
            fetchPricingIntelligence('full', undefined, undefined, true)
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
        paddingBottom: '16px',
        flexWrap: 'wrap'
      }}>
        {[
          { id: 'overview', label: '📊 Overview', icon: '📊' },
          { id: 'optimization', label: '🎯 Optimization', icon: '🎯' },
          { id: 'price_range', label: '💰 Price Range', icon: '💰' },
          { id: 'competitor', label: '⚔️ Competitor', icon: '⚔️' },
          { id: 'demand', label: '📈 Demand Impact', icon: '📈' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveView(tab.id as any)
              if (tab.id === 'optimization') {
                fetchPricingIntelligence('optimization', undefined, selectedCategory)
              } else if (tab.id === 'price_range') {
                // Only fetch if user has explicitly selected a SKU
                if (selectedSku) {
                  fetchPricingIntelligence('price_range', selectedSku, selectedCategory || undefined)
                }
                // No auto-select — show product picker from existing optimization data
              } else if (tab.id === 'competitor') {
                // Only fetch if user has explicitly selected a SKU
                if (selectedSku) {
                  fetchPricingIntelligence('competitor_comparison', selectedSku, selectedCategory || undefined)
                }
                // No auto-select — show product picker from existing optimization data
              } else if (tab.id === 'demand') {
                // Only fetch if user has explicitly selected a SKU
                if (selectedSku) {
                  fetchPricingIntelligence('demand_impact', selectedSku, undefined)
                }
                // No auto-select — show product picker from existing optimization data
              }
            }}
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
      {activeView === 'overview' && report.optimization_recommendations && (
        <div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '20px',
            marginBottom: '32px'
          }}>
            <div style={{
              padding: '24px',
              background: 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)',
              borderRadius: '12px',
              border: '2px solid #10B981'
            }}>
              <div style={{ fontSize: '32px', marginBottom: '8px' }}>📈</div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#111827', marginBottom: '4px' }}>
                {report.optimization_recommendations.total_recommendations}
              </div>
              <div style={{ fontSize: '14px', color: '#6B7280' }}>Total Recommendations</div>
            </div>
            
            <div style={{
              padding: '24px',
              background: 'linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%)',
              borderRadius: '12px',
              border: '2px solid #EF4444'
            }}>
              <div style={{ fontSize: '32px', marginBottom: '8px' }}>⬆️</div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#111827', marginBottom: '4px' }}>
                {report.optimization_recommendations.summary.increase_price}
              </div>
              <div style={{ fontSize: '14px', color: '#6B7280' }}>Increase Price</div>
            </div>
            
            <div style={{
              padding: '24px',
              background: 'linear-gradient(135deg, #F0F9FF 0%, #DBEAFE 100%)',
              borderRadius: '12px',
              border: '2px solid #3B82F6'
            }}>
              <div style={{ fontSize: '32px', marginBottom: '8px' }}>⬇️</div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#111827', marginBottom: '4px' }}>
                {report.optimization_recommendations.summary.decrease_price}
              </div>
              <div style={{ fontSize: '14px', color: '#6B7280' }}>Decrease Price</div>
            </div>
            
            <div style={{
              padding: '24px',
              background: 'linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%)',
              borderRadius: '12px',
              border: '2px solid #F59E0B'
            }}>
              <div style={{ fontSize: '32px', marginBottom: '8px' }}>💰</div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#111827', marginBottom: '4px' }}>
                {report.optimization_recommendations.summary.avg_price_change_pct.toFixed(1)}%
              </div>
              <div style={{ fontSize: '14px', color: '#6B7280' }}>Avg Price Change</div>
            </div>
          </div>

          {report.guardrails && (
            <div style={{
              padding: '20px',
              background: '#F9FAFB',
              borderRadius: '12px',
              marginBottom: '32px'
            }}>
              <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: '#111827' }}>
                🛡️ Pricing Guardrails
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                <div>
                  <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Min Margin</div>
                  <div style={{ fontSize: '18px', fontWeight: '700', color: '#111827' }}>
                    {report.guardrails.guardrails.min_margin_percent}%
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Max Discount</div>
                  <div style={{ fontSize: '18px', fontWeight: '700', color: '#111827' }}>
                    {report.guardrails.guardrails.max_discount_percent}%
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Competitive Tolerance</div>
                  <div style={{ fontSize: '18px', fontWeight: '700', color: '#111827' }}>
                    {report.guardrails.guardrails.competitive_price_tolerance}%
                  </div>
                </div>
              </div>
            </div>
          )}

          {report.ai_insights && !report.ai_insights.includes('fallback mode') && (
            <div style={{
              padding: '28px',
              background: 'linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%)',
              borderRadius: '12px',
              border: '2px solid #0EA5E9',
              marginBottom: '32px'
            }}>
              <h3 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '20px', color: '#111827', display: 'flex', alignItems: 'center', gap: '8px' }}>
                🤖 AI Pricing Strategy Insights
              </h3>
              <div style={{
                fontSize: '14px',
                color: '#374151',
                lineHeight: '1.8'
              }}>
                {report.ai_insights.split('\n').map((line, idx) => {
                  const trimmed = line.trim()
                  // Handle ## and ### headers
                  if (trimmed.startsWith('##')) {
                    const text = trimmed.replace(/^###+\s*/, '').replace(/^##\s*/, '')
                    const isH2 = trimmed.startsWith('## ') && !trimmed.startsWith('###')
                    return (
                      <h4 key={idx} style={{
                        fontSize: isH2 ? '18px' : '16px',
                        fontWeight: '700',
                        color: '#0C4A6E',
                        margin: isH2 ? '28px 0 14px 0' : '22px 0 10px 0',
                        paddingBottom: '8px',
                        borderBottom: isH2 ? '2px solid #0EA5E9' : '1px solid #BAE6FD',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}>
                        {text}
                      </h4>
                    )
                  }
                  // Bold standalone line
                  if (trimmed.startsWith('**') && trimmed.endsWith('**') && !trimmed.includes('**:')) {
                    const text = trimmed.replace(/\*\*/g, '')
                    return (
                      <div key={idx} style={{ margin: '12px 0 6px 0', fontWeight: '700', color: '#111827', fontSize: '15px' }}>
                        {text}
                      </div>
                    )
                  }
                  // Bullet points (- or *)
                  if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                    const text = trimmed.replace(/^[-*]\s+/, '')
                    return (
                      <div key={idx} style={{ margin: '5px 0 5px 24px', color: '#374151', display: 'flex', gap: '8px' }}>
                        <span style={{ color: '#0EA5E9', fontWeight: '700', flexShrink: 0 }}>•</span>
                        <span>{text.split(/(\*\*.+?\*\*)/).map((part, pidx) => {
                          if (part.startsWith('**') && part.endsWith('**')) {
                            return <strong key={pidx} style={{ fontWeight: '700', color: '#111827' }}>{part.replace(/\*\*/g, '')}</strong>
                          }
                          return <span key={pidx}>{part}</span>
                        })}</span>
                      </div>
                    )
                  }
                  // Sub-bullets (  - or   *)
                  if (line.match(/^\s{2,}[-*]\s+/)) {
                    const text = trimmed.replace(/^[-*]\s+/, '')
                    return (
                      <div key={idx} style={{ margin: '3px 0 3px 48px', color: '#6B7280', display: 'flex', gap: '8px', fontSize: '13px' }}>
                        <span style={{ color: '#94A3B8', fontWeight: '700', flexShrink: 0 }}>◦</span>
                        <span>{text.split(/(\*\*.+?\*\*)/).map((part, pidx) => {
                          if (part.startsWith('**') && part.endsWith('**')) {
                            return <strong key={pidx} style={{ fontWeight: '600', color: '#374151' }}>{part.replace(/\*\*/g, '')}</strong>
                          }
                          return <span key={pidx}>{part}</span>
                        })}</span>
                      </div>
                    )
                  }
                  // Numbered list items
                  if (trimmed.match(/^\d+\.\s+/)) {
                    const match = trimmed.match(/^(\d+\.)\s+(.+)$/)
                    if (match) {
                      const num = match[1]
                      const text = match[2]
                      return (
                        <div key={idx} style={{ margin: '6px 0 6px 24px', color: '#374151', display: 'flex', gap: '8px' }}>
                          <span style={{ color: '#0EA5E9', fontWeight: '700', minWidth: '24px', flexShrink: 0 }}>{num}</span>
                          <span>{text.split(/(\*\*.+?\*\*)/).map((part, pidx) => {
                            if (part.startsWith('**') && part.endsWith('**')) {
                              return <strong key={pidx} style={{ fontWeight: '700', color: '#111827' }}>{part.replace(/\*\*/g, '')}</strong>
                            }
                            return <span key={pidx}>{part}</span>
                          })}</span>
                        </div>
                      )
                    }
                  }
                  // Horizontal rule
                  if (trimmed === '---' || trimmed === '***') {
                    return <hr key={idx} style={{ border: 'none', borderTop: '1px solid #E5E7EB', margin: '16px 0' }} />
                  }
                  // Regular paragraph
                  if (trimmed.length > 0) {
                    return (
                      <p key={idx} style={{ margin: '8px 0', color: '#374151', lineHeight: '1.7' }}>
                        {trimmed.split(/(\*\*.+?\*\*)/).map((part, pidx) => {
                          if (part.startsWith('**') && part.endsWith('**')) {
                            return <strong key={pidx} style={{ fontWeight: '700', color: '#111827' }}>{part.replace(/\*\*/g, '')}</strong>
                          }
                          return <span key={pidx}>{part}</span>
                        })}
                      </p>
                    )
                  }
                  return null // skip empty lines instead of <br>
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Optimization View */}
      {activeView === 'optimization' && report.optimization_recommendations && (
        <div>
          <div style={{
            padding: '20px',
            background: '#F9FAFB',
            borderRadius: '12px',
            marginBottom: '24px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <div style={{ fontSize: '14px', color: '#6B7280', marginBottom: '4px' }}>Category</div>
                <div style={{ fontSize: '18px', fontWeight: '700', color: '#111827' }}>
                  {report.optimization_recommendations.category}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '14px', color: '#6B7280', marginBottom: '4px' }}>Total Recommendations</div>
                <div style={{ fontSize: '18px', fontWeight: '700', color: '#111827' }}>
                  {report.optimization_recommendations.total_recommendations}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '14px', color: '#6B7280', marginBottom: '4px' }}>Expected Revenue Impact</div>
                <div style={{ fontSize: '18px', fontWeight: '700', color: '#111827' }}>
                  {report.optimization_recommendations.summary.total_revenue_impact_pct.toFixed(1)}%
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {report.optimization_recommendations.recommendations.map((rec, idx) => (
              <div
                key={idx}
                style={{
                  padding: '20px',
                  background: '#FFFFFF',
                  borderRadius: '12px',
                  border: '2px solid #E5E7EB',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#DC143C'
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(220, 20, 60, 0.1)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#E5E7EB'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#111827', marginBottom: '4px' }}>
                      {rec.product_name}
                    </div>
                    <div style={{ fontSize: '12px', color: '#6B7280' }}>
                      {rec.sku} • {rec.category}
                    </div>
                  </div>
                  <div style={{
                    padding: '6px 12px',
                    background: getActionColor(rec.recommendation),
                    color: 'white',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: '700'
                  }}>
                    {rec.recommendation.replace('_', ' ')}
                  </div>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '16px', marginTop: '16px' }}>
                  <div>
                    <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Current Price</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#111827' }}>
                      {formatCurrency(rec.current_price)}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Recommended Price</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#111827' }}>
                      {formatCurrency(rec.recommended_price)}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Price Change</div>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: rec.price_change >= 0 ? '#10B981' : '#EF4444'
                    }}>
                      {rec.price_change >= 0 ? '+' : ''}{formatCurrency(rec.price_change)} ({rec.price_change_pct >= 0 ? '+' : ''}{rec.price_change_pct.toFixed(1)}%)
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Revenue Impact</div>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: rec.expected_revenue_change_pct >= 0 ? '#10B981' : '#EF4444'
                    }}>
                      {rec.expected_revenue_change_pct >= 0 ? '+' : ''}{rec.expected_revenue_change_pct.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Margin Impact</div>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: rec.expected_margin_change_pct >= 0 ? '#10B981' : '#EF4444'
                    }}>
                      {rec.expected_margin_change_pct >= 0 ? '+' : ''}{rec.expected_margin_change_pct.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Priority Score</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#111827' }}>
                      {rec.priority_score}
                    </div>
                  </div>
                </div>
                
                <div style={{
                  marginTop: '12px',
                  padding: '12px',
                  background: '#F9FAFB',
                  borderRadius: '8px',
                  fontSize: '13px',
                  color: '#6B7280'
                }}>
                  {rec.reason}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Price Range View */}
      {activeView === 'price_range' && (
        report.price_range ? (
        <div>
          <div style={{
            padding: '24px',
            background: 'linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%)',
            borderRadius: '12px',
            marginBottom: '24px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '20px', fontWeight: '700', margin: '0 0 4px 0', color: '#111827' }}>
              {report.price_range.product_name}
            </h3>
                <div style={{ fontSize: '13px', color: '#6B7280' }}>{report.price_range.sku} • {report.price_range.category}</div>
              </div>
              <button onClick={() => { setSelectedSku(''); setReport(prev => prev ? { ...prev, price_range: undefined, related_products: undefined } : prev) }}
                style={{ padding: '8px 16px', background: 'transparent', border: '1px solid #E5E7EB', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', color: '#6B7280', fontWeight: '500' }}>
                ← All Products
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Current Price</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#111827' }}>
                  {formatCurrency(report.price_range.current_price)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Cost Price</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#6B7280' }}>
                  {formatCurrency(report.price_range.cost_price)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Optimal Price</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#10B981' }}>
                  {formatCurrency(report.price_range.price_range.optimal_price)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Competitor Price</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#F59E0B' }}>
                  {formatCurrency(report.price_range.competitor_price)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Current Margin</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#111827' }}>
                  {report.price_range.current_margin_percent.toFixed(1)}%
                </div>
              </div>
            </div>
          </div>

          {/* Price Range Visual Bar */}
          <div style={{
            padding: '24px',
            background: '#FFFFFF',
            borderRadius: '12px',
            border: '2px solid #E5E7EB',
            marginBottom: '24px'
          }}>
            <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '20px', color: '#111827' }}>
              📊 Price Positioning
            </h3>
            <div style={{ position: 'relative', height: '60px', background: 'linear-gradient(90deg, #FEE2E2 0%, #FEF3C7 30%, #D1FAE5 50%, #FEF3C7 70%, #DBEAFE 100%)', borderRadius: '8px', marginBottom: '16px' }}>
              <div style={{ position: 'absolute', bottom: '-24px', left: '0', fontSize: '11px', color: '#EF4444', fontWeight: '600' }}>Min: {formatCurrency(report.price_range.price_range.min_price)}</div>
              <div style={{ position: 'absolute', bottom: '-24px', left: '50%', transform: 'translateX(-50%)', fontSize: '11px', color: '#10B981', fontWeight: '600' }}>Optimal: {formatCurrency(report.price_range.price_range.optimal_price)}</div>
              <div style={{ position: 'absolute', bottom: '-24px', right: '0', fontSize: '11px', color: '#3B82F6', fontWeight: '600' }}>Max: {formatCurrency(report.price_range.price_range.max_price)}</div>
              {/* Current price marker */}
              {(() => {
                const min = report.price_range.price_range.min_price
                const max = report.price_range.price_range.max_price
                const cur = report.price_range.current_price
                const pct = Math.max(5, Math.min(95, ((cur - min) / (max - min)) * 100))
                return (
                  <div style={{ position: 'absolute', left: `${pct}%`, top: '0', bottom: '0', display: 'flex', flexDirection: 'column', alignItems: 'center', transform: 'translateX(-50%)' }}>
                    <div style={{ fontSize: '11px', fontWeight: '700', color: '#DC143C', whiteSpace: 'nowrap', marginBottom: '4px' }}>You: {formatCurrency(cur)}</div>
                    <div style={{ width: '3px', flex: 1, background: '#DC143C', borderRadius: '2px' }} />
              </div>
                )
              })()}
              </div>
                  </div>

          {/* Recommendation */}
                  <div style={{
            padding: '20px',
            background: getActionColor(report.price_range.recommendation.action) + '15',
            borderRadius: '12px',
            border: `2px solid ${getActionColor(report.price_range.recommendation.action)}`,
            marginBottom: '24px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <div style={{ fontSize: '16px', fontWeight: '700', color: getActionColor(report.price_range.recommendation.action), marginBottom: '4px' }}>
                  💡 {report.price_range.recommendation.action.replace(/_/g, ' ')}
                  </div>
                <div style={{ fontSize: '14px', color: '#374151' }}>{report.price_range.recommendation.reason}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '12px', color: '#6B7280' }}>Suggested Price</div>
                <div style={{ fontSize: '22px', fontWeight: '800', color: '#111827' }}>{formatCurrency(report.price_range.recommendation.suggested_price)}</div>
                <div style={{ fontSize: '14px', fontWeight: '600', color: report.price_range.recommendation.price_change >= 0 ? '#10B981' : '#EF4444' }}>
                  {report.price_range.recommendation.price_change >= 0 ? '+' : ''}{formatCurrency(report.price_range.recommendation.price_change)} ({report.price_range.recommendation.price_change_percent >= 0 ? '+' : ''}{report.price_range.recommendation.price_change_percent.toFixed(1)}%)
                </div>
              </div>
            </div>
          </div>

          {/* Related Products in Same Category */}
          {report.related_products && report.related_products.length > 0 && (
          <div style={{
            padding: '20px',
            background: '#F9FAFB',
            borderRadius: '12px'
          }}>
            <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: '#111827' }}>
                📦 Related Products in Same Category
            </h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #E5E7EB' }}>
                      <th style={{ textAlign: 'left', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Product</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Current</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Optimal</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Competitor</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Margin</th>
                      <th style={{ textAlign: 'center', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.related_products.map((rp, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid #F3F4F6', cursor: 'pointer' }}
                        onClick={() => { setSelectedSku(rp.sku); fetchPricingIntelligence('price_range', rp.sku, undefined) }}
                        onMouseEnter={e => { e.currentTarget.style.background = '#F0F9FF' }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                      >
                        <td style={{ padding: '10px 12px' }}>
                          <div style={{ fontWeight: '600', color: '#111827' }}>{rp.product_name}</div>
                          <div style={{ fontSize: '11px', color: '#9CA3AF' }}>{rp.sku}</div>
                        </td>
                        <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: '600', color: '#111827' }}>{formatCurrency(rp.current_price)}</td>
                        <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: '600', color: '#10B981' }}>{formatCurrency(rp.optimal_price)}</td>
                        <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: '600', color: '#F59E0B' }}>{formatCurrency(rp.competitor_price)}</td>
                        <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: '600' }}>{rp.current_margin_percent.toFixed(1)}%</td>
                        <td style={{ textAlign: 'center', padding: '10px 12px' }}>
                          <span style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '700', color: 'white', background: getActionColor(rp.action) }}>
                            {rp.action.replace(/_/g, ' ')}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>💡 Click on any product to view its detailed price range analysis</div>
              </div>
          )}
                </div>
        ) : (
          <div style={{ padding: '20px', background: '#F9FAFB', borderRadius: '12px' }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#6B7280' }}>Fetching price data...</div>
            ) : (report?.optimization_recommendations?.recommendations?.length ?? 0) > 0 ? (
              <>
                <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '6px', color: '#111827' }}>💰 Select a Product to View Price Range</h3>
                <p style={{ fontSize: '13px', color: '#6B7280', marginBottom: '16px' }}>Click any product to load its detailed price range analysis.</p>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid #E5E7EB' }}>
                        <th style={{ textAlign: 'left', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Product</th>
                        <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Current</th>
                        <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Recommended</th>
                        <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Margin</th>
                        <th style={{ textAlign: 'center', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.optimization_recommendations!.recommendations.slice(0, 30).map((rec, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid #F3F4F6', cursor: 'pointer' }}
                          onClick={() => { setSelectedSku(rec.sku); fetchPricingIntelligence('price_range', rec.sku, undefined) }}
                          onMouseEnter={e => { e.currentTarget.style.background = '#F0F9FF' }}
                          onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                        >
                          <td style={{ padding: '10px 12px' }}>
                            <div style={{ fontWeight: '600', color: '#111827' }}>{rec.product_name}</div>
                            <div style={{ fontSize: '11px', color: '#9CA3AF' }}>{rec.sku} • {rec.category}</div>
                          </td>
                          <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: '600', color: '#111827' }}>{formatCurrency(rec.current_price)}</td>
                          <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: '600', color: '#10B981' }}>{formatCurrency(rec.recommended_price)}</td>
                          <td style={{ textAlign: 'right', padding: '10px 12px', fontWeight: '600' }}>{rec.current_margin.toFixed(1)}%</td>
                          <td style={{ textAlign: 'center', padding: '10px 12px' }}>
                            <span style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '700', color: 'white', background: getActionColor(rec.recommendation) }}>
                              {rec.recommendation.replace(/_/g, ' ')}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>💡 Showing top 30 products by priority — click any row to load detailed price range</div>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px', color: '#6B7280' }}>No product data available.</div>
            )}
          </div>
        )
      )}

      {/* Competitor Comparison View */}
      {activeView === 'competitor' && (
        report.competitor_comparison ? (
        <div>
          {/* Summary Header */}
          <div style={{
            padding: '24px',
            background: 'linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%)',
            borderRadius: '12px',
            marginBottom: '24px'
          }}>
            {report.competitor_comparison.product_name && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '16px' }}>
                <div>
                  <h3 style={{ fontSize: '20px', fontWeight: '700', margin: '0 0 4px 0', color: '#111827' }}>
                    {report.competitor_comparison.product_name}
                  </h3>
                  <div style={{ fontSize: '13px', color: '#6B7280' }}>{report.competitor_comparison.sku} • {report.competitor_comparison.category}</div>
                </div>
                <button onClick={() => { setSelectedSku(''); setReport(prev => prev ? { ...prev, competitor_comparison: undefined } : prev) }}
                  style={{ padding: '8px 16px', background: 'transparent', border: '1px solid #E5E7EB', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', color: '#6B7280', fontWeight: '500', flexShrink: 0 }}>
                  ← All Products
                </button>
              </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '16px' }}>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>HeartKart Price</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#DC143C' }}>
                  {formatCurrency(report.competitor_comparison.our_price)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Market Average</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#111827' }}>
                  {formatCurrency(report.competitor_comparison.avg_competitor_price)}
                </div>
              </div>
              {report.competitor_comparison.lowest_competitor_price && (
              <div>
                  <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Lowest Competitor</div>
                  <div style={{ fontSize: '24px', fontWeight: '800', color: '#10B981' }}>
                    {formatCurrency(report.competitor_comparison.lowest_competitor_price)}
                </div>
              </div>
              )}
              {report.competitor_comparison.highest_competitor_price && (
              <div>
                  <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Highest Competitor</div>
                  <div style={{ fontSize: '24px', fontWeight: '800', color: '#6B7280' }}>
                    {formatCurrency(report.competitor_comparison.highest_competitor_price)}
                  </div>
                </div>
              )}
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Market Position</div>
                <div style={{
                  fontSize: '20px',
                  fontWeight: '800',
                  color: getCompetitivenessColor(report.competitor_comparison.competitiveness)
                }}>
                  {report.competitor_comparison.competitiveness}
                </div>
              </div>
            </div>
            {report.competitor_comparison.market_insight && (
              <div style={{ marginTop: '16px', padding: '12px 16px', background: 'rgba(255,255,255,0.7)', borderRadius: '8px', fontSize: '14px', color: '#374151', lineHeight: '1.5' }}>
                💡 {report.competitor_comparison.market_insight}
              </div>
            )}
          </div>

          {/* Per-Platform Competitor Breakdown */}
          {report.competitor_comparison.competitors && report.competitor_comparison.competitors.length > 0 && (
            <div style={{
              padding: '20px',
              background: '#FFFFFF',
              borderRadius: '12px',
              border: '2px solid #E5E7EB',
              marginBottom: '24px'
            }}>
              <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: '#111827' }}>
                🏪 Platform-wise Price Comparison
              </h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #E5E7EB' }}>
                      <th style={{ textAlign: 'left', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Platform</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Price</th>
                      <th style={{ textAlign: 'right', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>vs HeartKart</th>
                      <th style={{ textAlign: 'center', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Stock</th>
                      <th style={{ textAlign: 'center', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Rating</th>
                      <th style={{ textAlign: 'center', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Delivery</th>
                      <th style={{ textAlign: 'center', padding: '10px 12px', color: '#6B7280', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>30d Trend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* HeartKart row first */}
                    <tr style={{ borderBottom: '1px solid #F3F4F6', background: '#FEF2F2' }}>
                      <td style={{ padding: '12px', fontWeight: '700', color: '#DC143C' }}>❤️ HeartKart</td>
                      <td style={{ textAlign: 'right', padding: '12px', fontWeight: '700', color: '#DC143C', fontSize: '16px' }}>{formatCurrency(report.competitor_comparison.our_price)}</td>
                      <td style={{ textAlign: 'right', padding: '12px', color: '#6B7280' }}>—</td>
                      <td style={{ textAlign: 'center', padding: '12px' }}><span style={{ color: '#10B981', fontWeight: '600' }}>✓ In Stock</span></td>
                      <td style={{ textAlign: 'center', padding: '12px', fontWeight: '600' }}>⭐ 4.5</td>
                      <td style={{ textAlign: 'center', padding: '12px', color: '#6B7280' }}>1-2 days</td>
                      <td style={{ textAlign: 'center', padding: '12px' }}>—</td>
                    </tr>
                    {report.competitor_comparison.competitors.map((comp, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid #F3F4F6' }}
                        onMouseEnter={e => { e.currentTarget.style.background = '#F9FAFB' }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                      >
                        <td style={{ padding: '12px', fontWeight: '600', color: '#111827' }}>{comp.platform}</td>
                        <td style={{ textAlign: 'right', padding: '12px', fontWeight: '700', color: '#111827', fontSize: '15px' }}>{formatCurrency(comp.price)}</td>
                        <td style={{ textAlign: 'right', padding: '12px' }}>
                          <span style={{
                            fontWeight: '600',
                            color: comp.price_difference > 0 ? '#10B981' : comp.price_difference < 0 ? '#EF4444' : '#6B7280'
                          }}>
                            {comp.price_difference > 0 ? `+${formatCurrency(comp.price_difference)}` : comp.price_difference < 0 ? formatCurrency(comp.price_difference) : '—'}
                          </span>
                          {comp.price_difference !== 0 && (
                            <span style={{ fontSize: '11px', color: '#9CA3AF', display: 'block' }}>
                              ({comp.price_difference_pct > 0 ? '+' : ''}{comp.price_difference_pct}%)
                            </span>
                          )}
                        </td>
                        <td style={{ textAlign: 'center', padding: '12px' }}>
                          {comp.in_stock
                            ? <span style={{ color: '#10B981', fontWeight: '600' }}>✓ In Stock</span>
                            : <span style={{ color: '#EF4444', fontWeight: '600' }}>✗ Out</span>
                          }
                        </td>
                        <td style={{ textAlign: 'center', padding: '12px', fontWeight: '600' }}>⭐ {comp.rating}</td>
                        <td style={{ textAlign: 'center', padding: '12px', color: '#6B7280', fontSize: '13px' }}>{comp.delivery}</td>
                        <td style={{ textAlign: 'center', padding: '12px' }}>
                          <span style={{
                            fontWeight: '600',
                            color: comp.price_trend === 'UP' ? '#EF4444' : comp.price_trend === 'DOWN' ? '#10B981' : '#6B7280',
                            fontSize: '13px'
                          }}>
                            {comp.price_trend === 'UP' ? '📈' : comp.price_trend === 'DOWN' ? '📉' : '➡️'} {comp.price_trend} {comp.price_trend_pct !== 0 ? `(${comp.price_trend_pct > 0 ? '+' : ''}${comp.price_trend_pct}%)` : ''}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Category-wide comparison */}
          {report.competitor_comparison.category_products && report.competitor_comparison.category_products.length > 0 && (
            <div style={{
              padding: '20px',
              background: '#F9FAFB',
              borderRadius: '12px'
            }}>
              <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: '#111827' }}>
                📦 Other Products in {report.competitor_comparison.category || 'Category'}
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {report.competitor_comparison.category_products.map((prod, idx) => (
                  <div key={idx} style={{
                    padding: '14px 16px',
                      background: '#FFFFFF',
                    borderRadius: '10px',
                    border: '1px solid #E5E7EB',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '8px',
                    cursor: 'pointer'
                  }}
                    onClick={() => { setSelectedSku(prod.sku); fetchPricingIntelligence('competitor_comparison', prod.sku, undefined) }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = '#DC143C' }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = '#E5E7EB' }}
                  >
                      <div>
                      <div style={{ fontWeight: '600', color: '#111827', fontSize: '14px' }}>{prod.name}</div>
                      <div style={{ fontSize: '11px', color: '#9CA3AF' }}>{prod.sku}</div>
                        </div>
                    <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '11px', color: '#6B7280' }}>HeartKart</div>
                        <div style={{ fontWeight: '700', color: '#111827' }}>{formatCurrency(prod.our_price)}</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '11px', color: '#6B7280' }}>Market Avg</div>
                        <div style={{ fontWeight: '700', color: '#6B7280' }}>{formatCurrency(prod.avg_competitor_price)}</div>
                        </div>
                      <span style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '11px',
                          fontWeight: '700',
                        color: 'white',
                        background: getCompetitivenessColor(prod.competitiveness)
                        }}>
                        {prod.competitiveness}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>💡 Click on any product for detailed competitor analysis</div>
            </div>
          )}
        </div>
        ) : (
          <div style={{ padding: '20px', background: '#F9FAFB', borderRadius: '12px' }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#6B7280' }}>Fetching competitor data...</div>
            ) : (report?.optimization_recommendations?.recommendations?.length ?? 0) > 0 ? (
              <>
                <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '6px', color: '#111827' }}>⚔️ Select a Product for Competitor Analysis</h3>
                <p style={{ fontSize: '13px', color: '#6B7280', marginBottom: '16px' }}>Click any product to see how HeartKart is positioned against competitors.</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {report.optimization_recommendations!.recommendations.slice(0, 30).map((rec, idx) => (
                    <div key={idx} style={{
                      padding: '14px 16px',
                      background: '#FFFFFF',
                      borderRadius: '10px',
                      border: '1px solid #E5E7EB',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '8px',
                      cursor: 'pointer',
                    }}
                      onClick={() => { setSelectedSku(rec.sku); fetchPricingIntelligence('competitor_comparison', rec.sku, undefined) }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = '#DC143C' }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = '#E5E7EB' }}
                    >
                      <div>
                        <div style={{ fontWeight: '600', color: '#111827', fontSize: '14px' }}>{rec.product_name}</div>
                        <div style={{ fontSize: '11px', color: '#9CA3AF' }}>{rec.sku} • {rec.category}</div>
                      </div>
                      <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '11px', color: '#6B7280' }}>HeartKart</div>
                          <div style={{ fontWeight: '700', color: '#111827' }}>{formatCurrency(rec.current_price)}</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '11px', color: '#6B7280' }}>Change</div>
                          <div style={{ fontWeight: '700', color: rec.price_change_pct >= 0 ? '#10B981' : '#EF4444' }}>
                            {rec.price_change_pct >= 0 ? '+' : ''}{rec.price_change_pct.toFixed(1)}%
                          </div>
                        </div>
                        <span style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '700', color: 'white', background: getCompetitivenessColor(rec.competitiveness) }}>
                          {rec.competitiveness}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>💡 Showing top 30 products — click any to see platform-by-platform competitor breakdown</div>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px', color: '#6B7280' }}>No product data available.</div>
            )}
          </div>
        )
      )}

      {/* Demand Impact View */}
      {activeView === 'demand' && (
        report.demand_impact ? (
        <div>
          {/* Product Header */}
          <div style={{
            padding: '24px',
            background: 'linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%)',
            borderRadius: '12px',
            marginBottom: '24px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '20px', fontWeight: '700', margin: '0 0 4px 0', color: '#111827' }}>
              {report.demand_impact.product_name}
            </h3>
                <div style={{ fontSize: '13px', color: '#6B7280' }}>
                  {report.demand_impact.sku} • {report.demand_impact.category || 'N/A'}
                  {report.demand_impact.price_segment && ` • ${report.demand_impact.price_segment} Segment`}
                  {report.demand_impact.elasticity && ` • Elasticity: ${report.demand_impact.elasticity}`}
                </div>
              </div>
              <button onClick={() => { setSelectedSku(''); setReport(prev => prev ? { ...prev, demand_impact: undefined, demand_products: undefined } : prev) }}
                style={{ padding: '8px 16px', background: 'transparent', border: '1px solid #E5E7EB', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', color: '#6B7280', fontWeight: '500', flexShrink: 0 }}>
                ← All Products
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '16px' }}>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Current Price</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#111827' }}>
                  {formatCurrency(report.demand_impact.current_price)}
                </div>
              </div>
              {report.demand_impact.cost_price && (
              <div>
                  <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Cost Price</div>
                  <div style={{ fontSize: '24px', fontWeight: '800', color: '#6B7280' }}>
                    {formatCurrency(report.demand_impact.cost_price)}
                  </div>
                </div>
              )}
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Recommended Price</div>
                <div style={{ fontSize: '24px', fontWeight: '800', color: '#10B981' }}>
                  {formatCurrency(report.demand_impact.new_price)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '4px' }}>Price Change</div>
                <div style={{
                  fontSize: '24px',
                  fontWeight: '800',
                  color: report.demand_impact.price_change_pct >= 0 ? '#EF4444' : '#10B981'
                }}>
                  {report.demand_impact.price_change_pct >= 0 ? '+' : ''}{report.demand_impact.price_change_pct.toFixed(1)}%
                </div>
              </div>
            </div>
          </div>

          {/* Impact Summary Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px', marginBottom: '24px' }}>
            <div style={{ padding: '20px', background: '#FFFFFF', borderRadius: '12px', border: '2px solid #E5E7EB' }}>
              <h4 style={{ fontSize: '15px', fontWeight: '700', marginBottom: '14px', color: '#111827' }}>📊 Demand Impact</h4>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>Current Velocity</span>
                <span style={{ fontWeight: '700' }}>{report.demand_impact.demand_impact.current_velocity.toFixed(2)} units/day</span>
                  </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>Expected Velocity</span>
                <span style={{ fontWeight: '700' }}>{report.demand_impact.demand_impact.expected_velocity.toFixed(2)} units/day</span>
                </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid #F3F4F6' }}>
                <span style={{ fontSize: '13px', fontWeight: '600', color: '#6B7280' }}>Change</span>
                <span style={{ fontWeight: '700', color: report.demand_impact.demand_impact.demand_change_pct >= 0 ? '#10B981' : '#EF4444' }}>
                    {report.demand_impact.demand_impact.demand_change_pct >= 0 ? '+' : ''}{report.demand_impact.demand_impact.demand_change_pct.toFixed(1)}%
                </span>
              </div>
            </div>

            <div style={{ padding: '20px', background: '#FFFFFF', borderRadius: '12px', border: '2px solid #E5E7EB' }}>
              <h4 style={{ fontSize: '15px', fontWeight: '700', marginBottom: '14px', color: '#111827' }}>💰 Revenue Impact</h4>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>Current Revenue</span>
                <span style={{ fontWeight: '700' }}>{formatCurrency(report.demand_impact.revenue_impact.current_revenue)}/day</span>
                  </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>Expected Revenue</span>
                <span style={{ fontWeight: '700' }}>{formatCurrency(report.demand_impact.revenue_impact.expected_revenue)}/day</span>
                </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid #F3F4F6' }}>
                <span style={{ fontSize: '13px', fontWeight: '600', color: '#6B7280' }}>Change</span>
                <span style={{ fontWeight: '700', color: report.demand_impact.revenue_impact.revenue_change >= 0 ? '#10B981' : '#EF4444' }}>
                  {report.demand_impact.revenue_impact.revenue_change >= 0 ? '+' : ''}{formatCurrency(report.demand_impact.revenue_impact.revenue_change)} ({report.demand_impact.revenue_impact.revenue_change_pct >= 0 ? '+' : ''}{report.demand_impact.revenue_impact.revenue_change_pct.toFixed(1)}%)
                </span>
                  </div>
                </div>

            <div style={{ padding: '20px', background: '#FFFFFF', borderRadius: '12px', border: '2px solid #E5E7EB' }}>
              <h4 style={{ fontSize: '15px', fontWeight: '700', marginBottom: '14px', color: '#111827' }}>📈 Margin Impact</h4>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>Current Margin</span>
                <span style={{ fontWeight: '700' }}>{formatCurrency(report.demand_impact.margin_impact.current_margin)}/day</span>
                  </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>Expected Margin</span>
                <span style={{ fontWeight: '700' }}>{formatCurrency(report.demand_impact.margin_impact.expected_margin)}/day</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid #F3F4F6' }}>
                <span style={{ fontSize: '13px', fontWeight: '600', color: '#6B7280' }}>Change</span>
                <span style={{ fontWeight: '700', color: report.demand_impact.margin_impact.margin_change >= 0 ? '#10B981' : '#EF4444' }}>
                  {report.demand_impact.margin_impact.margin_change >= 0 ? '+' : ''}{formatCurrency(report.demand_impact.margin_impact.margin_change)} ({report.demand_impact.margin_impact.margin_change_pct >= 0 ? '+' : ''}{report.demand_impact.margin_impact.margin_change_pct.toFixed(1)}%)
                </span>
                </div>
              </div>
            </div>

          {/* Price Scenarios Table */}
          {report.demand_impact.scenarios && report.demand_impact.scenarios.length > 0 && (
            <div style={{
              padding: '20px',
              background: '#FFFFFF',
              borderRadius: '12px',
              border: '2px solid #E5E7EB',
              marginBottom: '24px'
            }}>
              <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '4px', color: '#111827' }}>
                🔬 Price Sensitivity Scenarios
              </h3>
              <p style={{ fontSize: '13px', color: '#6B7280', margin: '0 0 16px 0' }}>
                What happens at different price points? Based on price elasticity of {report.demand_impact.elasticity} for the {report.demand_impact.price_segment || 'current'} segment.
              </p>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #E5E7EB' }}>
                      <th style={{ textAlign: 'center', padding: '10px 8px', color: '#6B7280', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>Scenario</th>
                      <th style={{ textAlign: 'right', padding: '10px 8px', color: '#6B7280', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>Price</th>
                      <th style={{ textAlign: 'right', padding: '10px 8px', color: '#6B7280', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>Demand</th>
                      <th style={{ textAlign: 'right', padding: '10px 8px', color: '#6B7280', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>Revenue/day</th>
                      <th style={{ textAlign: 'right', padding: '10px 8px', color: '#6B7280', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>Revenue Δ</th>
                      <th style={{ textAlign: 'right', padding: '10px 8px', color: '#6B7280', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>Margin/day</th>
                      <th style={{ textAlign: 'right', padding: '10px 8px', color: '#6B7280', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>Margin Δ</th>
                      <th style={{ textAlign: 'center', padding: '10px 8px', color: '#6B7280', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>Signal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.demand_impact.scenarios.map((sc, idx) => {
                      const recColor = sc.recommendation === 'STRONGLY_RECOMMEND' ? '#10B981'
                        : sc.recommendation === 'RECOMMEND' ? '#3B82F6'
                        : sc.recommendation === 'CONSIDER' ? '#F59E0B'
                        : '#EF4444'
                      return (
                        <tr key={idx} style={{
                          borderBottom: '1px solid #F3F4F6',
                          background: sc.is_current ? '#FEF3C7' : 'transparent',
                          fontWeight: sc.is_current ? '700' : '400'
                        }}>
                          <td style={{ textAlign: 'center', padding: '10px 8px', fontWeight: '700', color: sc.is_current ? '#D97706' : '#111827' }}>
                            {sc.label}
                          </td>
                          <td style={{ textAlign: 'right', padding: '10px 8px', fontWeight: '600' }}>{formatCurrency(sc.new_price)}</td>
                          <td style={{ textAlign: 'right', padding: '10px 8px' }}>
                            {sc.expected_velocity.toFixed(2)}
                            {!sc.is_current && <span style={{ fontSize: '11px', color: sc.demand_change_pct >= 0 ? '#10B981' : '#EF4444', marginLeft: '4px' }}>({sc.demand_change_pct >= 0 ? '+' : ''}{sc.demand_change_pct}%)</span>}
                          </td>
                          <td style={{ textAlign: 'right', padding: '10px 8px', fontWeight: '600' }}>{formatCurrency(sc.expected_revenue)}</td>
                          <td style={{ textAlign: 'right', padding: '10px 8px', color: sc.is_current ? '#D97706' : sc.revenue_change >= 0 ? '#10B981' : '#EF4444', fontWeight: '600' }}>
                            {sc.is_current ? '—' : `${sc.revenue_change >= 0 ? '+' : ''}${sc.revenue_change_pct}%`}
                          </td>
                          <td style={{ textAlign: 'right', padding: '10px 8px', fontWeight: '600' }}>{formatCurrency(sc.expected_margin)}</td>
                          <td style={{ textAlign: 'right', padding: '10px 8px', color: sc.is_current ? '#D97706' : sc.margin_change >= 0 ? '#10B981' : '#EF4444', fontWeight: '600' }}>
                            {sc.is_current ? '—' : `${sc.margin_change >= 0 ? '+' : ''}${sc.margin_change_pct}%`}
                          </td>
                          <td style={{ textAlign: 'center', padding: '10px 8px' }}>
                            {sc.is_current ? (
                              <span style={{ fontSize: '11px', fontWeight: '700', color: '#D97706' }}>CURRENT</span>
                            ) : (
                              <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '10px', fontWeight: '700', color: 'white', background: recColor }}>
                                {sc.recommendation.replace('_', ' ')}
                              </span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                  </div>
                </div>
          )}

          {/* Best Scenarios Callout */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px', marginBottom: '24px' }}>
            {report.demand_impact.best_revenue_scenario && (
              <div style={{ padding: '16px', background: '#F0FDF4', borderRadius: '12px', border: '2px solid #10B981' }}>
                <div style={{ fontSize: '13px', fontWeight: '600', color: '#10B981', marginBottom: '8px' }}>🏆 Best Revenue Scenario</div>
                <div style={{ fontSize: '18px', fontWeight: '800', color: '#111827' }}>{formatCurrency(report.demand_impact.best_revenue_scenario.new_price)}</div>
                <div style={{ fontSize: '13px', color: '#374151', marginTop: '4px' }}>
                  Revenue: {report.demand_impact.best_revenue_scenario.revenue_change >= 0 ? '+' : ''}{formatCurrency(report.demand_impact.best_revenue_scenario.revenue_change)}/day ({report.demand_impact.best_revenue_scenario.revenue_change_pct >= 0 ? '+' : ''}{report.demand_impact.best_revenue_scenario.revenue_change_pct}%)
                  </div>
                </div>
            )}
            {report.demand_impact.best_margin_scenario && (
              <div style={{ padding: '16px', background: '#EFF6FF', borderRadius: '12px', border: '2px solid #3B82F6' }}>
                <div style={{ fontSize: '13px', fontWeight: '600', color: '#3B82F6', marginBottom: '8px' }}>💎 Best Margin Scenario</div>
                <div style={{ fontSize: '18px', fontWeight: '800', color: '#111827' }}>{formatCurrency(report.demand_impact.best_margin_scenario.new_price)}</div>
                <div style={{ fontSize: '13px', color: '#374151', marginTop: '4px' }}>
                  Margin: {report.demand_impact.best_margin_scenario.margin_change >= 0 ? '+' : ''}{formatCurrency(report.demand_impact.best_margin_scenario.margin_change)}/day ({report.demand_impact.best_margin_scenario.margin_change_pct >= 0 ? '+' : ''}{report.demand_impact.best_margin_scenario.margin_change_pct}%)
                  </div>
                </div>
            )}
          </div>

          {/* Recommendation */}
          <div style={{
            padding: '20px',
            background: getActionColor(report.demand_impact.recommendation.action) + '15',
            borderRadius: '12px',
            border: `2px solid ${getActionColor(report.demand_impact.recommendation.action)}`
          }}>
            <div style={{ fontSize: '16px', fontWeight: '700', color: getActionColor(report.demand_impact.recommendation.action), marginBottom: '6px' }}>
              💡 {report.demand_impact.recommendation.action.replace(/_/g, ' ')}
            </div>
            <div style={{ fontSize: '14px', color: '#374151' }}>
              {report.demand_impact.recommendation.reason}
            </div>
          </div>

          {/* Other Products — demand navigation */}
          {report.demand_products && report.demand_products.length > 0 && (
            <div style={{ padding: '20px', background: '#F9FAFB', borderRadius: '12px', marginTop: '24px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', color: '#111827' }}>
                📦 Analyze Other Products
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {report.demand_products.map((prod, idx) => (
                  <div key={idx} style={{
                    padding: '12px 16px',
                    background: '#FFFFFF',
                    borderRadius: '10px',
                    border: `1px solid ${prod.sku === report.demand_impact?.sku ? '#DC143C' : '#E5E7EB'}`,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '8px',
                    cursor: 'pointer',
                  }}
                    onClick={() => { setSelectedSku(prod.sku); fetchPricingIntelligence('demand_impact', prod.sku, undefined) }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = '#DC143C' }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = prod.sku === report.demand_impact?.sku ? '#DC143C' : '#E5E7EB' }}
                  >
                    <div>
                      <div style={{ fontWeight: '600', color: '#111827', fontSize: '14px' }}>{prod.product_name}</div>
                      <div style={{ fontSize: '11px', color: '#9CA3AF' }}>{prod.sku} • {prod.category}</div>
                    </div>
                    <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '11px', color: '#6B7280' }}>Price</div>
                        <div style={{ fontWeight: '700', color: '#111827' }}>{formatCurrency(prod.current_price)}</div>
                      </div>
                      <span style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '700', color: 'white', background: getActionColor(prod.action) }}>
                        {prod.action.replace(/_/g, ' ')}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>💡 Click any product to run demand elasticity analysis</div>
            </div>
          )}
        </div>
        ) : (
          <div style={{ padding: '20px', background: '#F9FAFB', borderRadius: '12px' }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#6B7280' }}>Running demand elasticity model...</div>
            ) : (report?.optimization_recommendations?.recommendations?.length ?? 0) > 0 ? (
              <>
                <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '6px', color: '#111827' }}>📈 Select a Product for Demand Analysis</h3>
                <p style={{ fontSize: '13px', color: '#6B7280', marginBottom: '16px' }}>Click any product to model how price changes will affect demand and revenue.</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {report.optimization_recommendations!.recommendations.slice(0, 30).map((rec, idx) => (
                    <div key={idx} style={{
                      padding: '14px 16px',
                      background: '#FFFFFF',
                      borderRadius: '10px',
                      border: '1px solid #E5E7EB',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '8px',
                      cursor: 'pointer',
                    }}
                      onClick={() => { setSelectedSku(rec.sku); fetchPricingIntelligence('demand_impact', rec.sku, undefined) }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = '#DC143C' }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = '#E5E7EB' }}
                    >
                      <div>
                        <div style={{ fontWeight: '600', color: '#111827', fontSize: '14px' }}>{rec.product_name}</div>
                        <div style={{ fontSize: '11px', color: '#9CA3AF' }}>{rec.sku} • {rec.category}</div>
                      </div>
                      <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '11px', color: '#6B7280' }}>Current</div>
                          <div style={{ fontWeight: '700', color: '#111827' }}>{formatCurrency(rec.current_price)}</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '11px', color: '#6B7280' }}>Recommended</div>
                          <div style={{ fontWeight: '700', color: '#10B981' }}>{formatCurrency(rec.recommended_price)}</div>
                        </div>
                        <span style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '700', color: 'white', background: getActionColor(rec.recommendation) }}>
                          {rec.recommendation.replace(/_/g, ' ')}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>💡 Showing top 30 products by priority — click any to run demand elasticity simulation</div>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px', color: '#6B7280' }}>No product data available.</div>
            )}
          </div>
        )
      )}
    </div>
  )
}
