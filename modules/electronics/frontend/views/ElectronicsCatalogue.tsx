/**
 * ElectronicsCatalogue — browse and manage component models in the catalogue.
 *
 * Lists Material primitives from the Core catalogue filtered to electronics domain.
 * Supports seeding built-in presets and creating new models from SPICE parameters.
 */
import { useState, useEffect, useCallback } from 'react'
import { electronicsApi, type CatalogueModel } from '../api'

const COMPONENT_TYPES = [
  { value: '', label: 'All types' },
  { value: 'diode', label: 'Diode' },
  { value: 'zener', label: 'Zener' },
  { value: 'led', label: 'LED' },
  { value: 'npn_bjt', label: 'NPN BJT' },
  { value: 'pnp_bjt', label: 'PNP BJT' },
  { value: 'nmos', label: 'NMOS' },
  { value: 'pmos', label: 'PMOS' },
]

const TYPE_COLORS: Record<string, string> = {
  diode: '#f59e0b',
  zener: '#f97316',
  led: '#10b981',
  npn_bjt: '#3b82f6',
  pnp_bjt: '#6366f1',
  nmos: '#8b5cf6',
  pmos: '#a855f7',
}

export function ElectronicsCatalogue() {
  const [models, setModels] = useState<CatalogueModel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [search, setSearch] = useState('')
  const [seedStatus, setSeedStatus] = useState<string | null>(null)
  const [selected, setSelected] = useState<CatalogueModel | null>(null)

  const fetchModels = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: { component_type?: string; search?: string } = {}
      if (typeFilter) params.component_type = typeFilter
      if (search) params.search = search
      const resp = await electronicsApi.listCatalogueModels(params)
      setModels(resp.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load catalogue models')
      setModels([])
    } finally {
      setLoading(false)
    }
  }, [typeFilter, search])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  const handleSeed = async () => {
    setSeedStatus('Seeding...')
    try {
      const result = await electronicsApi.seedCatalogue()
      setSeedStatus(`Seeded ${result.seeded} models, skipped ${result.skipped}`)
      if (result.errors.length > 0) {
        setSeedStatus(prev => `${prev} (${result.errors.length} errors)`)
      }
      fetchModels()
    } catch (err) {
      setSeedStatus(`Error: ${err instanceof Error ? err.message : 'unknown'}`)
    }
  }

  return (
    <div className="flex h-full" style={{ backgroundColor: '#0a1628', color: '#94a3b8' }}>
      {/* Left panel — model list */}
      <div className="flex flex-col w-80 border-r border-white/10">
        {/* Header */}
        <div className="px-4 py-4 border-b border-white/10">
          <h2 className="text-lg font-semibold" style={{ color: '#e2e8f0' }}>
            Component Catalogue
          </h2>
          <p className="text-xs mt-1 opacity-60">
            SPICE models from the catalogue
          </p>
        </div>

        {/* Filters */}
        <div className="px-4 py-3 space-y-2 border-b border-white/10">
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
            className="w-full rounded px-2 py-1.5 text-sm"
            style={{ backgroundColor: '#1e293b', color: '#e2e8f0', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            {COMPONENT_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Search models..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full rounded px-2 py-1.5 text-sm"
            style={{ backgroundColor: '#1e293b', color: '#e2e8f0', border: '1px solid rgba(255,255,255,0.1)' }}
          />
        </div>

        {/* Seed button */}
        <div className="px-4 py-2 border-b border-white/10">
          <button
            onClick={handleSeed}
            className="w-full rounded px-3 py-1.5 text-sm font-medium transition-colors"
            style={{ backgroundColor: '#38bdf8', color: '#0a1628' }}
          >
            Seed Built-in Presets
          </button>
          {seedStatus && (
            <p className="text-xs mt-1 opacity-70">{seedStatus}</p>
          )}
        </div>

        {/* Model list */}
        <div className="flex-1 overflow-y-auto">
          {loading && <p className="px-4 py-3 text-sm opacity-50">Loading...</p>}
          {error && <p className="px-4 py-3 text-sm text-red-400">{error}</p>}
          {!loading && !error && models.length === 0 && (
            <p className="px-4 py-3 text-sm opacity-50">
              No models found. Try seeding built-in presets.
            </p>
          )}
          {models.map(model => (
            <button
              key={model.catalogue_path}
              onClick={() => setSelected(model)}
              className="w-full text-left px-4 py-3 border-b border-white/5 transition-colors"
              style={{
                backgroundColor: selected?.catalogue_path === model.catalogue_path ? '#1e293b' : 'transparent',
              }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ backgroundColor: TYPE_COLORS[model.component_type] || '#64748b' }}
                />
                <span className="text-sm font-medium" style={{ color: '#e2e8f0' }}>
                  {model.name}
                </span>
              </div>
              <div className="text-xs opacity-50 mt-0.5">
                {model.component_type.replace('_', ' ')}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right panel — model detail */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selected ? (
          <div className="flex items-center justify-center h-full opacity-30">
            <p>Select a model to view details</p>
          </div>
        ) : (
          <div>
            <div className="flex items-center gap-3 mb-4">
              <span
                className="inline-block px-2 py-0.5 rounded text-xs font-medium"
                style={{
                  backgroundColor: TYPE_COLORS[selected.component_type] || '#64748b',
                  color: '#0a1628',
                }}
              >
                {selected.component_type.replace('_', ' ').toUpperCase()}
              </span>
              <h2 className="text-xl font-semibold" style={{ color: '#e2e8f0' }}>
                {selected.name}
              </h2>
            </div>

            {selected.description && (
              <p className="text-sm mb-4 opacity-70">{selected.description}</p>
            )}

            <div className="mb-4">
              <h3 className="text-sm font-medium mb-2" style={{ color: '#e2e8f0' }}>
                Catalogue Path
              </h3>
              <code className="text-xs px-2 py-1 rounded" style={{ backgroundColor: '#1e293b' }}>
                {selected.catalogue_path}
              </code>
            </div>

            <div className="mb-4">
              <h3 className="text-sm font-medium mb-2" style={{ color: '#e2e8f0' }}>
                SPICE Parameters
              </h3>
              <div
                className="rounded p-3"
                style={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.1)' }}
              >
                <table className="w-full text-sm">
                  <thead>
                    <tr className="opacity-50">
                      <th className="text-left py-1 pr-4">Parameter</th>
                      <th className="text-right py-1">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(selected.spice_params).map(([key, val]) => (
                      <tr key={key} className="border-t border-white/5">
                        <td className="py-1.5 pr-4 font-mono text-xs" style={{ color: '#38bdf8' }}>
                          {key}
                        </td>
                        <td className="py-1.5 text-right font-mono text-xs">
                          {typeof val === 'number' ? val.toExponential(3) : String(val)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {selected.tags.length > 0 && (
              <div>
                <h3 className="text-sm font-medium mb-2" style={{ color: '#e2e8f0' }}>
                  Tags
                </h3>
                <div className="flex gap-1 flex-wrap">
                  {selected.tags.map(tag => (
                    <span
                      key={tag}
                      className="text-xs px-2 py-0.5 rounded"
                      style={{ backgroundColor: '#1e293b' }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
