/**
 * Electronics Lab home — recent circuits + create new.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Zap, CircuitBoard, BookOpen } from 'lucide-react'
import { electronicsApi } from '../api'
import { useState } from 'react'

export function ElectronicsHome() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [newName, setNewName] = useState('')

  const { data } = useQuery({
    queryKey: ['electronics-circuits'],
    queryFn: electronicsApi.listCircuits,
  })

  const { data: templates } = useQuery({
    queryKey: ['electronics-templates'],
    queryFn: electronicsApi.listTemplates,
  })

  const createMutation = useMutation({
    mutationFn: (name: string) => electronicsApi.createCircuit({ name }),
    onSuccess: (circuit) => {
      queryClient.invalidateQueries({ queryKey: ['electronics-circuits'] })
      navigate({ to: `/electronics/circuits/${circuit.id}` })
    },
  })

  const templateMutation = useMutation({
    mutationFn: (templateId: string) => electronicsApi.createFromTemplate(templateId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['electronics-circuits'] })
      navigate({ to: `/electronics/circuits/${result.id}` })
    },
  })

  const handleCreate = () => {
    const name = newName.trim() || 'Untitled Circuit'
    createMutation.mutate(name)
    setNewName('')
  }

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center gap-3 mb-6">
        <Zap size={28} className="text-sky-400" />
        <h1 className="text-2xl font-semibold">Electronics Lab</h1>
      </div>

      {/* Quick create */}
      <div className="flex gap-2 mb-8">
        <input
          type="text"
          placeholder="New circuit name..."
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          className="flex-1 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm"
        />
        <button
          onClick={handleCreate}
          disabled={createMutation.isPending}
          className="flex items-center gap-1 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          <Plus size={16} />
          Create
        </button>
      </div>

      {/* Templates */}
      {templates?.items && templates.items.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-medium mb-3 flex items-center gap-2">
            <BookOpen size={18} className="text-sky-400" />
            Templates
          </h2>
          <div className="grid grid-cols-2 gap-2">
            {templates.items.map((t) => (
              <button
                key={t.id}
                onClick={() => templateMutation.mutate(t.id)}
                disabled={templateMutation.isPending}
                className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3 text-left hover:bg-zinc-800 transition-colors"
              >
                <div className="text-xs font-medium truncate">{t.name}</div>
                <div className="text-[10px] text-zinc-500 mt-0.5">{t.description}</div>
                <div className="text-[9px] text-zinc-600 mt-1">{t.component_count} components</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Recent circuits */}
      <h2 className="text-lg font-medium mb-3">Recent Circuits</h2>
      {data?.items.length === 0 && (
        <p className="text-sm text-zinc-400">
          No circuits yet. Create one to get started.
        </p>
      )}
      <div className="space-y-2">
        {data?.items.map((circuit) => (
          <button
            key={circuit.id}
            onClick={() => navigate({ to: `/electronics/circuits/${circuit.id}` })}
            className="flex w-full items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-800/50 p-4 text-left hover:bg-zinc-800 transition-colors"
          >
            <CircuitBoard size={20} className="text-sky-400 shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium truncate">{circuit.name}</div>
              <div className="text-xs text-zinc-400">
                {new Date(circuit.updated_at).toLocaleDateString()}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
