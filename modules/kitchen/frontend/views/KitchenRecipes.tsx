/**
 * Kitchen Recipes view — recipe library with filters.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, BookOpen, Clock } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Card, CardBody } from '@/components/ui/Card'
import { kitchenApi } from '../api'
import type { RecipeListItem } from '../api'

const PAGE_SIZE = 20

function RecipeCard({
  recipe,
  onClick,
}: {
  recipe: RecipeListItem
  onClick: () => void
}) {
  return (
    <Card hoverable onClick={onClick}>
      <CardBody className="space-y-1.5">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-semibold text-text leading-tight">{recipe.title}</h3>
          {recipe.cuisine_tag && <Badge variant="muted">{recipe.cuisine_tag}</Badge>}
        </div>
        <div className="flex items-center gap-3 text-xs text-text-faint">
          {recipe.total_time_mins != null && (
            <span className="flex items-center gap-1">
              <Clock size={10} />
              {recipe.total_time_mins}min
            </span>
          )}
          <span>{recipe.servings} serving{recipe.servings !== 1 ? 's' : ''}</span>
          {recipe.cook_count > 0 && (
            <span>Cooked {recipe.cook_count}×</span>
          )}
        </div>
      </CardBody>
    </Card>
  )
}

export function KitchenRecipes() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-recipes', search, offset],
    queryFn: () => kitchenApi.listRecipes({ search: search || undefined, limit: PAGE_SIZE, offset }),
    staleTime: 60_000,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <BookOpen size={16} className="text-text-muted" />
          <h1 className="text-base font-semibold text-text">Recipes</h1>
          <span className="text-xs text-text-faint">{total}</span>
        </div>
      </div>

      <div className="px-4 pb-3">
        <Input
          placeholder="Search recipes…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOffset(0) }}
          className="max-w-xs"
        />
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {isLoading && (
          <div className="flex items-center justify-center py-16 text-text-muted gap-2">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        )}
        {isError && (
          <div className="flex items-center justify-center py-16 text-danger/70 gap-2">
            <AlertCircle size={16} /> Failed to load recipes.
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-text-faint">
            <BookOpen size={24} className="opacity-30" />
            <p className="text-sm">{search ? 'No recipes match that search.' : 'No recipes yet.'}</p>
          </div>
        )}
        {!isLoading && !isError && items.length > 0 && (
          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {items.map((recipe) => (
                <RecipeCard
                  key={recipe.id}
                  recipe={recipe}
                  onClick={() => void navigate({ to: '/kitchen/recipes/$id', params: { id: recipe.id } })}
                />
              ))}
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 pt-2">
                <Button variant="ghost" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                  Previous
                </Button>
                <span className="text-xs text-text-faint">{currentPage} / {totalPages}</span>
                <Button variant="ghost" size="sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                  Next
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
