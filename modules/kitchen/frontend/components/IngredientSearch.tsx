/**
 * IngredientSearch — typeahead search against catalogue materials.
 *
 * Debounces user input (300ms), queries the kitchen catalogue search
 * endpoint filtered to type=material, and shows a dropdown of matches.
 * Includes an "Add as new ingredient" option when no exact match exists.
 *
 * Returns { catalogue_path: string | null, name: string } via onSelect.
 */
import { useState, useRef, useEffect } from 'react'
import { Search, Plus } from 'lucide-react'
import { kitchenApi } from '../api'
import type { CatalogueSearchResult } from '../api'

interface IngredientSearchProps {
  onSelect: (result: { catalogue_path: string | null; name: string }) => void
  placeholder?: string
}

export function IngredientSearch({ onSelect, placeholder = 'Search ingredients...' }: IngredientSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CatalogueSearchResult[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const doSearch = (q: string) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (!q.trim()) {
      setResults([])
      setIsOpen(false)
      return
    }
    timerRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const resp = await kitchenApi.searchCatalogue(q, 'material')
        setResults(resp.results.slice(0, 8))
        setIsOpen(true)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 300)
  }

  const handleChange = (value: string) => {
    setQuery(value)
    doSearch(value)
  }

  const handleSelect = (item: CatalogueSearchResult) => {
    onSelect({ catalogue_path: item.path, name: item.name })
    setQuery('')
    setResults([])
    setIsOpen(false)
  }

  const handleAddNew = () => {
    if (!query.trim()) return
    onSelect({ catalogue_path: null, name: query.trim() })
    setQuery('')
    setResults([])
    setIsOpen(false)
  }

  return (
    <div ref={wrapperRef} className="relative">
      <div className="relative">
        <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-faint" />
        <input
          type="text"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onFocus={() => { if (results.length > 0 || query.trim()) setIsOpen(true) }}
          placeholder={placeholder}
          className="w-full pl-7 pr-3 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
          data-testid="ingredient-search-input"
        />
        {loading && (
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2">
            <div className="w-3 h-3 border border-text-faint border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>

      {isOpen && (
        <div className="absolute z-50 w-full mt-1 rounded border border-border bg-surface shadow-lg max-h-48 overflow-y-auto">
          {results.map((item) => (
            <button
              key={item.path}
              onClick={() => handleSelect(item)}
              className="w-full text-left px-3 py-2 text-xs hover:bg-accent/10 transition-colors border-b border-border/30 last:border-b-0"
              data-testid="ingredient-search-result"
            >
              <span className="font-medium text-text">{item.name}</span>
              {item.description && (
                <span className="text-text-faint ml-2 truncate">{item.description}</span>
              )}
            </button>
          ))}

          {query.trim() && (
            <button
              onClick={handleAddNew}
              className="w-full text-left px-3 py-2 text-xs hover:bg-accent/10 transition-colors flex items-center gap-1.5 text-accent"
              data-testid="ingredient-add-new"
            >
              <Plus size={10} />
              Add &ldquo;{query.trim()}&rdquo; as new ingredient
            </button>
          )}

          {!loading && results.length === 0 && query.trim() && (
            <div className="px-3 py-2 text-[10px] text-text-faint italic">
              No existing ingredients found
            </div>
          )}
        </div>
      )}
    </div>
  )
}
