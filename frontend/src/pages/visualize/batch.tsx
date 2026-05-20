/**
 * Batch Runner — placeholder page (PRP-33 MVP).
 *
 * Polls the parent batch status while in-flight and renders an items table.
 * Per PRP narrowing: NO slider, NO cancel button, NO retry, NO heatmap, NO
 * promotion panel — each downstream PRP owns one of those surfaces.
 *
 * MVP UX: a tiny submit form (manual scope only) + the live items table.
 * The form is intentionally minimal — the agent / curl is the canonical
 * driver in MVP; this page exists so the work is visible.
 */

import { useState } from 'react'

import { ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { StatusBadge } from '@/components/common/status-badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useBatch, useBatchItems, useSubmitBatch } from '@/hooks/use-batches'
import type { BatchSubmitRequest } from '@/types/api'

export default function BatchRunnerPage() {
  // Last-submitted batch the page tracks. null = nothing yet.
  const [batchId, setBatchId] = useState<string | null>(null)

  // Minimal submit form state — manual scope only (downstream PRP-26 adds
  // region/category/top_revenue/all UIs).
  const [storeIds, setStoreIds] = useState('1')
  const [productIds, setProductIds] = useState('1,2,3')
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2024-04-29')

  const submit = useSubmitBatch()
  const batch = useBatch(batchId)
  const items = useBatchItems({ batchId, pageSize: 50 })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const parseIds = (s: string) =>
      s
        .split(',')
        .map((t) => parseInt(t.trim(), 10))
        .filter((n) => !Number.isNaN(n))

    const payload: BatchSubmitRequest = {
      operation: 'backtest',
      scope: {
        kind: 'manual',
        store_ids: parseIds(storeIds),
        product_ids: parseIds(productIds),
      },
      model_configs: [{ model_type: 'naive', params: {} }],
      start_date: startDate,
      end_date: endDate,
    }
    submit.mutate(payload, {
      onSuccess: (data) => setBatchId(data.batch_id),
    })
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Batch Runner (MVP)</h1>
        <p className="text-muted-foreground text-sm">
          Submit a portfolio batch and watch its (store, product) items
          execute sequentially. This is the PRP-33 placeholder — the
          downstream PRPs add cancel, retry, priority, and the
          champion/heatmap surface.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Submit a manual backtest batch</CardTitle>
          <CardDescription>
            Comma-separated IDs; the runner fans out the cartesian product
            and backtests each pair using the naive baseline.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1">
              <span className="text-sm font-medium">Store IDs</span>
              <Input
                value={storeIds}
                onChange={(e) => setStoreIds(e.target.value)}
              />
            </label>
            <label className="space-y-1">
              <span className="text-sm font-medium">Product IDs</span>
              <Input
                value={productIds}
                onChange={(e) => setProductIds(e.target.value)}
              />
            </label>
            <label className="space-y-1">
              <span className="text-sm font-medium">Start date</span>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </label>
            <label className="space-y-1">
              <span className="text-sm font-medium">End date</span>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </label>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={submit.isPending}>
                {submit.isPending ? 'Submitting…' : 'Submit batch'}
              </Button>
            </div>
          </form>
          {submit.isError && (
            <div className="mt-3">
              <ErrorDisplay error={submit.error as Error} />
            </div>
          )}
        </CardContent>
      </Card>

      {batchId && (
        <Card>
          <CardHeader>
            <CardTitle>Batch {batchId.slice(0, 8)}…</CardTitle>
            {batch.data && (
              <CardDescription>
                Status: <StatusBadge status={batch.data.status} /> ·{' '}
                {batch.data.completed_items}/{batch.data.total_items} completed
                · {batch.data.failed_items} failed
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {items.isLoading ? (
              <LoadingState />
            ) : items.isError ? (
              <ErrorDisplay error={items.error as Error} />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead>Store</TableHead>
                    <TableHead>Product</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">WAPE</TableHead>
                    <TableHead className="text-right">Sample size</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.data?.items.map((item) => (
                    <TableRow key={item.item_id}>
                      <TableCell className="font-mono text-xs">
                        {item.item_id.slice(0, 8)}
                      </TableCell>
                      <TableCell>{item.store_id}</TableCell>
                      <TableCell>{item.product_id}</TableCell>
                      <TableCell>{item.model_type}</TableCell>
                      <TableCell>
                        <StatusBadge status={item.status} />
                      </TableCell>
                      <TableCell className="text-right">
                        {item.metrics?.wape != null
                          ? item.metrics.wape.toFixed(3)
                          : '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        {item.metrics?.sample_size ?? '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                  {items.data?.items.length === 0 && (
                    <TableRow>
                      <TableCell
                        colSpan={7}
                        className="text-muted-foreground py-6 text-center"
                      >
                        No items yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
