/**
 * Circuit list view — browse and manage all circuits.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Trash2, CircuitBoard } from 'lucide-react'
import { electronicsApi } from '../api'
import { useState } from 'react'

export function ElectronicsCircuits() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [newName, setNewName] = useState('')

  const { data } = useQuery({
    queryKey: ['electronics-circuits'],
    queryFn: electronicsApi.listCircuits,
  })

  const createMutation = useMutation({
    mutationFn: (name: string) => electronicsApi.createCircuit({ name }),
    onSuccess: (circuit) => {
      queryClient.invalidateQueries({ queryKey: ['electronics-circuits'] })
      navigate({ to: `/electronics/circuits/${circuit.id}` })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: electronicsApi.deleteCircuit,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['electronics-circuits'] })
    },
  })

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Circuits</h1>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Name..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                createMutation.mutate(newName.trim() || 'Untitled Circuit')
                setNewName('')
              }
            }}
            className="rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm w-48"
          />
          <button
            onClick={() => {
              createMutation.mutate(newName.trim() || 'Untitled Circuit')
              setNewName('')
            }}
            className="flex items-center gap-1 rounded-md bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-500"
          >
            <Plus size={14} />
            New
          </button>
        </div>
      </div>

      {data?.items.length === 0 && (
        <p className="text-sm text-zinc-400">No circuits yet.</p>
      )}

      <div className="space-y-2">
        {data?.items.map((circuit) => (
          <div
            key={circuit.id}
            className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-800/50 p-3 hover:bg-zinc-800 transition-colors"
          >
            <button
              onClick={() => navigate({ to: `/electronics/circuits/${circuit.id}` })}
              className="flex flex-1 items-center gap-3 text-left min-w-0"
            >
              <CircuitBoard size={18} className="text-sky-400 shrink-0" />
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">{circuit.name}</div>
                <div className="text-xs text-zinc-400">
                  Updated {new Date(circuit.updated_at).toLocaleDateString()}
                </div>
              </div>
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation()
                if (confirm(`Delete "${circuit.name}"?`)) {
                  deleteMutation.mutate(circuit.id)
                }
              }}
              className="p-1.5 rounded text-zinc-500 hover:text-red-400 hover:bg-zinc-700"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
