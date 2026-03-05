'use client';

import { useState, useEffect } from 'react';
import { getApiBaseUrl } from '../lib/apiBaseUrl';

// Add animations
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = `
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
    @keyframes scaleIn {
      from { 
        transform: scale(0);
      }
      to { 
        transform: scale(1);
      }
    }
  `;
  if (!document.head.querySelector('style[data-markdown-animations]')) {
    style.setAttribute('data-markdown-animations', 'true');
    document.head.appendChild(style);
  }
}

interface AgedProduct {
  sku: string;
  name: string;
  category: string;
  current_price: number;
  quantity: number;
  sales_velocity: number;
  days_remaining: number;
  age_category: string;
  markdown_recommendation: {
    markdown_percentage: number;
    new_price: number;
    potential_revenue: number;
    reason: string;
    urgency: string;
  };
  vendor: string;
}

interface Bundle {
  bundle_name: string;
  items: Array<{ sku: string; name: string }>;
  regular_value: number;
  bundle_price: number;
  savings: number;
  savings_percentage: number;
}

export default function MarkdownPanel() {
  const [loading, setLoading] = useState(true);
  const [agedProducts, setAgedProducts] = useState<AgedProduct[]>([]);
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [aiRecommendations, setAiRecommendations] = useState<string>('');
  const [selectedProduct, setSelectedProduct] = useState<AgedProduct | null>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [activeView, setActiveView] = useState<'products' | 'bundles' | 'timeline'>('products');
  const [showBundleSuccess, setShowBundleSuccess] = useState(false);
  const [createdBundle, setCreatedBundle] = useState<Bundle | null>(null);
  const [showMarkdownSuccess, setShowMarkdownSuccess] = useState(false);
  const [appliedProduct, setAppliedProduct] = useState<AgedProduct | null>(null);

  // Prices are stored in INR — no conversion needed
  const usdToInr = (amount: number) => {
    if (!amount || !Number.isFinite(amount)) return 0;
    return Math.round(amount * 100) / 100;
  };

  useEffect(() => {
    fetchMarkdownReport();
  }, []);

  const fetchMarkdownReport = async () => {
    setLoading(true);
    const apiBaseUrl = getApiBaseUrl();
    try {
      const response = await fetch(`${apiBaseUrl}/api/markdown/report`);
      const data = await response.json();
      
      if (data.status === 'success') {
        setAgedProducts(data.aged_products || []);
        setBundles(data.suggested_bundles || []);
        setTimeline(data.timeline || null);
        setSummary(data.summary);
        setAiRecommendations(data.ai_recommendations || '');
      }
    } catch (error) {
      console.error('Error fetching markdown report:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = () => {
    fetchMarkdownReport();
  };

  const handleCreateBundle = (bundle: Bundle) => {
    setCreatedBundle(bundle);
    setShowBundleSuccess(true);
    
    // Auto-close after 3 seconds
    setTimeout(() => {
      setShowBundleSuccess(false);
      setCreatedBundle(null);
    }, 3000);
  };

  const [applyingMarkdown, setApplyingMarkdown] = useState(false);

  const handleApplyMarkdown = async (product: AgedProduct) => {
    setApplyingMarkdown(true);
    const apiBaseUrl = getApiBaseUrl();
    try {
      const response = await fetch(`${apiBaseUrl}/api/markdown/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sku: product.sku,
          new_price: product.markdown_recommendation.new_price,
        }),
      });
      const data = await response.json();

      if (data.status === 'success') {
        // Remove product from the aged products list
        setAgedProducts(prev => prev.filter(p => p.sku !== product.sku));

        // Update summary counts
        if (summary) {
          setSummary((prev: any) => ({
            ...prev,
            total_aged_items: Math.max(0, (prev?.total_aged_items || 0) - 1),
          }));
        }

        setAppliedProduct(product);
        setShowMarkdownSuccess(true);
        setSelectedProduct(null);

        // Auto-close after 3 seconds
        setTimeout(() => {
          setShowMarkdownSuccess(false);
          setAppliedProduct(null);
        }, 3000);
      } else {
        alert(`Failed to apply markdown: ${data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error applying markdown:', error);
      alert('Failed to apply markdown. Please try again.');
    } finally {
      setApplyingMarkdown(false);
    }
  };

  const getAgeCategoryBadge = (category: string) => {
    const styles: any = {
      DEAD_STOCK: { bg: '#FEE2E2', color: '#991B1B', label: '💀 DEAD STOCK' },
      CRITICAL: { bg: '#FEF3C7', color: '#92400E', label: '🔴 CRITICAL' },
      HIGH: { bg: '#FED7AA', color: '#9A3412', label: '🟠 HIGH' },
      MEDIUM: { bg: '#FEF9C3', color: '#854D0E', label: '🟡 MEDIUM' },
      NORMAL: { bg: '#D1FAE5', color: '#065F46', label: '🟢 NORMAL' }
    };
    
    const style = styles[category] || styles.NORMAL;
    return (
      <span style={{
        padding: '4px 12px',
        background: style.bg,
        color: style.color,
        borderRadius: '6px',
        fontSize: '11px',
        fontWeight: '700'
      }}>
        {style.label}
      </span>
    );
  };

  if (loading) {
    return (
      <div style={{ padding: '60px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>🏷️</div>
        <div style={{ fontSize: '18px', color: '#6B7280' }}>Analyzing aged inventory...</div>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px' }}>
      {/* Header */}
      <div style={{ marginBottom: '32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: '700',color:'black', marginBottom: '8px' }}>
            🏷️ Markdown & Clearance Coach
          </h1>
          <p style={{ fontSize: '14px', color: '#6B7280' }}>
            AI-powered pricing strategy for aged inventory
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={loading}
          style={{
            padding: '12px 24px',
            background: loading ? '#E5E7EB' : 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)',
            color: 'white',
            border: 'none',
            borderRadius: '12px',
            fontSize: '14px',
            fontWeight: '600',
            cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: loading ? 'none' : '0 4px 12px rgba(139, 92, 246, 0.3)',
            transition: 'all 0.2s'
          }}
        >
          <span style={{ fontSize: '16px' }}>🔄</span>
          {loading ? 'Analyzing...' : 'Refresh Analysis'}
        </button>
      </div>

      {/* Summary Stats */}
      {summary && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '20px',
          marginBottom: '32px'
        }}>
          <div style={{
            background: 'white',
            padding: '24px',
            borderRadius: '12px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
          }}>
            <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '8px' }}>AGED ITEMS</div>
            <div style={{ fontSize: '32px', fontWeight: '700', color: '#F59E0B' }}>
              {summary.total_aged_items}
            </div>
          </div>

          <div style={{
            background: 'white',
            padding: '24px',
            borderRadius: '12px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
          }}>
            <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '8px' }}>CURRENT VALUE</div>
            <div style={{ fontSize: '32px', fontWeight: '700', color: '#EF4444' }}>
              ₹{usdToInr(summary.total_aged_value || 0).toLocaleString()}
            </div>
          </div>

          <div style={{
            background: 'white',
            padding: '24px',
            borderRadius: '12px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
          }}>
            <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '8px' }}>POTENTIAL REVENUE</div>
            <div style={{ fontSize: '32px', fontWeight: '700', color: '#10B981' }}>
              ₹{usdToInr(summary.potential_revenue || 0).toLocaleString()}
            </div>
          </div>

          <div style={{
            background: 'white',
            padding: '24px',
            borderRadius: '12px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
          }}>
            <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '8px' }}>RECOVERY RATE</div>
            <div style={{ fontSize: '32px', fontWeight: '700', color: '#3B82F6' }}>
              {summary.recovery_rate}%
            </div>
          </div>
        </div>
      )}

      {/* AI Recommendations */}
      {aiRecommendations && (
        <div style={{
          background: 'white',
          padding: '24px',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          marginBottom: '32px'
        }}>
          <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px' }}>
            🤖 AI Strategic Recommendations
          </h3>
          <div style={{ fontSize: '14px', lineHeight: '1.8', color: '#374151' }}>
            {aiRecommendations.split('\n').map((line, index) => {
              // Headers (###)
              if (line.startsWith('###')) {
                return (
                  <h4 key={index} style={{ 
                    fontSize: '16px', 
                    fontWeight: '700', 
                    marginTop: '20px', 
                    marginBottom: '12px',
                    color: '#F59E0B'
                  }}>
                    {line.replace('###', '').trim()}
                  </h4>
                );
              }
              // Bold text (**text**)
              else if (line.includes('**')) {
                const parts = line.split('**');
                return (
                  <p key={index} style={{ marginBottom: '8px' }}>
                    {parts.map((part, i) => 
                      i % 2 === 1 ? <strong key={i}>{part}</strong> : part
                    )}
                  </p>
                );
              }
              // Bullet points (-)
              else if (line.trim().startsWith('-')) {
                return (
                  <li key={index} style={{ 
                    marginLeft: '20px', 
                    marginBottom: '6px',
                    listStyleType: 'disc'
                  }}>
                    {line.replace(/^-\s*/, '')}
                  </li>
                );
              }
              // Empty lines
              else if (line.trim() === '') {
                return <div key={index} style={{ height: '8px' }} />;
              }
              // Regular paragraphs
              else {
                return (
                  <p key={index} style={{ marginBottom: '8px' }}>
                    {line}
                  </p>
                );
              }
            })}
          </div>
        </div>
      )}

      {/* View Tabs */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
        <button
          onClick={() => setActiveView('products')}
          style={{
            padding: '12px 24px',
            background: activeView === 'products' ? '#F59E0B' : 'white',
            color: activeView === 'products' ? 'white' : '#6B7280',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: '600',
            cursor: 'pointer'
          }}
        >
          📦 Aged Products ({agedProducts.length})
        </button>
        <button
          onClick={() => setActiveView('bundles')}
          style={{
            padding: '12px 24px',
            background: activeView === 'bundles' ? '#F59E0B' : 'white',
            color: activeView === 'bundles' ? 'white' : '#6B7280',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: '600',
            cursor: 'pointer'
          }}
        >
          🎁 Bundles ({bundles.length})
        </button>
        <button
          onClick={() => setActiveView('timeline')}
          style={{
            padding: '12px 24px',
            background: activeView === 'timeline' ? '#F59E0B' : 'white',
            color: activeView === 'timeline' ? 'white' : '#6B7280',
            border: '1px solid #E5E7EB',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: '600',
            cursor: 'pointer'
          }}
        >
          📅 4 Week Plan
        </button>
      </div>

      {/* Aged Products View */}
      {activeView === 'products' && (
        <div style={{
          background: 'white',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          overflow: 'hidden'
        }}>
          {agedProducts.length === 0 ? (
            <div style={{ padding: '60px', textAlign: 'center' }}>
              <div style={{ fontSize: '64px', marginBottom: '16px' }}>✅</div>
              <h3 style={{ fontSize: '20px', fontWeight: '600', marginBottom: '8px' }}>
                No Aged Inventory
              </h3>
              <p style={{ fontSize: '14px', color: '#6B7280' }}>
                All products are moving at healthy rates!
              </p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', minWidth: '800px' }}>
              <thead>
                <tr style={{ background: '#F9FAFB', borderBottom: '2px solid #E5E7EB' }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '700', color: '#6B7280', width: '28%' }}>PRODUCT</th>
                  <th style={{ padding: '12px 8px', textAlign: 'center', fontSize: '12px', fontWeight: '700', color: '#6B7280', width: '12%' }}>STATUS</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', fontSize: '12px', fontWeight: '700', color: '#6B7280', width: '14%' }}>CURRENT</th>
                  <th style={{ padding: '12px 8px', textAlign: 'center', fontSize: '12px', fontWeight: '700', color: '#6B7280', width: '10%' }}>MARKDOWN</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', fontSize: '12px', fontWeight: '700', color: '#6B7280', width: '14%' }}>NEW PRICE</th>
                  <th style={{ padding: '12px 8px', textAlign: 'right', fontSize: '12px', fontWeight: '700', color: '#6B7280', width: '8%' }}>QTY</th>
                  <th style={{ padding: '12px 8px', textAlign: 'center', fontSize: '12px', fontWeight: '700', color: '#6B7280', width: '14%' }}>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {agedProducts.map((product) => (
                  <tr
                    key={product.sku}
                    style={{ borderBottom: '1px solid #E5E7EB', cursor: 'pointer' }}
                    onClick={() => setSelectedProduct(product)}
                  >
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: '600', color: '#111827', fontSize: '13px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.name}</div>
                      <div style={{ fontSize: '11px', color: '#6B7280' }}>{product.category}</div>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center' }}>
                      {getAgeCategoryBadge(product.age_category)}
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: '600', color: '#111827', fontSize: '14px' }}>
                      ₹{usdToInr(product.current_price).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center' }}>
                      <span style={{
                        padding: '4px 8px',
                        background: '#FEE2E2',
                        color: '#991B1B',
                        borderRadius: '4px',
                        fontSize: '12px',
                        fontWeight: '700'
                      }}>
                        -{product.markdown_recommendation.markdown_percentage}%
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: '700', color: '#10B981', fontSize: '14px' }}>
                      ₹{usdToInr(product.markdown_recommendation.new_price).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right', fontSize: '13px', color: '#111827' }}>
                      {product.quantity}
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center' }}>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleApplyMarkdown(product); }}
                        disabled={applyingMarkdown}
                        style={{
                          padding: '6px 16px',
                          background: applyingMarkdown ? '#D1D5DB' : '#F59E0B',
                          color: 'white',
                          border: 'none',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: '600',
                          cursor: applyingMarkdown ? 'not-allowed' : 'pointer'
                        }}
                      >
                        Apply
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </div>
      )}

      {/* Bundles View */}
      {activeView === 'bundles' && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
          gap: '24px'
        }}>
          {bundles.map((bundle, index) => (
            <div
              key={index}
              style={{
                background: 'white',
                borderRadius: '12px',
                padding: '24px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
              }}
            >
              <div style={{ fontSize: '32px', marginBottom: '12px' }}>🎁</div>
              <h3 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px' }}>
                {bundle.bundle_name}
              </h3>
              
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '8px', fontWeight: '600' }}>
                  INCLUDES:
                </div>
                {bundle.items.map((item, i) => (
                  <div key={i} style={{ fontSize: '13px', marginBottom: '4px' }}>
                    • {item.name}
                  </div>
                ))}
              </div>

              <div style={{
                background: '#F9FAFB',
                padding: '16px',
                borderRadius: '8px',
                marginBottom: '16px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '13px', color: '#6B7280' }}>Regular:</span>
                  <span style={{ fontSize: '14px', textDecoration: 'line-through' }}>
                    ₹{usdToInr(bundle.regular_value).toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '13px', color: '#6B7280' }}>Bundle:</span>
                  <span style={{ fontSize: '18px', fontWeight: '800', color: '#10B981' }}>
                    ₹{usdToInr(bundle.bundle_price).toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '13px', color: '#6B7280' }}>Save:</span>
                  <span style={{ fontSize: '14px', fontWeight: '700', color: '#EF4444' }}>
                    ₹{usdToInr(bundle.savings).toFixed(2)} ({bundle.savings_percentage}%)
                  </span>
                </div>
              </div>

              <button
                onClick={() => handleCreateBundle(bundle)}
                style={{
                  width: '100%',
                  padding: '12px',
                  background: '#F59E0B',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#D97706'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#F59E0B'}
              >
                Create Bundle
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Timeline / 4 Week Plan View */}
      {activeView === 'timeline' && (
        <div style={{
          background: 'white',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          padding: '32px'
        }}>
          {!timeline ? (
            <div style={{ padding: '60px', textAlign: 'center' }}>
              <div style={{ fontSize: '64px', marginBottom: '16px' }}>📅</div>
              <h3 style={{ fontSize: '20px', fontWeight: '600', marginBottom: '8px', color: '#111827' }}>
                No Timeline Data
              </h3>
              <p style={{ fontSize: '14px', color: '#6B7280' }}>
                Refresh the analysis to generate a clearance timeline.
              </p>
            </div>
          ) : (
            <>
              <h3 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '8px', color: '#111827' }}>
                📅 Phased Clearance Plan
              </h3>
              <p style={{ fontSize: '14px', color: '#6B7280', marginBottom: '28px' }}>
                Strategically phase markdowns over 4 weeks to maximize revenue recovery
              </p>

              {/* Total summary bar */}
              <div style={{
                background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                borderRadius: '12px',
                padding: '20px 28px',
                marginBottom: '28px',
                color: 'white',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <div>
                  <div style={{ fontSize: '13px', opacity: 0.9, marginBottom: '4px' }}>TOTAL ITEMS IN PLAN</div>
                  <div style={{ fontSize: '32px', fontWeight: '800' }}>{timeline.total || 0}</div>
                </div>
                <div style={{ fontSize: '48px' }}>🎯</div>
              </div>

              {/* Phase cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px' }}>
                {/* Immediate */}
                <div style={{
                  border: '2px solid #FEE2E2',
                  borderRadius: '12px',
                  padding: '24px',
                  background: '#FFF5F5'
                }}>
                  <div style={{
                    width: '48px',
                    height: '48px',
                    background: '#FEE2E2',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '24px',
                    marginBottom: '16px'
                  }}>🔴</div>
                  <div style={{ fontSize: '12px', fontWeight: '700', color: '#991B1B', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Immediate Action
                  </div>
                  <div style={{ fontSize: '11px', color: '#B91C1C', marginBottom: '12px' }}>
                    Week 1 — Critical & Dead Stock
                  </div>
                  <div style={{ fontSize: '36px', fontWeight: '800', color: '#991B1B' }}>
                    {typeof timeline.immediate === 'number' ? timeline.immediate : (timeline.immediate?.length || 0)}
                  </div>
                  <div style={{ fontSize: '12px', color: '#B91C1C', marginTop: '4px' }}>products</div>
                  <div style={{
                    marginTop: '16px',
                    padding: '10px 12px',
                    background: '#FEE2E2',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#991B1B',
                    lineHeight: '1.5'
                  }}>
                    35-50% markdown. Flash sales, email blasts, homepage banners.
                  </div>
                </div>

                {/* Week 2 */}
                <div style={{
                  border: '2px solid #FED7AA',
                  borderRadius: '12px',
                  padding: '24px',
                  background: '#FFFBF5'
                }}>
                  <div style={{
                    width: '48px',
                    height: '48px',
                    background: '#FED7AA',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '24px',
                    marginBottom: '16px'
                  }}>🟠</div>
                  <div style={{ fontSize: '12px', fontWeight: '700', color: '#9A3412', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Week 2
                  </div>
                  <div style={{ fontSize: '11px', color: '#C2410C', marginBottom: '12px' }}>
                    High-priority items
                  </div>
                  <div style={{ fontSize: '36px', fontWeight: '800', color: '#9A3412' }}>
                    {typeof timeline.week_2 === 'number' ? timeline.week_2 : (timeline.week_2?.length || 0)}
                  </div>
                  <div style={{ fontSize: '12px', color: '#C2410C', marginTop: '4px' }}>products</div>
                  <div style={{
                    marginTop: '16px',
                    padding: '10px 12px',
                    background: '#FED7AA',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#9A3412',
                    lineHeight: '1.5'
                  }}>
                    25% markdown. Category promotions, bundle deals, social campaigns.
                  </div>
                </div>

                {/* Week 4 */}
                <div style={{
                  border: '2px solid #FEF9C3',
                  borderRadius: '12px',
                  padding: '24px',
                  background: '#FFFEF5'
                }}>
                  <div style={{
                    width: '48px',
                    height: '48px',
                    background: '#FEF9C3',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '24px',
                    marginBottom: '16px'
                  }}>🟡</div>
                  <div style={{ fontSize: '12px', fontWeight: '700', color: '#854D0E', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Week 3-4
                  </div>
                  <div style={{ fontSize: '11px', color: '#A16207', marginBottom: '12px' }}>
                    Moderate-priority items
                  </div>
                  <div style={{ fontSize: '36px', fontWeight: '800', color: '#854D0E' }}>
                    {typeof timeline.week_4 === 'number' ? timeline.week_4 : (timeline.week_4?.length || 0)}
                  </div>
                  <div style={{ fontSize: '12px', color: '#A16207', marginTop: '4px' }}>products</div>
                  <div style={{
                    marginTop: '16px',
                    padding: '10px 12px',
                    background: '#FEF9C3',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#854D0E',
                    lineHeight: '1.5'
                  }}>
                    15% markdown. Gentle discounts, loyalty offers, cross-sells.
                  </div>
                </div>

                {/* Liquidation */}
                <div style={{
                  border: '2px solid #E5E7EB',
                  borderRadius: '12px',
                  padding: '24px',
                  background: '#F9FAFB'
                }}>
                  <div style={{
                    width: '48px',
                    height: '48px',
                    background: '#E5E7EB',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '24px',
                    marginBottom: '16px'
                  }}>♻️</div>
                  <div style={{ fontSize: '12px', fontWeight: '700', color: '#374151', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Liquidation
                  </div>
                  <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '12px' }}>
                    Post week 4 — remaining stock
                  </div>
                  <div style={{ fontSize: '36px', fontWeight: '800', color: '#374151' }}>
                    {typeof timeline.liquidation === 'number' ? timeline.liquidation : (timeline.liquidation?.length || 0)}
                  </div>
                  <div style={{ fontSize: '12px', color: '#6B7280', marginTop: '4px' }}>products</div>
                  <div style={{
                    marginTop: '16px',
                    padding: '10px 12px',
                    background: '#E5E7EB',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: '#374151',
                    lineHeight: '1.5'
                  }}>
                    50%+ clearance. Bulk deals, B2B channels, donation write-offs.
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Markdown Applied Success Modal */}
      {showMarkdownSuccess && appliedProduct && (
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
          zIndex: 10000,
          animation: 'fadeIn 0.2s ease-in'
        }} onClick={() => setShowMarkdownSuccess(false)}>
          <div style={{
            background: 'white',
            borderRadius: '16px',
            maxWidth: '500px',
            width: '90%',
            padding: '32px',
            textAlign: 'center',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            animation: 'slideUp 0.3s ease-out'
          }} onClick={(e) => e.stopPropagation()}>
            
            {/* Success Icon */}
            <div style={{
              width: '80px',
              height: '80px',
              background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 24px',
              animation: 'scaleIn 0.4s ease-out'
            }}>
              <span style={{ fontSize: '48px' }}>🏷️</span>
            </div>

            {/* Success Message */}
            <h2 style={{ 
              fontSize: '28px', 
              fontWeight: '700', 
              marginBottom: '12px',
              color: '#1F2937'
            }}>
              Markdown Applied!
            </h2>
            
            <p style={{ 
              fontSize: '16px', 
              color: '#6B7280', 
              marginBottom: '24px',
              lineHeight: '1.6'
            }}>
              <strong>{appliedProduct.name}</strong> has been successfully marked down.
            </p>

            {/* Markdown Summary */}
            <div style={{
              background: '#F9FAFB',
              padding: '20px',
              borderRadius: '12px',
              marginBottom: '24px',
              textAlign: 'left'
            }}>
              <div style={{ 
                fontSize: '12px', 
                color: '#6B7280', 
                marginBottom: '12px',
                fontWeight: '600',
                textTransform: 'uppercase'
              }}>
                Pricing Update
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '14px', color: '#6B7280' }}>Original Price:</span>
                <span style={{ fontSize: '14px', textDecoration: 'line-through', color: '#374151' }}>
                  ₹{usdToInr(appliedProduct.current_price).toFixed(2)}
                </span>
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '14px', color: '#6B7280' }}>Markdown:</span>
                <span style={{ fontSize: '16px', fontWeight: '700', color: '#EF4444' }}>
                  -{appliedProduct.markdown_recommendation.markdown_percentage}%
                </span>
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '14px', color: '#6B7280' }}>New Price:</span>
                <span style={{ fontSize: '18px', fontWeight: '800', color: '#10B981' }}>
                  ₹{usdToInr(appliedProduct.markdown_recommendation.new_price).toFixed(2)}
                </span>
              </div>
              
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between',
                paddingTop: '12px',
                borderTop: '1px solid #E5E7EB'
              }}>
                <span style={{ fontSize: '14px', color: '#6B7280' }}>Potential Revenue:</span>
                <span style={{ fontSize: '16px', fontWeight: '700', color: '#F59E0B' }}>
                  ₹{usdToInr(appliedProduct.markdown_recommendation.potential_revenue).toLocaleString()}
                </span>
              </div>
            </div>

            {/* Additional Info */}
            <div style={{
              background: '#FEF3C7',
              padding: '16px',
              borderRadius: '8px',
              marginBottom: '24px',
              textAlign: 'left'
            }}>
              <div style={{ fontSize: '13px', color: '#92400E', lineHeight: '1.6' }}>
                <strong>📊 What's Next:</strong><br/>
                The new price is now active. Monitor sales velocity over the next 7 days to assess effectiveness.
              </div>
            </div>

            {/* Close Button */}
            <button
              onClick={() => setShowMarkdownSuccess(false)}
              style={{
                width: '100%',
                padding: '14px',
                background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                color: 'white',
                border: 'none',
                borderRadius: '10px',
                fontSize: '16px',
                fontWeight: '600',
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(245, 158, 11, 0.3)',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 6px 16px rgba(245, 158, 11, 0.4)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 4px 12px rgba(245, 158, 11, 0.3)';
              }}
            >
              Got it!
            </button>

            {/* Auto-close indicator */}
            <p style={{ 
              fontSize: '12px', 
              color: '#9CA3AF', 
              marginTop: '12px' 
            }}>
              This message will close automatically
            </p>
          </div>
        </div>
      )}

      {/* Bundle Success Modal */}
      {showBundleSuccess && createdBundle && (
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
          zIndex: 10000,
          animation: 'fadeIn 0.2s ease-in'
        }} onClick={() => setShowBundleSuccess(false)}>
          <div style={{
            background: 'white',
            borderRadius: '16px',
            maxWidth: '500px',
            width: '90%',
            padding: '32px',
            textAlign: 'center',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            animation: 'slideUp 0.3s ease-out'
          }} onClick={(e) => e.stopPropagation()}>
            
            {/* Success Icon */}
            <div style={{
              width: '80px',
              height: '80px',
              background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 24px',
              animation: 'scaleIn 0.4s ease-out'
            }}>
              <span style={{ fontSize: '48px' }}>✓</span>
            </div>

            {/* Success Message */}
            <h2 style={{ 
              fontSize: '28px', 
              fontWeight: '700', 
              marginBottom: '12px',
              color: '#1F2937'
            }}>
              Bundle Created!
            </h2>
            
            <p style={{ 
              fontSize: '16px', 
              color: '#6B7280', 
              marginBottom: '24px',
              lineHeight: '1.6'
            }}>
              <strong>{createdBundle.bundle_name}</strong> has been successfully created and is now available for purchase.
            </p>

            {/* Bundle Summary */}
            <div style={{
              background: '#F9FAFB',
              padding: '20px',
              borderRadius: '12px',
              marginBottom: '24px',
              textAlign: 'left'
            }}>
              <div style={{ 
                fontSize: '12px', 
                color: '#6B7280', 
                marginBottom: '12px',
                fontWeight: '600',
                textTransform: 'uppercase'
              }}>
                Bundle Details
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '14px', color: '#6B7280' }}>Items:</span>
                <span style={{ fontSize: '14px', fontWeight: '600' }}>
                  {createdBundle.items.length} products
                </span>
              </div>
              
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '14px', color: '#6B7280' }}>Regular Price:</span>
                  <span style={{ fontSize: '14px', textDecoration: 'line-through' }}>
                    ₹{usdToInr(createdBundle.regular_value).toFixed(2)}
                  </span>
                </div>
              
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '14px', color: '#6B7280' }}>Bundle Price:</span>
                  <span style={{ fontSize: '18px', fontWeight: '800', color: '#10B981' }}>
                    ₹{usdToInr(createdBundle.bundle_price).toFixed(2)}
                  </span>
                </div>
              
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between',
                paddingTop: '12px',
                borderTop: '1px solid #E5E7EB'
              }}>
                <span style={{ fontSize: '14px', color: '#6B7280' }}>Customer Saves:</span>
                <span style={{ fontSize: '16px', fontWeight: '700', color: '#EF4444' }}>
                  ₹{usdToInr(createdBundle.savings).toFixed(2)} ({createdBundle.savings_percentage}%)
                </span>
              </div>
            </div>

            {/* Close Button */}
            <button
              onClick={() => setShowBundleSuccess(false)}
              style={{
                width: '100%',
                padding: '14px',
                background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
                color: 'white',
                border: 'none',
                borderRadius: '10px',
                fontSize: '16px',
                fontWeight: '600',
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 6px 16px rgba(16, 185, 129, 0.4)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 4px 12px rgba(16, 185, 129, 0.3)';
              }}
            >
              Got it!
            </button>

            {/* Auto-close indicator */}
            <p style={{ 
              fontSize: '12px', 
              color: '#9CA3AF', 
              marginTop: '12px' 
            }}>
              This message will close automatically
            </p>
          </div>
        </div>
      )}

      {/* Product Detail Modal */}
      {selectedProduct && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '20px'
        }} onClick={() => setSelectedProduct(null)}>
          <div style={{
            background: 'white',
            borderRadius: '16px',
            maxWidth: '520px',
            width: '100%',
            padding: '28px',
            maxHeight: '90vh',
            overflow: 'auto',
            color: '#111827',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
          }} onClick={(e) => e.stopPropagation()}>

            <h2 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '6px', color: '#111827' }}>
              {selectedProduct.name}
            </h2>
            <p style={{ fontSize: '13px', color: '#6B7280', marginBottom: '16px' }}>
              {selectedProduct.category} &bull; SKU: {selectedProduct.sku}
            </p>

            <div style={{ marginBottom: '20px' }}>
              {getAgeCategoryBadge(selectedProduct.age_category)}
              <span style={{ marginLeft: '12px', fontSize: '12px', color: '#6B7280' }}>
                {selectedProduct.quantity} units &bull; {selectedProduct.days_remaining} days of supply
              </span>
            </div>

            {/* Price comparison */}
            <div style={{
              background: '#F9FAFB',
              padding: '20px',
              borderRadius: '12px',
              marginBottom: '20px',
              border: '1px solid #E5E7EB'
            }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '4px', fontWeight: '600', textTransform: 'uppercase' }}>Current Price</div>
                  <div style={{ fontSize: '22px', fontWeight: '800', color: '#111827' }}>
                    ₹{usdToInr(selectedProduct.current_price).toLocaleString('en-IN')}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '11px', color: '#6B7280', marginBottom: '4px', fontWeight: '600', textTransform: 'uppercase' }}>New Price</div>
                  <div style={{ fontSize: '22px', fontWeight: '800', color: '#10B981' }}>
                    ₹{usdToInr(selectedProduct.markdown_recommendation.new_price).toLocaleString('en-IN')}
                  </div>
                </div>
              </div>
            </div>

            {/* Recommendation */}
            <div style={{
              background: '#FEF3C7',
              padding: '16px',
              borderRadius: '10px',
              marginBottom: '20px',
              border: '1px solid #FDE68A'
            }}>
              <div style={{ fontSize: '14px', fontWeight: '700', marginBottom: '8px', color: '#92400E' }}>
                💡 Recommendation
              </div>
              <div style={{ fontSize: '13px', marginBottom: '10px', color: '#78350F', lineHeight: '1.5' }}>
                {selectedProduct.markdown_recommendation.reason}
              </div>
              <div style={{ fontSize: '12px', color: '#92400E' }}>
                Markdown: <strong>{selectedProduct.markdown_recommendation.markdown_percentage}%</strong> &bull;
                Potential Revenue: <strong>₹{usdToInr(selectedProduct.markdown_recommendation.potential_revenue).toLocaleString('en-IN')}</strong>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={() => handleApplyMarkdown(selectedProduct)}
                disabled={applyingMarkdown}
                style={{
                  flex: 1,
                  padding: '14px',
                  background: applyingMarkdown ? '#D1D5DB' : 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '10px',
                  fontSize: '15px',
                  fontWeight: '700',
                  cursor: applyingMarkdown ? 'not-allowed' : 'pointer',
                  boxShadow: applyingMarkdown ? 'none' : '0 4px 12px rgba(245, 158, 11, 0.3)'
                }}
              >
                {applyingMarkdown ? 'Applying...' : 'Apply Markdown'}
              </button>
              <button
                onClick={() => setSelectedProduct(null)}
                style={{
                  padding: '14px 24px',
                  background: '#F3F4F6',
                  color: '#374151',
                  border: '1px solid #D1D5DB',
                  borderRadius: '10px',
                  fontSize: '15px',
                  fontWeight: '600',
                  cursor: 'pointer'
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
