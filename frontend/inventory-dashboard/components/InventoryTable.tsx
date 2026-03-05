interface InventoryTableProps {
  inventory: any[]
  loading: boolean
  onProductSelect: (product: any) => void
  onRefresh: () => void
}

export default function InventoryTable({ inventory, loading, onProductSelect, onRefresh }: InventoryTableProps) {
  // Prices are stored in INR — no conversion needed
  const usdToInr = (amount: number) => {
    if (!amount || !Number.isFinite(amount)) return 0
    return Math.round(amount * 100) / 100
  }

  const getStockStatus = (item: any) => {
    if (item.stock_quantity === 0) return { label: 'Out of Stock', color: '#EF4444' }
    if (item.stock_quantity <= item.reorder_point) return { label: 'Low Stock', color: '#F59E0B' }
    return { label: 'In Stock', color: '#10B981' }
  }

  return (
    <div style={{
      background: 'white',
      borderRadius: '12px',
      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
      overflow: 'hidden'
    }}>
      <div style={{
        padding: '20px',
        borderBottom: '1px solid #E5E7EB',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '600' }}>
          Inventory Items
        </h2>
        <button
          onClick={onRefresh}
          style={{
            padding: '8px 16px',
            background: '#E11D48',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: '600'
          }}
        >
          🔄 Refresh
        </button>
      </div>

      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: '#6B7280' }}>
          Loading inventory...
        </div>
      ) : (
        <div style={{ overflowX: 'auto', maxHeight: '600px', overflowY: 'auto', width: '100%' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'auto', minWidth: '1000px' }}>
            <thead style={{ background: '#F9FAFB', position: 'sticky', top: 0, zIndex: 10 }}>
              <tr>
                <th style={{ 
                  padding: '12px', 
                  textAlign: 'left', 
                  fontSize: '12px', 
                  fontWeight: '600', 
                  color: '#374151',
                  minWidth: '120px'
                }}>SKU</th>
                <th style={{ 
                  padding: '12px', 
                  textAlign: 'left', 
                  fontSize: '12px', 
                  fontWeight: '600', 
                  color: '#374151',
                  minWidth: '200px'
                }}>Product</th>
                <th style={{ 
                  padding: '12px', 
                  textAlign: 'left', 
                  fontSize: '12px', 
                  fontWeight: '600', 
                  color: '#374151',
                  minWidth: '150px'
                }}>Vendor</th>
                <th style={{ 
                  padding: '12px', 
                  textAlign: 'right', 
                  fontSize: '12px', 
                  fontWeight: '600', 
                  color: '#374151',
                  minWidth: '80px'
                }}>Stock</th>
                <th style={{ 
                  padding: '12px', 
                  textAlign: 'right', 
                  fontSize: '12px', 
                  fontWeight: '600', 
                  color: '#374151',
                  minWidth: '100px'
                }}>Reorder Point</th>
                <th style={{ 
                  padding: '12px', 
                  textAlign: 'right', 
                  fontSize: '12px', 
                  fontWeight: '600', 
                  color: '#374151',
                  minWidth: '100px'
                }}>Price</th>
                <th style={{ 
                  padding: '12px', 
                  textAlign: 'center', 
                  fontSize: '12px', 
                  fontWeight: '600', 
                  color: '#374151',
                  minWidth: '100px'
                }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {inventory.map((item, index) => {
                const status = getStockStatus(item)
                return (
                  <tr key={index} style={{ borderBottom: '1px solid #E5E7EB' }}>
                    <td style={{ 
                      padding: '12px', 
                      fontSize: '13px', 
                      fontFamily: 'ui-monospace, monospace',
                      color: '#111827',
                      fontWeight: '600',
                      minWidth: '120px'
                    }}>
                      {item.sku || 'N/A'}
                    </td>
                    <td style={{ 
                      padding: '12px', 
                      fontSize: '14px', 
                      fontWeight: '600',
                      color: '#111827',
                      minWidth: '200px'
                    }}>
                      {item.name || 'Unknown Product'}
                    </td>
                    <td style={{ 
                      padding: '12px', 
                      fontSize: '14px', 
                      color: '#111827',
                      fontWeight: '500',
                      minWidth: '150px'
                    }}>
                      {item.vendor || 'N/A'}
                    </td>
                    <td style={{ 
                      padding: '12px', 
                      textAlign: 'right', 
                      fontSize: '14px', 
                      fontWeight: '700',
                      color: '#111827',
                      minWidth: '80px'
                    }}>
                      {item.stock_quantity ?? item.inventory ?? 0}
                    </td>
                    <td style={{ 
                      padding: '12px', 
                      textAlign: 'right', 
                      fontSize: '14px', 
                      fontWeight: '600',
                      color: '#111827',
                      minWidth: '100px'
                    }}>
                      {item.reorder_point}
                    </td>
                    <td style={{ 
                      padding: '12px', 
                      textAlign: 'right', 
                      fontSize: '14px', 
                      fontWeight: '700',
                      color: '#111827',
                      minWidth: '100px'
                    }}>
                      ₹{usdToInr(item.price || 0).toFixed(2)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <span style={{
                        padding: '4px 12px',
                        borderRadius: '12px',
                        fontSize: '12px',
                        fontWeight: '600',
                        background: `${status.color}20`,
                        color: status.color
                      }}>
                        {status.label}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
