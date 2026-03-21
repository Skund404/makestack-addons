/**
 * Custom sidebar for the Electronics Lab standalone app mode.
 */
import { useLocation, useNavigate } from '@tanstack/react-router'
import { Zap, CircuitBoard, Box } from 'lucide-react'

const NAV_ITEMS = [
  { id: 'home',       label: 'Home',       icon: Zap,          route: '/electronics' },
  { id: 'circuits',   label: 'Circuits',   icon: CircuitBoard, route: '/electronics/circuits' },
  { id: 'components', label: 'Components', icon: Box,          route: '/electronics/components' },
]

export function ElectronicsSidebar() {
  const location = useLocation()
  const navigate = useNavigate()

  const isActive = (route: string) => {
    if (route === '/electronics') return location.pathname === '/electronics'
    return location.pathname.startsWith(route)
  }

  return (
    <div
      className="flex h-full flex-col"
      style={{
        width: 200,
        backgroundColor: '#0a1628',
        color: '#94a3b8',
      }}
    >
      {/* Branding */}
      <div className="px-4 py-5 border-b border-white/10">
        <div className="flex items-center gap-2">
          <Zap size={20} style={{ color: '#38bdf8' }} />
          <div>
            <div className="text-sm font-semibold" style={{ color: '#e2e8f0' }}>
              Electronics Lab
            </div>
            <div className="text-xs opacity-60">Circuit simulator</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-1">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          const active = isActive(item.route)
          return (
            <button
              key={item.id}
              onClick={() => navigate({ to: item.route })}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors"
              style={{
                backgroundColor: active ? '#1e293b' : 'transparent',
                color: active ? '#e2e8f0' : '#94a3b8',
              }}
            >
              <Icon size={16} />
              {item.label}
            </button>
          )
        })}
      </nav>

      {/* Back to workshop */}
      <div className="px-3 py-3 border-t border-white/10">
        <button
          onClick={() => {
            const ws = sessionStorage.getItem('ms-app-origin')
            navigate({ to: ws || '/' })
          }}
          className="text-xs opacity-50 hover:opacity-80 transition-opacity"
        >
          Back to workshop
        </button>
      </div>
    </div>
  )
}
