import { useState } from 'react'
import { ColumnDef, PaginationState } from '@tanstack/react-table'
import { useProducts } from '@/hooks/use-products'
import { DataTable } from '@/components/data-table/data-table'
import { DataTableToolbar } from '@/components/data-table/data-table-toolbar'
import { ErrorDisplay } from '@/components/common/error-display'
import { formatCurrency } from '@/lib/api'
import type { Product } from '@/types/api'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'

const columns: ColumnDef<Product>[] = [
  {
    accessorKey: 'id',
    header: 'ID',
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.id}</span>,
  },
  {
    accessorKey: 'sku',
    header: 'SKU',
    cell: ({ row }) => <span className="font-medium">{row.original.sku}</span>,
  },
  {
    accessorKey: 'name',
    header: 'Name',
  },
  {
    accessorKey: 'category',
    header: 'Category',
    cell: ({ row }) => row.original.category ?? '-',
  },
  {
    accessorKey: 'brand',
    header: 'Brand',
    cell: ({ row }) => row.original.brand ?? '-',
  },
  {
    accessorKey: 'base_price',
    header: 'Base Price',
    cell: ({ row }) => formatCurrency(row.original.base_price),
  },
]

export default function ProductsExplorerPage() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  })
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Record<string, string | undefined>>({})

  const { data, isLoading, error, refetch } = useProducts({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
    search: search.length >= 2 ? search : undefined,
    category: filters.category,
    brand: filters.brand,
  })

  const handleFilterChange = (key: string, value: string | undefined) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
    setPagination((prev) => ({ ...prev, pageIndex: 0 }))
  }

  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPagination((prev) => ({ ...prev, pageIndex: 0 }))
  }

  const handleReset = () => {
    setSearch('')
    setFilters({})
    setPagination({ pageIndex: 0, pageSize: DEFAULT_PAGE_SIZE })
  }

  const hasActiveFilters = !!search || Object.values(filters).some(Boolean)

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Products</h1>
        <ErrorDisplay error={error} onRetry={refetch} />
      </div>
    )
  }

  const pageCount = data ? Math.ceil(data.total / pagination.pageSize) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Products</h1>

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
        filterValues={filters}
        onFilterChange={handleFilterChange}
        onReset={handleReset}
        hasActiveFilters={hasActiveFilters}
      />

      <DataTable
        columns={columns}
        data={data?.products ?? []}
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={setPagination}
        isLoading={isLoading}
        emptyMessage="No products found."
      />
    </div>
  )
}
