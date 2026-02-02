import { useState } from 'react'
import { ColumnDef, PaginationState } from '@tanstack/react-table'
import { useStores } from '@/hooks/use-stores'
import { DataTable } from '@/components/data-table/data-table'
import { DataTableToolbar } from '@/components/data-table/data-table-toolbar'
import { ErrorDisplay } from '@/components/common/error-display'
import type { Store } from '@/types/api'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'

const columns: ColumnDef<Store>[] = [
  {
    accessorKey: 'id',
    header: 'ID',
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.id}</span>,
  },
  {
    accessorKey: 'code',
    header: 'Code',
    cell: ({ row }) => <span className="font-medium">{row.original.code}</span>,
  },
  {
    accessorKey: 'name',
    header: 'Name',
  },
  {
    accessorKey: 'region',
    header: 'Region',
    cell: ({ row }) => row.original.region ?? '-',
  },
  {
    accessorKey: 'city',
    header: 'City',
    cell: ({ row }) => row.original.city ?? '-',
  },
  {
    accessorKey: 'store_type',
    header: 'Type',
    cell: ({ row }) => row.original.store_type ?? '-',
  },
]

export default function StoresExplorerPage() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  })
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Record<string, string | undefined>>({})

  // Convert 0-indexed pageIndex to 1-indexed page for API
  const { data, isLoading, error, refetch } = useStores({
    page: pagination.pageIndex + 1,
    pageSize: pagination.pageSize,
    search: search.length >= 2 ? search : undefined,
    region: filters.region,
    storeType: filters.storeType,
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
        <h1 className="text-3xl font-bold">Stores</h1>
        <ErrorDisplay error={error} onRetry={refetch} />
      </div>
    )
  }

  const pageCount = data ? Math.ceil(data.total / pagination.pageSize) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Stores</h1>

      <DataTableToolbar
        searchValue={search}
        onSearchChange={handleSearchChange}
        searchPlaceholder="Search by code or name..."
        filters={[
          {
            key: 'region',
            label: 'Region',
            options: [
              { label: 'North', value: 'North' },
              { label: 'South', value: 'South' },
              { label: 'East', value: 'East' },
              { label: 'West', value: 'West' },
            ],
          },
          {
            key: 'storeType',
            label: 'Type',
            options: [
              { label: 'Supermarket', value: 'Supermarket' },
              { label: 'Convenience', value: 'Convenience' },
              { label: 'Hypermarket', value: 'Hypermarket' },
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
        data={data?.stores ?? []}
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={setPagination}
        isLoading={isLoading}
        emptyMessage="No stores found."
      />
    </div>
  )
}
