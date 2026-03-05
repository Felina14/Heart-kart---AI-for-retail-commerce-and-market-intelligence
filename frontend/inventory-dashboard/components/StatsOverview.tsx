interface StatsOverviewProps {
  inventory: any[]
}

export default function StatsOverview({ inventory }: StatsOverviewProps) {
  // Prices are stored in INR — no conversion needed
  const usdToInr = (amount: number) => {
    if (!amount || !Number.isFinite(amount)) return 0
    return Math.round(amount * 100) / 100
  }

  const totalProducts = inventory.length
  const lowStockCount = inventory.filter(item => 
    item.stock_quantity <= item.reorder_point
  ).length
  const outOfStockCount = inventory.filter(item => 
    item.stock_quantity === 0
  ).length
  const totalValueUsd = inventory.reduce((sum, item) =>
    sum + (item.stock_quantity * item.price), 0
  )
  const totalValueInr = usdToInr(totalValueUsd)

  const stats = [
    { label: 'Total Products', value: totalProducts, icon: '📦', color: '#3B82F6' },
    { label: 'Low Stock Items', value: lowStockCount, icon: '⚠️', color: '#F59E0B' },
    { label: 'Out of Stock', value: outOfStockCount, icon: '🚫', color: '#EF4444' },
    { label: 'Inventory Value', value: `₹${totalValueInr.toLocaleString()}`, icon: '💰', color: '#10B981' },
  ]

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px' }}>
      {stats.map((stat, index) => (
        <div key={index} style={{
          background: 'white',
          padding: '20px',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          border: `2px solid ${stat.color}20`
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '14px', color: '#6B7280', marginBottom: '8px' }}>
                {stat.label}
              </div>
              <div style={{ fontSize: '28px', fontWeight: '700', color: stat.color }}>
                {stat.value}
              </div>
            </div>
            <div style={{ fontSize: '32px' }}>{stat.icon}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
