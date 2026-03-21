/**
 * KitchenRecipeNew — thin wrapper that renders RecipeBuilder in create mode.
 */
import { RecipeBuilder } from '../components/RecipeBuilder'

export function KitchenRecipeNew() {
  const handleDone = () => {
    window.history.back()
  }

  return <RecipeBuilder onDone={handleDone} />
}
