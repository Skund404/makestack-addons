/**
 * Recent circuits panel — for the workshop home dashboard.
 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { CircuitBoard } from 'lucide-react'
import { electronicsApi } from '../api'

export function ElectronicsRecentCircuits() {
  const navigate = useNavigate()
  const { data } = useQuery({
    queryKey: ['electronics-circuits'],
    queryFn: electronicsApi.listCircuits,
  })

  const circuits = data?.items.slice(0, 5) || []

  return (
    <div className="p-4">
      <h3 className="text-sm font-medium mb-3">Recent Circuits</h3>
      {circuits.length === 0 && (
        <p className="text-xs text-zinc-400">No circuits yet</p>
      )}
      <div className="space-y-1.5">
        {circuits.map((c) => (
          <button
            key={c.id}
            onClick={() => navigate({ to: `/electronics/circuits/${c.id}` })}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-left hover:bg-zinc-800 transition-colors"
          >
            <CircuitBoard size={14} className="text-sky-400 shrink-0" />
            <span className="truncate">{c.name}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
