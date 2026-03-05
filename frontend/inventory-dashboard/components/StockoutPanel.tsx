'use client'

import { useState, useEffect } from 'react'
import { getApiBaseUrl } from '../lib/apiBaseUrl'

interface Substitute {
  sku: string
  name: string
  category: string
  color: string
  price: number
  stock_quantity: number
  match_score: number
  price_difference: number
  reason: string
}

interface AtRiskProduct {
  sku: string
  name: string
  category: string
  color: string
  price: number
  current_stock: number
  sales_velocity: number
  days_until_stockout: number
  stockout_date: string
  risk_level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  substitutes: Substitute[]
  substitute_count: number
}

interface StockoutReport {
  status: string
  generated_at: string
  summary: {
    total_at_risk: number
    critical_risk: number
    high_risk: number
    products_with_substitutes: number
    substitute_coverage: number
    categories_affected: Record<string, number>
    colors_affected: Record<string, number>
  }
  ai_analysis: string
  at_risk_products: AtRiskProduct[]
}

const API_BASE_URL = getApiBaseUrl()

export default function StockoutPanel() {
  const [report, setReport] = useState<StockoutReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'all' | 'critical'>('all')
  const [selectedProduct, setSelectedProduct] = useState<AtRiskProduct | null>(null)
  const [hasLoaded, setHasLoaded] = useState(false)

  useEffect(() => {
    // Only fetch on first mount if not already loaded
    if (!hasLoaded) {
      fetchStockoutReport()
    }
  }, [])

  const fetchStockoutReport = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/api/stockout/report`)
      const data = await response.json()
      setReport(data)
      setError(null)
      setHasLoaded(true)
    } catch (err) {
      setError('Failed to load stockout report. Make sure the API is running.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'CRITICAL': return '#EF4444'
      case 'HIGH': return '#F59E0B'
      case 'MEDIUM': return '#EAB308'
      case 'LOW': return '#10B981'
      default: return '#6B7280'
    }
  }

  const getRiskEmoji = (risk: string) => {
    switch (risk) {
      case 'CRITICAL': return '🔴'
      case 'HIGH': return '🟠'
      case 'MEDIUM': return '🟡'
      case 'LOW': return '🟢'
      default: return '⚪'
    }
  }

  // Show empty state on first load
  if (!hasLoaded && !loading && !error) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '20px' }}>🎯</div>
        <div style={{ fontSize: '18px', color: '#6B7280', marginBottom: '20px' }}>
          Ready to analyze stockout risks
        </div>
        <button
          onClick={fetchStockoutReport}
          style={{
            padding: '12px 32px',
            background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
            color: 'white',
            border: 'none',
            borderRadius: '12px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '16px',
            boxShadow: '0 4px 12px rgba(245, 158, 11, 0.3)'
          }}
        >
          Analyze Risks
        </button>
      </div>
    )
  }

  if (loading) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '20px' }}>🔄</div>
        <div style={{ fontSize: '18px', color: '#6B7280' }}>Analyzing stockout risks...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '20px' }}>⚠️</div>
        <div style={{ fontSize: '18px', color: '#EF4444', marginBottom: '10px' }}>{error}</div>
        <button
          onClick={fetchStockoutReport}
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

  if (!report) return null

  // Be defensive: some reports might be missing at_risk_products.
  const summary = report.summary
  const at_risk_products = report.at_risk_products ?? []
  const displayProducts = viewMode === 'critical' 
    ? at_risk_products.filter(p => p.risk_level === 'CRITICAL')
    : at_risk_products

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
              background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
              borderRadius: '16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '28px',
              boxShadow: '0 4px 12px rgba(245, 158, 11, 0.3)'
            }}>
              🎯
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
                Stockout Sentinel
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
                <span style={{ fontSize: '13px', color: '#9CA3AF' }}>•</span>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>
                  Last updated: {new Date(report.generated_at).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
          
          {/* Refresh Button */}
          <button
            onClick={fetchStockoutReport}
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
          background: 'linear-gradient(135deg, #ffffff 0%, #fffbeb 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(245, 158, 11, 0.1)',
          transition: 'transform 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-4px)'}
        onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Products at Risk</div>
          <div style={{ fontSize: '40px', fontWeight: '800', color: '#F59E0B', lineHeight: '1' }}>
            {report.summary?.total_at_risk ?? 0}
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>items need attention</div>
        </div>

        <div style={{ 
          background: 'linear-gradient(135deg, #ffffff 0%, #fef2f2 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(239, 68, 68, 0.1)',
          transition: 'transform 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-4px)'}
        onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Critical Risk</div>
          <div style={{ fontSize: '40px', fontWeight: '800', color: '#EF4444', lineHeight: '1' }}>
            {report.summary?.critical_risk ?? 0}
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>stockout within 3 days</div>
        </div>

        <div style={{ 
          background: 'linear-gradient(135deg, #ffffff 0%, #fff7ed 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(251, 146, 60, 0.1)',
          transition: 'transform 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-4px)'}
        onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>High Risk</div>
          <div style={{ fontSize: '40px', fontWeight: '800', color: '#FB923C', lineHeight: '1' }}>
            {report.summary?.high_risk ?? 0}
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>stockout within 7 days</div>
        </div>

        <div style={{ 
          background: 'linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%)', 
          padding: '24px', 
          borderRadius: '16px', 
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid rgba(16, 185, 129, 0.1)',
          transition: 'transform 0.2s',
          cursor: 'pointer'
        }}
        onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-4px)'}
        onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}>
          <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Substitute Coverage</div>
          <div style={{ fontSize: '40px', fontWeight: '800', color: '#10B981', lineHeight: '1' }}>
            {(report.summary?.substitute_coverage ?? 0).toFixed(0)}%
          </div>
          <div style={{ fontSize: '12px', color: '#9CA3AF', marginTop: '8px' }}>
            {report.summary?.products_with_substitutes ?? 0} have alternatives
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <button
          onClick={() => setViewMode('all')}
          style={{
            padding: '12px 24px',
            background: viewMode === 'all' ? 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)' : 'white',
            color: viewMode === 'all' ? 'white' : '#374151',
            border: viewMode === 'all' ? 'none' : '2px solid #E5E7EB',
            borderRadius: '12px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '14px',
            transition: 'all 0.2s'
          }}
        >
          All At Risk ({at_risk_products.length})
        </button>

        <button
          onClick={() => setViewMode('critical')}
          style={{
            padding: '12px 24px',
            background: viewMode === 'critical' ? 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)' : 'white',
            color: viewMode === 'critical' ? 'white' : '#374151',
            border: viewMode === 'critical' ? 'none' : '2px solid #E5E7EB',
            borderRadius: '12px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '14px',
            transition: 'all 0.2s'
          }}
        >
          🔥 Critical Only ({report.summary?.critical_risk ?? 0})
        </button>

      </div>

      {/* Products Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '20px' }}>
        {displayProducts.map((product) => (
          <div
            key={product.sku}
            style={{
              background: 'white',
              borderRadius: '16px',
              padding: '20px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              border: `2px solid ${getRiskColor(product.risk_level)}20`,
              transition: 'all 0.2s',
              cursor: 'pointer'
            }}
            onClick={() => setSelectedProduct(product)}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-4px)'
              e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.12)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.08)'
            }}
          >
            {/* Risk Badge */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
              <span style={{
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: '600',
                background: `${getRiskColor(product.risk_level)}15`,
                color: getRiskColor(product.risk_level),
                border: `1.5px solid ${getRiskColor(product.risk_level)}30`
              }}>
                {getRiskEmoji(product.risk_level)} {product.risk_level}
              </span>
              <span style={{ fontSize: '12px', color: '#9CA3AF' }}>
                {product.sku}
              </span>
            </div>

            {/* Product Info */}
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: '#1F2937', margin: '0 0 8px 0' }}>
              {product.name}
            </h3>
            <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '12px' }}>
              {product.category} • {product.color} • ₹{(product.price).toFixed(2)}
            </div>

            {/* Stock Info */}
            <div style={{ 
              background: '#F9FAFB', 
              padding: '12px', 
              borderRadius: '8px',
              marginBottom: '12px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: '#6B7280' }}>Current Stock:</span>
                <span style={{ fontSize: '12px', fontWeight: '600', color: '#1F2937' }}>
                  {product.current_stock} units
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: '#6B7280' }}>Sales Velocity:</span>
                <span style={{ fontSize: '12px', fontWeight: '600', color: '#1F2937' }}>
                  {product.sales_velocity}/day
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '12px', color: '#6B7280' }}>Stockout Date:</span>
                <span style={{ fontSize: '12px', fontWeight: '600', color: getRiskColor(product.risk_level) }}>
                  {product.days_until_stockout} days ({product.stockout_date})
                </span>
              </div>
            </div>

            {/* Substitutes */}
            {product.substitute_count > 0 && (
              <div style={{
                background: 'linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)',
                padding: '12px',
                borderRadius: '8px',
                border: '1px solid #BBF7D0'
              }}>
                <div style={{ fontSize: '12px', fontWeight: '600', color: '#059669', marginBottom: '6px' }}>
                  💡 {product.substitute_count} Substitute{product.substitute_count !== 1 ? 's' : ''} Available
                </div>
                <div style={{ fontSize: '11px', color: '#047857' }}>
                  Click to view alternatives
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Substitute Modal */}
      {selectedProduct && (
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
          padding: '20px'
        }}
        onClick={() => setSelectedProduct(null)}>
          <div style={{
            background: 'white',
            borderRadius: '20px',
            padding: '32px',
            maxWidth: '800px',
            maxHeight: '80vh',
            overflow: 'auto',
            boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)'
          }}
          onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#1F2937', margin: '0 0 8px 0' }}>
              {selectedProduct.name}
            </h2>
            <p style={{ fontSize: '14px', color: '#6B7280', margin: '0 0 24px 0' }}>
              Stockout in {selectedProduct.days_until_stockout} days • {selectedProduct.substitute_count} alternatives available
            </p>

            {selectedProduct.substitutes.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {selectedProduct.substitutes.map((sub) => (
                  <div key={sub.sku} style={{
                    background: '#F9FAFB',
                    padding: '16px',
                    borderRadius: '12px',
                    border: '1px solid #E5E7EB'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '8px' }}>
                      <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#1F2937', margin: 0 }}>
                        {sub.name}
                      </h3>
                      <span style={{
                        padding: '4px 8px',
                        background: '#10B981',
                        color: 'white',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '600'
                      }}>
                        {sub.match_score}% match
                      </span>
                    </div>
                    <div style={{ fontSize: '13px', color: '#6B7280', marginBottom: '8px' }}>
                      {sub.reason}
                    </div>
                    <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
                      <span style={{ color: '#374151' }}>
                        <strong>Price:</strong>{' '}
                        {(() => {
                          const priceInr = sub.price
                          const diffInr = sub.price_difference
                          return (
                            <>
                              ₹{priceInr.toFixed(2)}
                              {sub.price_difference !== 0 && (
                                <span style={{ color: sub.price_difference < 0 ? '#10B981' : '#F59E0B', marginLeft: '4px' }}>
                                  ({sub.price_difference > 0 ? '+' : ''}₹{diffInr.toFixed(2)})
                                </span>
                              )}
                            </>
                          )
                        })()}
                      </span>
                      <span style={{ color: '#374151' }}>
                        <strong>Stock:</strong> {sub.stock_quantity} units
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px', color: '#9CA3AF' }}>
                No substitutes found for this product
              </div>
            )}

            <button
              onClick={() => setSelectedProduct(null)}
              style={{
                marginTop: '24px',
                width: '100%',
                padding: '12px',
                background: '#E5E7EB',
                color: '#374151',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: '600'
              }}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
