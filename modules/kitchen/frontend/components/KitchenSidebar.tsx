/**
 * KitchenSidebar — custom branded sidebar for the kitchen module.
 *
 * Replaces the generic ModuleAppSidebar with:
 * - Warm brown theme from the mockup (#15100b background, serif branding)
 * - Shopping list badge count on the "Shop" nav item
 */
import { ArrowLeft } from 'lucide-react'
import { Link, useLocation, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { resolveIcon } from '@/lib/icons'
import { apiGet } from '@/lib/api'
import type { AppModeConfig, AppNavItem } from '@/modules/app-registry'

interface KitchenSidebarProps {
  config: AppModeConfig
}

export function KitchenSidebar({ config }: KitchenSidebarProps) {
  const navigate = useNavigate()
  const loc = useLocation()

  const workshopId = (() => {
    try { return sessionStorage.getItem('app-mode-workshop-id') ?? '' } catch { return '' }
  })()
  const workshopName = (() => {
    try { return sessionStorage.getItem('app-mode-workshop-name') ?? 'Workshop' } catch { return 'Workshop' }
  })()

  const handleBack = () => {
    if (workshopId) {
      void navigate({ to: '/workshop/$id', params: { id: workshopId } })
    } else {
      void navigate({ to: '/workshops' })
    }
  }

  // Fetch persistent shopping list badge count
  const { data: shoppingData } = useQuery({
    queryKey: ['kitchen-shopping-badge'],
    queryFn: async () => {
      try {
        return await apiGet<{ count: number }>('/modules/kitchen/shopping/badge')
      } catch {
        return { count: 0 }
      }
    },
    staleTime: 60_000,
    refetchInterval: 120_000,
  })

  return (
    <aside
      className="shrink-0 h-full flex flex-col"
      style={{ width: 186, backgroundColor: '#15100b' }}
    >
      {/* Back link */}
      <button
        onClick={handleBack}
        className="flex items-center gap-1.5 px-3.5 py-2.5 text-[11px] cursor-pointer transition-colors"
        style={{ color: '#56432d', borderBottom: '0.5px solid #1f1509' }}
      >
        <ArrowLeft size={11} />
        <span className="truncate">{workshopName}</span>
      </button>

      {/* Branding */}
      <div className="px-3.5 pt-4 pb-3" style={{ borderBottom: '0.5px solid #1f1509' }}>
        <div
          className="text-[23px] leading-none"
          style={{
            fontFamily: "'Cormorant Garamond', Georgia, serif",
            color: '#eddec8',
            letterSpacing: '0.02em',
          }}
        >
          Kitchen
        </div>
        <div
          className="text-[10px] mt-1"
          style={{ letterSpacing: '0.1em', color: '#46321d' }}
        >
          Home module
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto py-2 px-1.5 space-y-0.5">
        {config.nav_items.map((item) => {
          const isActive = loc.pathname === item.route ||
            (item.route !== '/kitchen' && loc.pathname.startsWith(item.route + '/'))
          const isExactHome = item.route === '/kitchen' && loc.pathname === '/kitchen'
          const active = isActive || isExactHome

          const badgeCount = item.id === 'kitchen-shopping' ? (shoppingData?.count ?? 0) : 0

          return (
            <Link key={item.id} to={item.route as never} className="block">
              <span
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-md text-[12.5px] transition-colors w-full"
                style={{
                  backgroundColor: active ? '#271d12' : 'transparent',
                  color: active ? '#eddec8' : '#7a6a58',
                }}
              >
                {resolveIcon(item.icon, 14)}
                <span className="flex-1 truncate">{item.label}</span>
                {badgeCount > 0 && (
                  <span
                    className="text-[9px] font-medium px-1.5 py-px rounded-full"
                    style={{
                      backgroundColor: active ? '#4a3015' : '#3a2510',
                      color: active ? '#eddec8' : '#c8935a',
                    }}
                  >
                    {badgeCount}
                  </span>
                )}
              </span>
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
