import { Activity, LineChart, TreePine } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ModelFamily } from '@/types/api'

/**
 * MLZOO-D / PRP-31 — Family badge rendered on the runs explorer, run detail,
 * run compare and forecast viz pages. Pure derivation; no hooks, no fetch.
 *
 * Variant + icon map:
 *   baseline → secondary + Activity   (the simple "what-just-happened" family)
 *   tree     → default + TreePine     (the gradient-boosted family)
 *   additive → outline + LineChart    (the prophet_like Ridge family)
 */

interface ModelFamilyBadgeProps {
  family: ModelFamily
  className?: string
}

const FAMILY_LABEL: Record<ModelFamily, string> = {
  baseline: 'Baseline',
  tree: 'Tree',
  additive: 'Additive',
}

const FAMILY_VARIANT: Record<ModelFamily, 'default' | 'secondary' | 'outline'> = {
  baseline: 'secondary',
  tree: 'default',
  additive: 'outline',
}

const FAMILY_ICON: Record<
  ModelFamily,
  typeof Activity | typeof TreePine | typeof LineChart
> = {
  baseline: Activity,
  tree: TreePine,
  additive: LineChart,
}

export function ModelFamilyBadge({ family, className }: ModelFamilyBadgeProps) {
  const Icon = FAMILY_ICON[family]
  return (
    <Badge
      variant={FAMILY_VARIANT[family]}
      className={cn('gap-1', className)}
      data-family={family}
      data-testid="model-family-badge"
    >
      <Icon className="h-3 w-3" aria-hidden />
      {FAMILY_LABEL[family]}
    </Badge>
  )
}
