/**
 * Kitchen Recipe Detail view.
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, Clock, Users, Star } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Separator } from '@/components/ui/Separator'
import { kitchenApi, fmtQty } from '../api'

interface KitchenRecipeDetailProps {
  id: string
}

function NutritionRow({ label, value, unit }: { label: string; value: number | null; unit: string }) {
  if (value == null) return null
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-text-muted">{label}</span>
      <span className="text-text font-mono">{value.toFixed(1)}{unit}</span>
    </div>
  )
}

function StockBadge({ status }: { status: 'ok' | 'low' | 'missing' }) {
  if (status === 'ok') return <Badge variant="success">OK</Badge>
  if (status === 'low') return <Badge variant="warning">Low</Badge>
  return <Badge variant="danger">Missing</Badge>
}

export function KitchenRecipeDetail({ id }: KitchenRecipeDetailProps) {
  const { data: recipe, isLoading, isError } = useQuery({
    queryKey: ['kitchen-recipe', id],
    queryFn: () => kitchenApi.getRecipe(id),
    staleTime: 60_000,
  })

  const { data: stockCheck } = useQuery({
    queryKey: ['kitchen-stock-check', id],
    queryFn: () => kitchenApi.stockCheck(id),
    staleTime: 60_000,
    enabled: !!recipe,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted gap-2">
        <Loader2 size={16} className="animate-spin" /> Loading…
      </div>
    )
  }

  if (isError || !recipe) {
    return (
      <div className="flex items-center justify-center py-16 text-danger/70 gap-2">
        <AlertCircle size={16} /> Failed to load recipe.
      </div>
    )
  }

  const nut = recipe.nutrition

  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto">
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-start gap-2">
          <h1 className="text-lg font-semibold text-text flex-1">{recipe.title}</h1>
          {recipe.cuisine_tag && <Badge variant="muted">{recipe.cuisine_tag}</Badge>}
          {stockCheck && (
            <Badge variant={stockCheck.can_make ? 'success' : 'muted'}>
              {stockCheck.can_make ? 'Can make' : 'Missing stock'}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-text-faint">
          {recipe.total_time_mins != null && (
            <span className="flex items-center gap-1"><Clock size={10} /> {recipe.total_time_mins}min</span>
          )}
          <span className="flex items-center gap-1"><Users size={10} /> {recipe.servings} serving{recipe.servings !== 1 ? 's' : ''}</span>
          {recipe.cook_summary && recipe.cook_summary.count > 0 && (
            <span>Cooked {recipe.cook_summary.count}×</span>
          )}
          {recipe.cook_summary?.avg_rating != null && (
            <span className="flex items-center gap-1 text-warning">
              <Star size={10} fill="currentColor" /> {recipe.cook_summary.avg_rating.toFixed(1)}
            </span>
          )}
        </div>
        {recipe.description && (
          <p className="text-sm text-text-muted mt-1">{recipe.description}</p>
        )}
      </div>

      <Separator />

      {/* Ingredients */}
      {recipe.ingredients.length > 0 && (
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-text">Ingredients</h2>
          </CardHeader>
          <CardBody className="space-y-1.5">
            {recipe.ingredients.map((ing) => {
              const stockIng = stockCheck?.ingredients.find((i) => i.catalogue_path === ing.catalogue_path)
              return (
                <div key={ing.id} className="flex items-center gap-2 text-sm">
                  <span className="flex-1 text-text">{ing.name}</span>
                  <span className="text-text-muted font-mono">{fmtQty(ing.quantity, ing.unit)}</span>
                  {stockIng && <StockBadge status={stockIng.status} />}
                </div>
              )
            })}
          </CardBody>
        </Card>
      )}

      {/* Nutrition */}
      {nut && (
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-text">Nutrition (per serving)</h2>
          </CardHeader>
          <CardBody className="space-y-1">
            <NutritionRow label="Calories" value={nut.calories} unit=" kcal" />
            <NutritionRow label="Protein" value={nut.protein_g} unit="g" />
            <NutritionRow label="Fat" value={nut.fat_g} unit="g" />
            <NutritionRow label="Carbs" value={nut.carbs_g} unit="g" />
            <NutritionRow label="Fiber" value={nut.fiber_g} unit="g" />
            <NutritionRow label="Sugar" value={nut.sugar_g} unit="g" />
            <NutritionRow label="Sodium" value={nut.sodium_mg} unit="mg" />
            {nut.warnings.length > 0 && (
              <p className="text-xs text-warning mt-2">
                Missing data: {nut.warnings.join(', ')}
              </p>
            )}
          </CardBody>
        </Card>
      )}

      {/* Notes */}
      {recipe.notes && (
        <div>
          <h2 className="text-sm font-semibold text-text mb-1">Notes</h2>
          <p className="text-sm text-text-muted whitespace-pre-line">{recipe.notes}</p>
        </div>
      )}
    </div>
  )
}
