import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface FilterOption {
  label: string
  value: string
}

interface FilterConfig {
  key: string
  label: string
  options: FilterOption[]
}

interface DataTableToolbarProps {
  searchValue?: string
  onSearchChange?: (value: string) => void
  searchPlaceholder?: string
  filters?: FilterConfig[]
  filterValues?: Record<string, string | undefined>
  onFilterChange?: (key: string, value: string | undefined) => void
  onReset?: () => void
  hasActiveFilters?: boolean
}

export function DataTableToolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Search...',
  filters = [],
  filterValues = {},
  onFilterChange,
  onReset,
  hasActiveFilters = false,
}: DataTableToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {onSearchChange && (
        <Input
          placeholder={searchPlaceholder}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
          className="h-8 w-[150px] lg:w-[250px]"
        />
      )}

      {filters.map((filter) => (
        <Select
          key={filter.key}
          value={filterValues[filter.key] ?? ''}
          onValueChange={(value) => {
            onFilterChange?.(filter.key, value === 'all' ? undefined : value)
          }}
        >
          <SelectTrigger className="h-8 w-[130px]">
            <SelectValue placeholder={filter.label} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All {filter.label}</SelectItem>
            {filter.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ))}

      {hasActiveFilters && onReset && (
        <Button
          variant="ghost"
          onClick={onReset}
          className="h-8 px-2 lg:px-3"
        >
          Reset
          <X className="ml-2 h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
