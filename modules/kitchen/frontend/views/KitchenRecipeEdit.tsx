/**
 * KitchenRecipeEdit — fetches recipe data and renders RecipeBuilder in edit mode.
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { kitchenApi } from '../api'
import { RecipeBuilder } from '../components/RecipeBuilder'

export function KitchenRecipeEdit({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['kitchen-recipe', id],
    queryFn: () => kitchenApi.getRecipe(id),
  })

  const handleDone = () => {
    window.history.back()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 gap-2 text-text-muted">
        <Loader2 size={14} className="animate-spin" />
        <span className="text-xs">Loading recipe...</span>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="p-4 text-sm text-red-400">
        Failed to load recipe. <button onClick={handleDone} className="text-accent underline ml-1">Go back</button>
      </div>
    )
  }

  return <RecipeBuilder existing={data} onDone={handleDone} />
}
