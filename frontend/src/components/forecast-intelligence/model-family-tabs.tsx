import { Activity, LineChart, TreePine } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { ModelFamily } from '@/types/api'

/**
 * PRP-37 Slice C — segmented model-family picker. Uses the shadcn Tabs
 * primitive as a segmented control (no separate SegmentedControl component
 * exists in the registry — see `.claude/rules/shadcn-ui.md`).
 */

interface ModelFamilyTabsProps {
  family: ModelFamily
  onChange: (family: ModelFamily) => void
  disabled?: boolean
  className?: string
}

const FAMILIES: Array<{
  value: ModelFamily
  label: string
  Icon: typeof Activity
}> = [
  { value: 'baseline', label: 'Baseline', Icon: Activity },
  { value: 'tree', label: 'Tree', Icon: TreePine },
  { value: 'additive', label: 'Additive', Icon: LineChart },
]

export function ModelFamilyTabs({
  family,
  onChange,
  disabled,
  className,
}: ModelFamilyTabsProps) {
  return (
    <Tabs
      value={family}
      onValueChange={(value) => {
        if (disabled) return
        onChange(value as ModelFamily)
      }}
      className={className}
      data-testid="model-family-tabs"
    >
      <TabsList>
        {FAMILIES.map(({ value, label, Icon }) => (
          <TabsTrigger
            key={value}
            value={value}
            disabled={disabled}
            data-testid={`model-family-tab-${value}`}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden />
            {label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
