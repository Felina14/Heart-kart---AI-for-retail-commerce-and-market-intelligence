'use client'

import { useState, useEffect } from 'react'
import DashboardHeader from '../components/DashboardHeader'
import StatsOverview from '../components/StatsOverview'
import InventoryTable from '../components/InventoryTable'
import ReplenishmentPanel from '../components/ReplenishmentPanel'
import StockoutPanel from '../components/StockoutPanel'
import CopilotPanel from '../components/CopilotPanel'
import ExceptionPanel from '../components/ExceptionPanel'
import NotificationsPanel from '../components/NotificationsPanel'
import { getApiBaseUrl } from '../lib/apiBaseUrl'

const API_BASE_URL = getApiBaseUrl()
import MarkdownPanel from '../components/MarkdownPanel'
import MarketIntelligencePanel from '../components/MarketIntelligencePanel'
import PricingIntelligencePanel from '../components/PricingIntelligencePanel'

type TabName = 'inventory' | 'replenishment' | 'notifications' | 'stockout'
  | 'exceptions' | 'copilot' | 'markdown' | 'market-intelligence' | 'pricing-intelligence'

export default function InventoryDashboard() {
  const [inventory, setInventory] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<TabName>('inventory')
  const [mountedTabs, setMountedTabs] = useState<Set<TabName>>(new Set(['inventory']))
  const [notificationCount, setNotificationCount] = useState(0)

  // Track which tabs have been visited so we lazy-mount panels
  const handleTabChange = (tab: TabName) => {
    setActiveTab(tab)
    setMountedTabs(prev => {
      if (prev.has(tab)) return prev
      const next = new Set(prev)
      next.add(tab)
      return next
    })
  }
  
  // Function to switch to notifications tab (passed to child components)
  const switchToNotifications = () => {
    handleTabChange('notifications')
  }
  
  // Function to increment notification count (passed to child components)
  const incrementNotificationCount = () => {
    setNotificationCount(prev => prev + 1)
  }
  
  // Reset count when viewing notifications tab
  useEffect(() => {
    if (activeTab === 'notifications') {
      setNotificationCount(0)
    }
  }, [activeTab])

  useEffect(() => {
    fetchInventory()
  }, [])

  const fetchInventory = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/inventory`)
      const data = await response.json()
      if (data.success) {
        setInventory(data.inventory)
      }
    } catch (error) {
      console.error('Error fetching inventory:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleProductSelect = (product: any) => {
    // Product selection handler - can be used for future features
    console.log('Selected product:', product)
  }

  return (
    <div style={{ 
      minHeight: '100vh', 
      backgroundColor: '#f5f5f5',
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      overflow: 'hidden'
    }}>
      <DashboardHeader />
      
      <div style={{ 
        maxWidth: '1400px', 
        margin: '0 auto', 
        padding: '20px',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        overflow: 'hidden'
      }}>
        {/* Tab Navigation - Sticky */}
        <div style={{ 
          display: 'flex', 
          gap: '8px', 
          marginBottom: '24px',
          padding: '8px',
          position: 'sticky',
          top: 0,
          background: 'linear-gradient(135deg, #FFFFFF 0%, #F9FAFB 100%)',
          zIndex: 100,
          borderRadius: '16px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          border: '1px solid #E5E7EB'
        }}>
          <button
            onClick={() => handleTabChange('inventory')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'inventory' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'inventory' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'inventory' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'inventory' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'inventory') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'inventory') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            📦 Inventory Overview
          </button>
          
          <button
            onClick={() => handleTabChange('replenishment')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'replenishment' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'replenishment' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'replenishment' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'replenishment' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'replenishment') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'replenishment') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            🤖 Replenishment Planner
          </button>
          
          <button
            onClick={() => handleTabChange('notifications')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'notifications' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'notifications' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'notifications' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'notifications' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'notifications') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'notifications') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            📧 Notifications
            {notificationCount > 0 && (
              <span style={{
                marginLeft: '8px',
                background: '#EF4444',
                color: 'white',
                borderRadius: '12px',
                padding: '2px 8px',
                fontSize: '12px',
                fontWeight: '700',
                minWidth: '20px',
                display: 'inline-block',
                textAlign: 'center'
              }}>
                {notificationCount}
              </span>
            )}
          </button>
          
          <button
            onClick={() => handleTabChange('stockout')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'stockout' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'stockout' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'stockout' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'stockout' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'stockout') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'stockout') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            🎯 Stockout Sentinel
          </button>
          
          <button
            onClick={() => handleTabChange('exceptions')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'exceptions' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'exceptions' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'exceptions' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'exceptions' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'exceptions') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'exceptions') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            🔍 Exception Investigator
          </button>
          
          <button
            onClick={() => handleTabChange('copilot')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'copilot' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'copilot' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'copilot' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'copilot' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'copilot') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'copilot') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            💬 Inventory Copilot
          </button>
          
          <button
            onClick={() => handleTabChange('markdown')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'markdown' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'markdown' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'markdown' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'markdown' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'markdown') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'markdown') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            🏷️ Markdown Coach
          </button>
          
          <button
            onClick={() => handleTabChange('market-intelligence')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'market-intelligence' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'market-intelligence' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'market-intelligence' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'market-intelligence' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'market-intelligence') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'market-intelligence') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            📊 Market Intelligence
          </button>
          
          <button
            onClick={() => handleTabChange('pricing-intelligence')}
            style={{
              padding: '14px 20px',
              background: activeTab === 'pricing-intelligence' 
                ? 'linear-gradient(135deg, #DC143C 0%, #B91C1C 100%)' 
                : 'transparent',
              color: activeTab === 'pricing-intelligence' ? 'white' : '#6B7280',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              fontSize: '15px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              boxShadow: activeTab === 'pricing-intelligence' 
                ? '0 4px 12px rgba(220, 20, 60, 0.3)' 
                : 'none',
              transform: activeTab === 'pricing-intelligence' ? 'translateY(-2px)' : 'none'
            }}
            onMouseEnter={(e) => {
              if (activeTab !== 'pricing-intelligence') {
                e.currentTarget.style.background = '#F3F4F6';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== 'pricing-intelligence') {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            💰 Pricing Intelligence
          </button>
          
        </div>

        {/* Tab Content - Scrollable with hidden scrollbar */}
        <div style={{ 
          flex: 1,
          overflow: 'auto',
          scrollbarWidth: 'none', /* Firefox */
          msOverflowStyle: 'none', /* IE and Edge */
        }}>
          <style jsx>{`
            div::-webkit-scrollbar {
              display: none; /* Chrome, Safari, Opera */
            }
          `}</style>
          
          {/* Lazy-mount: only render a panel after its tab is first clicked.
              This avoids 8+ simultaneous Lambda calls on page load (account limit = 10). */}
          <div style={{ display: activeTab === 'inventory' ? 'block' : 'none' }}>
            <StatsOverview inventory={inventory} />

            <div style={{ marginTop: '20px' }}>
              <InventoryTable
                inventory={inventory}
                loading={loading}
                onProductSelect={handleProductSelect}
                onRefresh={fetchInventory}
              />
            </div>
          </div>

          {mountedTabs.has('replenishment') && (
            <div style={{ display: activeTab === 'replenishment' ? 'block' : 'none' }}>
              <ReplenishmentPanel
                onSwitchToNotifications={switchToNotifications}
                onNotificationCreated={incrementNotificationCount}
              />
            </div>
          )}

          {mountedTabs.has('stockout') && (
            <div style={{ display: activeTab === 'stockout' ? 'block' : 'none' }}>
              <StockoutPanel />
            </div>
          )}

          {mountedTabs.has('exceptions') && (
            <div style={{ display: activeTab === 'exceptions' ? 'block' : 'none' }}>
              <ExceptionPanel />
            </div>
          )}

          {mountedTabs.has('copilot') && (
            <div style={{ display: activeTab === 'copilot' ? 'block' : 'none' }}>
              <CopilotPanel />
            </div>
          )}

          {mountedTabs.has('notifications') && (
            <div style={{ display: activeTab === 'notifications' ? 'block' : 'none' }}>
              <NotificationsPanel />
            </div>
          )}

          {mountedTabs.has('markdown') && (
            <div style={{ display: activeTab === 'markdown' ? 'block' : 'none' }}>
              <MarkdownPanel />
            </div>
          )}

          {mountedTabs.has('market-intelligence') && (
            <div style={{ display: activeTab === 'market-intelligence' ? 'block' : 'none' }}>
              <MarketIntelligencePanel />
            </div>
          )}

          {mountedTabs.has('pricing-intelligence') && (
            <div style={{ display: activeTab === 'pricing-intelligence' ? 'block' : 'none' }}>
              <PricingIntelligencePanel />
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
