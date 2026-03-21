/**
 * RecipeBuilder — multi-section recipe form with progressive disclosure.
 *
 * Used by both KitchenRecipeNew (create) and KitchenRecipeEdit (edit).
 * A single "Save" calls createRecipeFull or updateRecipeFull — one API call
 * orchestrates Workflow primitive creation, Material creation, and kitchen rows.
 */
import { useState } from 'react'
import { ArrowLeft, X, ChevronDown, ChevronRight, Plus, ArrowUp, ArrowDown } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { kitchenApi } from '../api'
import type { RecipeFullCreate, RecipeIngredientInput, RecipeDetail } from '../api'
import { IngredientSearch } from './IngredientSearch'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface IngredientRow extends RecipeIngredientInput {
  _key: string  // stable React key
}

interface RecipeBuilderProps {
  /** null = create mode; RecipeDetail = edit mode (pre-populated). */
  existing?: RecipeDetail | null
  onDone: () => void
}

// ---------------------------------------------------------------------------
// Tag editor sub-component
// ---------------------------------------------------------------------------

function TagEditor({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [input, setInput] = useState('')

  const addTag = () => {
    const t = input.trim().toLowerCase()
    if (t && !tags.includes(t)) {
      onChange([...tags, t])
    }
    setInput('')
  }

  return (
    <div className="flex flex-wrap gap-1 items-center">
      {tags.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-accent/10 text-accent rounded-full">
          {tag}
          <button onClick={() => onChange(tags.filter((t) => t !== tag))} className="hover:text-text">
            <X size={8} />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag() } }}
        placeholder="+ Add tag"
        className="px-2 py-0.5 text-[10px] bg-transparent text-text-faint placeholder:text-text-faint focus:outline-none w-20"
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ingredient row sub-component
// ---------------------------------------------------------------------------

function IngredientRowItem({
  ing,
  onChange,
  onRemove,
}: {
  ing: IngredientRow
  onChange: (updated: IngredientRow) => void
  onRemove: () => void
}) {
  return (
    <div className="flex items-center gap-2 py-1.5 border-b border-border/30 last:border-b-0">
      <span className="flex-1 text-xs text-text truncate min-w-0" title={ing.name}>
        {ing.name}
        {!ing.catalogue_path && (
          <span className="text-[9px] text-accent ml-1">(new)</span>
        )}
      </span>
      <input
        type="number"
        value={ing.quantity}
        onChange={(e) => onChange({ ...ing, quantity: parseFloat(e.target.value) || 0 })}
        min="0"
        step="any"
        className="w-14 px-1.5 py-1 text-xs rounded border border-border bg-bg text-text text-center focus:outline-none focus:border-accent/50"
      />
      <input
        type="text"
        value={ing.unit}
        onChange={(e) => onChange({ ...ing, unit: e.target.value })}
        placeholder="unit"
        className="w-14 px-1.5 py-1 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
      />
      <button onClick={onRemove} className="text-text-faint hover:text-red-400 shrink-0">
        <X size={12} />
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CatalogueSearch for techniques/tools (simpler version)
// ---------------------------------------------------------------------------

function CatalogueItemSearch({
  type,
  items,
  onAdd,
  onRemove,
  label,
}: {
  type: string
  items: string[]
  onAdd: (path: string, name: string) => void
  onRemove: (path: string) => void
  label: string
}) {
  return (
    <div>
      <IngredientSearch
        placeholder={`Search ${label.toLowerCase()}...`}
        onSelect={(r) => {
          if (r.catalogue_path && !items.includes(r.catalogue_path)) {
            onAdd(r.catalogue_path, r.name)
          }
        }}
      />
      {items.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {items.map((path) => {
            const name = path.split('/').slice(-2, -1)[0]?.split('-').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') || path
            return (
              <span key={path} className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-surface-el text-text-muted rounded border border-border">
                {name}
                <button onClick={() => onRemove(path)} className="hover:text-red-400">
                  <X size={8} />
                </button>
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main RecipeBuilder
// ---------------------------------------------------------------------------

let _keyCounter = 0
function nextKey() { return `ing_${++_keyCounter}` }

export function RecipeBuilder({ existing, onDone }: RecipeBuilderProps) {
  const queryClient = useQueryClient()
  const isEdit = !!existing

  // Form state
  const [title, setTitle] = useState(existing?.title ?? '')
  const [description, setDescription] = useState(existing?.description ?? '')
  const [cuisineTag, setCuisineTag] = useState(existing?.cuisine_tag ?? '')
  const [prepTime, setPrepTime] = useState<string>(existing?.prep_time_mins?.toString() ?? '')
  const [cookTime, setCookTime] = useState<string>(existing?.cook_time_mins?.toString() ?? '')
  const [servings, setServings] = useState<string>(existing?.servings?.toString() ?? '1')
  const [difficulty, setDifficulty] = useState('')
  const [notes, setNotes] = useState(existing?.notes ?? '')
  const [tags, setTags] = useState<string[]>([])
  const [steps, setSteps] = useState<string[]>([])
  const [techniques, setTechniques] = useState<string[]>([])
  const [tools, setTools] = useState<string[]>([])

  // Ingredients
  const [ingredients, setIngredients] = useState<IngredientRow[]>(() => {
    if (existing?.ingredients) {
      return existing.ingredients.map((ing) => ({
        _key: nextKey(),
        catalogue_path: ing.catalogue_path || null,
        name: ing.name,
        quantity: ing.quantity,
        unit: ing.unit,
        notes: ing.notes,
      }))
    }
    return []
  })

  // Collapsed sections
  const [techOpen, setTechOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)

  // Saving
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const addIngredient = (result: { catalogue_path: string | null; name: string }) => {
    setIngredients((prev) => [
      ...prev,
      { _key: nextKey(), catalogue_path: result.catalogue_path, name: result.name, quantity: 1, unit: '', notes: '' },
    ])
  }

  const updateIngredient = (key: string, updated: IngredientRow) => {
    setIngredients((prev) => prev.map((i) => (i._key === key ? updated : i)))
  }

  const removeIngredient = (key: string) => {
    setIngredients((prev) => prev.filter((i) => i._key !== key))
  }

  // Steps
  const addStep = () => setSteps((prev) => [...prev, ''])
  const updateStep = (idx: number, value: string) => {
    setSteps((prev) => prev.map((s, i) => (i === idx ? value : s)))
  }
  const removeStep = (idx: number) => {
    setSteps((prev) => prev.filter((_, i) => i !== idx))
  }
  const moveStep = (idx: number, dir: -1 | 1) => {
    setSteps((prev) => {
      const next = [...prev]
      const target = idx + dir
      if (target < 0 || target >= next.length) return prev
      ;[next[idx], next[target]] = [next[target], next[idx]]
      return next
    })
  }

  const handleSave = async () => {
    if (!title.trim()) return
    setSaving(true)
    setError('')

    const payload: RecipeFullCreate = {
      title: title.trim(),
      description: description.trim(),
      cuisine_tag: cuisineTag.trim(),
      prep_time_mins: prepTime ? parseInt(prepTime, 10) : null,
      cook_time_mins: cookTime ? parseInt(cookTime, 10) : null,
      servings: parseInt(servings, 10) || 1,
      difficulty,
      notes: notes.trim(),
      tags,
      steps: steps.filter((s) => s.trim()),
      ingredients: ingredients.map(({ catalogue_path, name, quantity, unit, notes: n }) => ({
        catalogue_path,
        name,
        quantity,
        unit,
        notes: n,
      })),
      techniques,
      tools,
    }

    try {
      if (isEdit && existing) {
        await kitchenApi.updateRecipeFull(existing.id, payload)
      } else {
        await kitchenApi.createRecipeFull(payload)
      }
      await queryClient.invalidateQueries({ queryKey: ['kitchen-recipes'] })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save recipe')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-surface shrink-0">
        <button onClick={onDone} className="text-text-faint hover:text-text transition-colors">
          <ArrowLeft size={16} />
        </button>
        <h2
          className="text-xl flex-1"
          style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
        >
          {isEdit ? 'Edit Recipe' : 'New Recipe'}
        </h2>
        <button
          onClick={handleSave}
          disabled={!title.trim() || saving}
          className="px-4 py-1.5 text-xs font-medium rounded transition-colors disabled:opacity-50"
          style={{ backgroundColor: '#c8935a', color: '#15100b' }}
          data-testid="recipe-save-btn"
        >
          {saving ? 'Saving...' : 'Save Recipe'}
        </button>
      </div>

      {/* Form body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 max-w-2xl">
        {error && (
          <div className="px-3 py-2 text-xs bg-red-500/10 text-red-400 rounded border border-red-500/20">
            {error}
          </div>
        )}

        {/* Title + Description */}
        <div className="space-y-3">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Recipe title"
            className="w-full px-3 py-2 text-sm rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
            data-testid="recipe-title-input"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Short description (optional)"
            rows={2}
            className="w-full px-3 py-2 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50 resize-none"
          />
        </div>

        {/* Details grid */}
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint mb-2">Details</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="block text-[10px] text-text-faint mb-1">Servings</label>
              <input
                type="number"
                value={servings}
                onChange={(e) => setServings(e.target.value)}
                min="1"
                className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
              />
            </div>
            <div>
              <label className="block text-[10px] text-text-faint mb-1">Prep (min)</label>
              <input
                type="number"
                value={prepTime}
                onChange={(e) => setPrepTime(e.target.value)}
                min="0"
                className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
              />
            </div>
            <div>
              <label className="block text-[10px] text-text-faint mb-1">Cook (min)</label>
              <input
                type="number"
                value={cookTime}
                onChange={(e) => setCookTime(e.target.value)}
                min="0"
                className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
              />
            </div>
            <div>
              <label className="block text-[10px] text-text-faint mb-1">Difficulty</label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
              >
                <option value="">—</option>
                <option value="easy">Easy</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
            </div>
          </div>
          <div className="mt-3">
            <label className="block text-[10px] text-text-faint mb-1">Cuisine</label>
            <input
              type="text"
              value={cuisineTag}
              onChange={(e) => setCuisineTag(e.target.value)}
              placeholder="e.g. Italian, Japanese"
              className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
            />
          </div>
          <div className="mt-3">
            <label className="block text-[10px] text-text-faint mb-1">Tags</label>
            <TagEditor tags={tags} onChange={setTags} />
          </div>
        </div>

        {/* Ingredients */}
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint mb-2">Ingredients</p>
          <IngredientSearch onSelect={addIngredient} />
          {ingredients.length > 0 && (
            <div className="mt-2 border border-border rounded divide-y divide-border/30 px-2">
              {ingredients.map((ing) => (
                <IngredientRowItem
                  key={ing._key}
                  ing={ing}
                  onChange={(updated) => updateIngredient(ing._key, updated)}
                  onRemove={() => removeIngredient(ing._key)}
                />
              ))}
            </div>
          )}
          {ingredients.length === 0 && (
            <p className="text-[10px] text-text-faint italic mt-2">Search above to add ingredients</p>
          )}
        </div>

        {/* Techniques (collapsed) */}
        <div>
          <button
            onClick={() => setTechOpen(!techOpen)}
            className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-text-faint hover:text-text transition-colors"
          >
            {techOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            Techniques (optional)
          </button>
          {techOpen && (
            <div className="mt-2">
              <CatalogueItemSearch
                type="technique"
                items={techniques}
                onAdd={(path) => setTechniques((prev) => [...prev, path])}
                onRemove={(path) => setTechniques((prev) => prev.filter((p) => p !== path))}
                label="Techniques"
              />
            </div>
          )}
        </div>

        {/* Equipment (collapsed) */}
        <div>
          <button
            onClick={() => setToolsOpen(!toolsOpen)}
            className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-text-faint hover:text-text transition-colors"
          >
            {toolsOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            Equipment (optional)
          </button>
          {toolsOpen && (
            <div className="mt-2">
              <CatalogueItemSearch
                type="tool"
                items={tools}
                onAdd={(path) => setTools((prev) => [...prev, path])}
                onRemove={(path) => setTools((prev) => prev.filter((p) => p !== path))}
                label="Equipment"
              />
            </div>
          )}
        </div>

        {/* Steps */}
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint mb-2">Steps</p>
          {steps.map((step, idx) => (
            <div key={idx} className="flex items-start gap-2 mb-2">
              <span className="text-[10px] text-text-faint mt-2 w-4 text-right shrink-0">{idx + 1}.</span>
              <textarea
                value={step}
                onChange={(e) => updateStep(idx, e.target.value)}
                rows={2}
                className="flex-1 px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50 resize-none"
                placeholder={`Step ${idx + 1}...`}
              />
              <div className="flex flex-col gap-0.5 shrink-0">
                <button onClick={() => moveStep(idx, -1)} disabled={idx === 0} className="text-text-faint hover:text-text disabled:opacity-30">
                  <ArrowUp size={10} />
                </button>
                <button onClick={() => moveStep(idx, 1)} disabled={idx === steps.length - 1} className="text-text-faint hover:text-text disabled:opacity-30">
                  <ArrowDown size={10} />
                </button>
                <button onClick={() => removeStep(idx)} className="text-text-faint hover:text-red-400 mt-0.5">
                  <X size={10} />
                </button>
              </div>
            </div>
          ))}
          <button
            onClick={addStep}
            className="flex items-center gap-1 text-[10px] text-accent hover:text-accent/80 transition-colors"
          >
            <Plus size={10} /> Add step
          </button>
        </div>

        {/* Notes */}
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint mb-2">Notes</p>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="Additional notes..."
            className="w-full px-3 py-2 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50 resize-none"
          />
        </div>
      </div>
    </div>
  )
}
