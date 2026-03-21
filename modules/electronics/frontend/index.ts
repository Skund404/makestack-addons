/**
 * Electronics module frontend — registers panels, views, and app mode with the shell.
 */
import { registerPanel } from '@/modules/panel-registry'
import { registerView } from '@/modules/view-registry'
import { registerAppMode } from '@/modules/app-registry'
import { ElectronicsRecentCircuits } from './panels/ElectronicsRecentCircuits'
import { ElectronicsHome } from './views/ElectronicsHome'
import { ElectronicsCircuits } from './views/ElectronicsCircuits'
import { ElectronicsCircuitEditor } from './views/ElectronicsCircuitEditor'
import { ElectronicsComponents } from './views/ElectronicsComponents'
import { ElectronicsSidebar } from './components/ElectronicsSidebar'

export function registerElectronicsModule(): void {
  // --- App mode (standalone layout) ---
  registerAppMode({
    module_name: 'electronics',
    title: 'Electronics Lab',
    subtitle: 'Circuit simulator',
    sidebar_width: 200,
    home_route: '/electronics',
    nav_items: [
      { id: 'electronics-home',       label: 'Home',       icon: 'Zap',          route: '/electronics' },
      { id: 'electronics-circuits',   label: 'Circuits',   icon: 'CircuitBoard', route: '/electronics/circuits' },
      { id: 'electronics-components', label: 'Components', icon: 'Box',          route: '/electronics/components' },
    ],
    theme: {
      sidebar_bg: '#0a1628',
      sidebar_text: '#94a3b8',
      sidebar_active_bg: '#1e293b',
      accent: '#38bdf8',
    },
    custom_sidebar: ElectronicsSidebar,
  })

  // --- Panels (workshop home) ---
  registerPanel('electronics-recent-circuits', ElectronicsRecentCircuits)

  // --- Views (routes) ---
  registerView('/electronics',              ElectronicsHome)
  registerView('/electronics/circuits',     ElectronicsCircuits)
  registerView('/electronics/circuits/:id', ElectronicsCircuitEditor)
  registerView('/electronics/components',   ElectronicsComponents)
}

export const keywords = {}
