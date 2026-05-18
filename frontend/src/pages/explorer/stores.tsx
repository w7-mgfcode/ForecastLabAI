import { useNavigate, useSearchParams } from 'react-router-dom'
import { ColumnDef, OnChangeFn, PaginationState, SortingState } from '@tanstack/react-table'
import { Download } from 'lucide-react'
import { useStores } from '@/hooks/use-stores'
import { DataTable } from '@/components/data-table/data-table'
import { DataTableToolbar } from '@/components/data-table/data-table-toolbar'
import { DataTableColumnHeader } from '@/components/data-table/data-table-column-header'
import { ErrorDisplay } from '@/components/common/error-display'
import { Button } from '@/components/ui/button'
import { toCsv, downloadCsv, type CsvColumn } from '@/lib/csv-export'
import type { Store } from '@/types/api'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'

const columns: ColumnDef<Store>[] = [
  {
    accessorKey: 'id',
    header: 'ID',
    enableSorting: false,
    enableHiding: false,
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.id}</span>,
  },
  {
    accessorKey: 'code',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Code" />,
    cell: ({ row }) => <span className="font-medium">{row.original.code}</span>,
  },
  {
    accessorKey: 'name',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
  },
  {
    accessorKey: 'region',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Region" />,
    cell: ({ row }) => row.original.region ?? '-',
  },
  {
    accessorKey: 'city',
    header: ({ column }) => <DataTableColumnHeader column={column} title="City" />,
    cell: ({ row }) => row.original.city ?? '-',
  },
  {
    accessorKey: 'store_type',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
    cell: ({ row }) => row.original.store_type ?? '-',
  },
]

const csvColumns: CsvColumn<Store>[] = [
  { key: 'id', header: 'ID' },
  { key: 'code', header: 'Code' },
  { key: 'name', header: 'Name' },
  { key: 'region', header: 'Region' },
  { key: 'city', header: 'City' },
  { key: 'store_type', header: 'Type' },
]

export default function StoresExplorerPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // URL query string is the single source of truth for filter/sort/page state,
  // so a pasted URL reproduces the exact view.
  const search = searchParams.get('search') ?? ''
  const region = searchParams.get('region') ?? undefined
  const storeType = searchParams.get('store_type') ?? undefined
  const page = Number(searchParams.get('page')) || 1
  const sortBy = searchParams.get('sort_by') ?? undefined
  const sortOrder: 'asc' | 'desc' = searchParams.get('sort_order') === 'desc' ? 'desc' : 'asc'

  const pagination: PaginationState = {
    pageIndex: page - 1,
    pageSize: DEFAULT_PAGE_SIZE,
  }
  const sorting: SortingState = sortBy ? [{ id: sortBy, desc: sortOrder === 'desc' }] : []

  const { data, isLoading, error, refetch } = useStores({
    page,
    pageSize: pagination.pageSize,
    search: search.length >= 2 ? search : undefined,
    region,
    storeType,
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
    const paramKey = key === 'storeType' ? 'store_type' : key
    updateParams({ [paramKey]: value, page: '1' })
  }

  const handleReset = () => {
    setSearchParams(new URLSearchParams())
  }

  const handleExport = () => {
    downloadCsv('stores.csv', toCsv(data?.stores ?? [], csvColumns))
  }

  const hasActiveFilters = !!search || !!region || !!storeType || !!sortBy

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Stores</h1>
        <ErrorDisplay error={error} onRetry={() => void refetch()} />
      </div>
    )
  }

  const pageCount = data ? Math.ceil(data.total / pagination.pageSize) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Stores</h1>

      <div className="flex flex-wrap items-center justify-between gap-2">
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
          filterValues={{ region, storeType }}
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
        data={data?.stores ?? []}
        pageCount={pageCount}
        pagination={pagination}
        onPaginationChange={handlePaginationChange}
        sorting={sorting}
        onSortingChange={handleSortingChange}
        onRowClick={(store) => navigate(`/explorer/stores/${store.id}`)}
        enableColumnVisibility
        isLoading={isLoading}
        emptyMessage="No stores found."
      />
    </div>
  )
}
