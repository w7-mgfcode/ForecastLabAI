import { useNavigate, useSearchParams } from 'react-router-dom'
import { ColumnDef, OnChangeFn, PaginationState, SortingState } from '@tanstack/react-table'
import { Download } from 'lucide-react'
import { useProducts } from '@/hooks/use-products'
import { DataTable } from '@/components/data-table/data-table'
import { DataTableToolbar } from '@/components/data-table/data-table-toolbar'
import { DataTableColumnHeader } from '@/components/data-table/data-table-column-header'
import { ErrorDisplay } from '@/components/common/error-display'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/api'
import { toCsv, downloadCsv, type CsvColumn } from '@/lib/csv-export'
import { parsePageParam } from '@/lib/url-params'
import type { Product } from '@/types/api'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'

const columns: ColumnDef<Product>[] = [
  {
    accessorKey: 'id',
    header: 'ID',
    enableSorting: false,
    enableHiding: false,
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.id}</span>,
  },
  {
    accessorKey: 'sku',
    header: ({ column }) => <DataTableColumnHeader column={column} title="SKU" />,
    cell: ({ row }) => <span className="font-medium">{row.original.sku}</span>,
  },
  {
    accessorKey: 'name',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
  },
  {
    accessorKey: 'category',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Category" />,
    cell: ({ row }) => row.original.category ?? '-',
  },
  {
    accessorKey: 'brand',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Brand" />,
    cell: ({ row }) => row.original.brand ?? '-',
  },
  {
    accessorKey: 'base_price',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Base Price" />,
    cell: ({ row }) => formatCurrency(row.original.base_price),
  },
]

const csvColumns: CsvColumn<Product>[] = [
  { key: 'id', header: 'ID' },
  { key: 'sku', header: 'SKU' },
  { key: 'name', header: 'Name' },
  { key: 'category', header: 'Category' },
  { key: 'brand', header: 'Brand' },
  { key: 'base_price', header: 'Base Price' },
]

export default function ProductsExplorerPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // URL query string is the single source of truth for filter/sort/page state.
  const search = searchParams.get('search') ?? ''
  const category = searchParams.get('category') ?? undefined
  // Clamp `page` to a positive integer — a hand-edited NaN/negative value
  // would otherwise reach the API as-is.
  const page = parsePageParam(searchParams.get('page'))
  const sortBy = searchParams.get('sort_by') ?? undefined
  const sortOrder: 'asc' | 'desc' = searchParams.get('sort_order') === 'desc' ? 'desc' : 'asc'

  const pagination: PaginationState = {
    pageIndex: page - 1,
    pageSize: DEFAULT_PAGE_SIZE,
  }
  const sorting: SortingState = sortBy ? [{ id: sortBy, desc: sortOrder === 'desc' }] : []

  const { data, isLoading, error, refetch } = useProducts({
    page,
    pageSize: pagination.pageSize,
    search: search.length >= 2 ? search : undefined,
    category,
    sortBy,
    sortOrder: sortBy ? sortOrder : undefined,
  })

  function updateParams(updates: Record<string, string | undefined>) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        if (value === undefined || value === '') next.delete(key)
        else next.set(key, value)
      }
      return next
    })
  }

  const handlePaginationChange: OnChangeFn<PaginationState> = (updater) => {
    const next = typeof updater === 'function' ? updater(pagination) : updater
    updateParams({ page: String(next.pageIndex + 1) })
  }

  const handleSortingChange: OnChangeFn<SortingState> = (updater) => {
    const next = typeof updater === 'function' ? updater(sorting) : updater
    const first = next[0]
    updateParams({
      sort_by: first?.id,
      sort_order: first ? (first.desc ? 'desc' : 'asc') : undefined,
      page: '1',
    })
  }

  const handleSearchChange = (value: string) => {
    updateParams({ search: value || undefined, page: '1' })
  }

  const handleFilterChange = (key: string, value: string | undefined) => {
    updateParams({ [key]: value, page: '1' })
  }

  const handleReset = () => {
    setSearchParams(new URLSearchParams())
  }

  const handleExport = () => {
    downloadCsv('products.csv', toCsv(data?.products ?? [], csvColumns))
  }

  const hasActiveFilters = !!search || !!category || !!sortBy

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Products</h1>
        <ErrorDisplay error={error} onRetry={() => void refetch()} />
      </div>
    )
  }

  const pageCount = data ? Math.ceil(data.total / pagination.pageSize) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Products</h1>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <DataTableToolbar
          searchValue={search}
          onSearchChange={handleSearchChange}
          searchPlaceholder="Search by SKU or name..."
          filters={[
            {
              key: 'category',
              label: 'Category',
              options: [
                { label: 'Beverage', value: 'Beverage' },
                { label: 'Snacks', value: 'Snacks' },
                { label: 'Dairy', value: 'Dairy' },
                { label: 'Grocery', value: 'Grocery' },
              ],
            },
          ]}
          filterValues={{ category }}
          onFilterChange={handleFilterChange}
          onReset={handleReset}
          hasActiveFilters={hasActiveFilters}
        />
        <Button variant="outline" size="sm" className="h-8" onClick={handleExport}>
          <Download className="mr-2 h-4 w-4" />
          Export CSV
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.products ?? []}
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={handlePaginationChange}
        sorting={sorting}
        onSortingChange={handleSortingChange}
        onRowClick={(product) => navigate(`/explorer/products/${product.id}`)}
        enableColumnVisibility
        isLoading={isLoading}
        emptyMessage="No products found."
      />
    </div>
  )
}
