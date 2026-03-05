export default function DashboardHeader() {
  return (
    <div style={{
      background: 'linear-gradient(135deg, #E11D48 0%, #C91A3F 100%)',
      color: 'white',
      padding: '20px 40px',
      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
      position: 'sticky',
      top: 0,
      zIndex: 1000
    }}>
      <div style={{ maxWidth: '1400px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <img 
            src="/HeartKart.png" 
            alt="HeartKart Logo" 
            style={{ height: '70px', width: 'auto', marginTop: '-15px', marginBottom: '-15px' }}
          />
          <div>
            <h1 style={{ margin: 0, fontSize: '22px', fontWeight: '700' }}>
              HeartKart Inventory
            </h1>
            
          </div>
        </div>
        
        
      </div>
    </div>
  )
}
