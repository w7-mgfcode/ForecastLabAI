import { Crosshair } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useProducts } from '@/hooks/use-products'
import { useSeederStatus } from '@/hooks/use-seeder'
import { useStores } from '@/hooks/use-stores'
import type { UserScope } from '@/types/api'

/**
 * E3 (#409) — store/product focus-pair selector with a pre-run preview.
 *
 * Fed from live /dimensions data (NEVER synthesized ids — Postgres sequences
 * don't reset, so ids are not 1-based). Works without re-seeding: scope
 * selection on the existing dataset is the primary use. The status step
 * validates the pair server-side and warn-falls-back to discovery when it
 * dangles (e.g. after a reset re-issued ids).
 */
interface ScopeSelectorProps {
  value: UserScope | null
  onChange: (value: UserScope | null) => void
  disabled?: boolean
}

// page_size hard cap on /dimensions endpoints is 100.
const PAGE_SIZE = 100

/** "S001 · Main St (North, supermarket)" — label + non-null traits. */
function describeEntity(label: string, traits: Array<string | null>): string {
  const present = traits.filter((t): t is string => t !== null && t !== '')
  return present.length > 0 ? `${label} (${present.join(', ')})` : label
}

export function ScopeSelector({ value, onChange, disabled = false }: ScopeSelectorProps) {
  const storesQuery = useStores({ page: 1, pageSize: PAGE_SIZE })
  const productsQuery = useProducts({ page: 1, pageSize: PAGE_SIZE })
  const { data: seederStatus } = useSeederStatus()

  const stores = storesQuery.data?.stores ?? []
  const products = productsQuery.data?.products ?? []
  const selectedStore = stores.find((s) => s.id === value?.store_id) ?? null
  const selectedProduct = products.find((p) => p.id === value?.product_id) ?? null

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-xs text-muted-foreground">Focus store</span>
          <Select
            value={value?.store_id !== undefined ? String(value.store_id) : ''}
            onValueChange={(v) =>
              onChange({
                store_id: Number(v),
                product_id: value?.product_id ?? products[0]?.id ?? 0,
              })
            }
            disabled={disabled || stores.length === 0}
          >
            <SelectTrigger className="w-56" aria-label="Focus store">
              <SelectValue placeholder="Auto-discover first store" />
            </SelectTrigger>
            <SelectContent>
              {stores.map((store) => (
                <SelectItem key={store.id} value={String(store.id)}>
                  {store.code} · {store.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-xs text-muted-foreground">Focus product</span>
          <Select
            value={value?.product_id !== undefined ? String(value.product_id) : ''}
            onValueChange={(v) =>
              onChange({
                store_id: value?.store_id ?? stores[0]?.id ?? 0,
                product_id: Number(v),
              })
            }
            disabled={disabled || products.length === 0}
          >
            <SelectTrigger className="w-56" aria-label="Focus product">
              <SelectValue placeholder="Auto-discover first product" />
            </SelectTrigger>
            <SelectContent>
              {products.map((product) => (
                <SelectItem key={product.id} value={String(product.id)}>
                  {product.sku} · {product.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        {value !== null && (
          <Button variant="outline" size="sm" disabled={disabled} onClick={() => onChange(null)}>
            Clear focus
          </Button>
        )}
      </div>

      {value !== null && (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-1 py-3 text-sm">
            <span className="flex items-center gap-1 text-muted-foreground">
              <Crosshair data-icon="inline-start" />
              Focus pair
            </span>
            <span>
              {selectedStore
                ? describeEntity(`${selectedStore.code} · ${selectedStore.name}`, [
                    selectedStore.region,
                    selectedStore.store_type,
                  ])
                : `store #${value.store_id}`}
            </span>
            <span>
              {selectedProduct
                ? describeEntity(`${selectedProduct.sku} · ${selectedProduct.name}`, [
                    selectedProduct.category,
                    selectedProduct.brand,
                  ])
                : `product #${value.product_id}`}
            </span>
            {seederStatus?.date_range_start && seederStatus.date_range_end && (
              <span className="text-muted-foreground">
                seeded window {seederStatus.date_range_start} → {seederStatus.date_range_end}
              </span>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
