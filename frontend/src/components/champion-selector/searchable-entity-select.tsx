import { useState } from 'react'
import { Check, ChevronsUpDown, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

export interface SearchableEntityItem {
  id: number
  primary: string
  secondary?: string
}

interface SearchableEntitySelectProps {
  items: SearchableEntityItem[]
  value: number | null
  onChange: (id: number) => void
  placeholder?: string
  loading?: boolean
  emptyLabel?: string
  /** Forwarded to the trigger button + filter input for scoped test queries. */
  testId?: string
}

/**
 * A combobox built from existing primitives (Popover + Input + a filtered
 * `<button>` list) — the repo ships no `cmdk`/`command` primitive, and Slice A
 * adds no new dependency (LOCKED #6). The list is filtered CLIENT-SIDE over the
 * already-fetched (<= 100) rows, matching both the primary and secondary text.
 */
export function SearchableEntitySelect({
  items,
  value,
  onChange,
  placeholder = 'Select…',
  loading = false,
  emptyLabel = 'No matches',
  testId = 'searchable-entity-select',
}: SearchableEntitySelectProps) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const selected = items.find((item) => item.id === value) ?? null
  const needle = filter.trim().toLowerCase()
  const filtered = needle
    ? items.filter(
        (item) =>
          item.primary.toLowerCase().includes(needle) ||
          (item.secondary?.toLowerCase().includes(needle) ?? false),
      )
    : items

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={loading}
          data-testid={testId}
          className="w-full justify-between font-normal"
        >
          <span className="flex min-w-0 flex-col items-start text-left">
            {selected ? (
              <>
                <span className="truncate">{selected.primary}</span>
                {selected.secondary && (
                  <span className="truncate text-xs text-muted-foreground">
                    {selected.secondary}
                  </span>
                )}
              </>
            ) : (
              <span className="text-muted-foreground">
                {loading ? 'Loading…' : placeholder}
              </span>
            )}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
        <div className="flex items-center gap-2 border-b px-3 py-2">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <Input
            autoFocus
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter…"
            data-testid={`${testId}-filter`}
            className="h-8 border-0 px-0 shadow-none focus-visible:ring-0"
          />
        </div>
        <div className="max-h-64 overflow-y-auto p-1" role="listbox">
          {filtered.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              {emptyLabel}
            </p>
          ) : (
            filtered.map((item) => (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={item.id === value}
                data-testid={`${testId}-option-${item.id}`}
                onClick={() => {
                  onChange(item.id)
                  setFilter('')
                  setOpen(false)
                }}
                className={cn(
                  'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground',
                  item.id === value && 'bg-accent/50',
                )}
              >
                <Check
                  className={cn(
                    'h-4 w-4 shrink-0',
                    item.id === value ? 'opacity-100' : 'opacity-0',
                  )}
                />
                <span className="flex min-w-0 flex-col">
                  <span className="truncate">{item.primary}</span>
                  {item.secondary && (
                    <span className="truncate text-xs text-muted-foreground">
                      {item.secondary}
                    </span>
                  )}
                </span>
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
