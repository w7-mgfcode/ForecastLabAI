/**
 * Batch Runner — PRP-34 (bounded concurrency + cooperative cancel).
 *
 * Extends the PRP-33 placeholder with:
 * - a max-parallel ``Slider`` on the submit form (PRP-34: activates
 *   ``batch_job.max_parallel`` — runtime-clamped server-side by
 *   ``Settings.batch_global_max_parallel``);
 * - a ``running_items`` chip on the parent progress card;
 * - a "Cancel batch" ``Button`` + confirmation ``AlertDialog`` that fires
 *   ``DELETE /batch/{batch_id}``.
 *
 * Per PRP narrowing: still NO retry, NO heatmap, NO promotion panel — those
 * are owned by their respective downstream PRPs.
 */

import { useState } from 'react'

import { ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { StatusBadge } from '@/components/common/status-badge'
import { BatchPresetSelect } from '@/components/forecast-intelligence/batch-preset-select'
import {
  buildPresetConfigs,
  type BatchPresetId,
} from '@/components/forecast-intelligence/batch-preset-utils'
import {
  BatchMatrixPicker,
  type MatrixRow,
} from '@/components/forecast-intelligence/batch-matrix-picker'
import { defaultV2Groups } from '@/lib/feature-frame-utils'
import { FEATURE_GROUP_VALUES } from '@/types/api'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  useBatch,
  useBatchItems,
  useCancelBatch,
  useSubmitBatch,
} from '@/hooks/use-batches'
import {
  TERMINAL_BATCH_STATES,
  type BatchModelConfig,
  type BatchSubmitRequest,
} from '@/types/api'

const AVAILABLE_BATCH_MODELS: string[] = [
  'naive',
  'seasonal_naive',
  'moving_average',
  'weighted_moving_average',
  'seasonal_average',
  'regression',
  'lightgbm',
  'xgboost',
  'random_forest',
  'prophet_like',
  'trend_regression_baseline',
]

export default function BatchRunnerPage() {
  // Last-submitted batch the page tracks. null = nothing yet.
  const [batchId, setBatchId] = useState<string | null>(null)

  // Minimal submit form state — manual scope only (downstream PRP-26 adds
  // region/category/top_revenue/all UIs).
  const [storeIds, setStoreIds] = useState('1')
  const [productIds, setProductIds] = useState('1,2,3')
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2024-04-29')
  // PRP-34: per-batch parallelism request (server runtime-clamps by the
  // global cap). Default matches the server's default of 4.
  const [maxParallel, setMaxParallel] = useState(4)
  // PRP-37: sweep matrix — multi-model × multi-feature-pack picker.
  const [preset, setPreset] = useState<BatchPresetId | undefined>(undefined)
  const [matrixRows, setMatrixRows] = useState<MatrixRow[]>([])

  function handlePresetChange(next: BatchPresetId) {
    setPreset(next)
    // Map each preset's BatchModelConfig list into MatrixRow values the
    // BatchMatrixPicker renders. A preset with no feature_frame_version
    // (baseline sweep) maps to V1; otherwise V2 + the preset's groups.
    const configs = buildPresetConfigs(next)
    setMatrixRows(
      configs.map((config) => ({
        model_type: config.model_type,
        feature_frame_version: config.feature_frame_version ?? 1,
        feature_groups: config.feature_groups ?? [],
      })),
    )
  }

  const submit = useSubmitBatch()
  const cancel = useCancelBatch()
  const batch = useBatch(batchId)
  const items = useBatchItems({ batchId, pageSize: 50 })

  const isTerminal = batch.data
    ? TERMINAL_BATCH_STATES.has(batch.data.status)
    : false

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const parseIds = (s: string) =>
      s
        .split(',')
        .map((t) => parseInt(t.trim(), 10))
        .filter((n) => !Number.isNaN(n))

    // PRP-37 — translate the matrix into BatchModelConfig rows. Fall back to
    // the single-naive submit when the matrix is empty (preserves the prior
    // PRP-33/34 default behaviour).
    const matrixConfigs: BatchModelConfig[] = matrixRows.map((row) => {
      const config: BatchModelConfig = {
        model_type: row.model_type as BatchModelConfig['model_type'],
      }
      if (row.feature_frame_version === 2) {
        config.feature_frame_version = 2
        if (row.feature_groups.length > 0) {
          config.feature_groups = row.feature_groups
        }
      }
      return config
    })

    const payload: BatchSubmitRequest = {
      operation: 'backtest',
      scope: {
        kind: 'manual',
        store_ids: parseIds(storeIds),
        product_ids: parseIds(productIds),
      },
      model_configs:
        matrixConfigs.length > 0
          ? matrixConfigs
          : [{ model_type: 'naive', params: {} }],
      start_date: startDate,
      end_date: endDate,
      max_parallel: maxParallel,
    }
    submit.mutate(payload, {
      onSuccess: (data) => setBatchId(data.batch_id),
    })
  }

  function handleCancel() {
    if (!batchId) return
    cancel.mutate(batchId)
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Batch Runner</h1>
        <p className="text-muted-foreground text-sm">
          Submit a portfolio batch and watch its (store, product) items
          execute under a bounded concurrency cap. Cancel in-flight batches
          cooperatively from the progress card.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Submit a manual backtest batch</CardTitle>
          <CardDescription>
            Comma-separated IDs; the runner fans out the cartesian product
            and backtests each pair under the naive baseline.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
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
            <div className="space-y-3 sm:col-span-2">
              {/* PRP-37 — preset Select + matrix picker. Preset prefills the
                  matrix; rows can still be hand-edited afterward. */}
              <div className="space-y-1">
                <span className="text-sm font-medium">Sweep preset</span>
                <BatchPresetSelect
                  value={preset}
                  onChange={handlePresetChange}
                />
                <p className="text-muted-foreground text-xs">
                  Optional. Picking a preset overwrites the matrix below.
                </p>
              </div>
              <div className="space-y-1">
                <span className="text-sm font-medium">
                  Sweep matrix (model × feature frame)
                </span>
                <BatchMatrixPicker
                  availableModels={AVAILABLE_BATCH_MODELS}
                  availableGroups={[...FEATURE_GROUP_VALUES]}
                  defaults={defaultV2Groups()}
                  value={matrixRows}
                  onChange={setMatrixRows}
                />
              </div>
            </div>
            <div className="space-y-2 sm:col-span-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  Max parallel: <span className="font-mono">{maxParallel}</span>
                </span>
                <span
                  className="text-muted-foreground text-xs"
                  title="Effective parallelism = min(this, server global cap)."
                >
                  effective = min(this, server cap)
                </span>
              </div>
              <Slider
                value={[maxParallel]}
                onValueChange={(values) => {
                  const next = values[0]
                  if (typeof next === 'number') setMaxParallel(next)
                }}
                min={1}
                max={8}
                step={1}
                aria-label="Max parallel"
              />
            </div>
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
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle>Batch {batchId.slice(0, 8)}…</CardTitle>
                {batch.data && (
                  <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                    <StatusBadge status={batch.data.status} />
                    <span>
                      {batch.data.completed_items}/{batch.data.total_items} completed
                    </span>
                    <span>· {batch.data.failed_items} failed</span>
                    <span>
                      ·{' '}
                      <Badge variant="outline" className="font-mono">
                        running: {batch.data.running_items}
                      </Badge>
                    </span>
                    {batch.data.effective_max_parallel > 0 && (
                      <span>
                        ·{' '}
                        <Badge variant="outline" className="font-mono">
                          parallel: {batch.data.effective_max_parallel}
                        </Badge>
                      </span>
                    )}
                  </CardDescription>
                )}
              </div>
              {batch.data && (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={isTerminal || cancel.isPending}
                    >
                      {cancel.isPending ? 'Cancelling…' : 'Cancel batch'}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Cancel this batch?</AlertDialogTitle>
                      <AlertDialogDescription>
                        Pending items will be skipped; running items observe
                        the cancel at the next safe yield point. In-flight
                        model fits are uncancellable mid-call, so a long fit
                        may stall the drain.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Keep running</AlertDialogCancel>
                      <AlertDialogAction onClick={handleCancel}>
                        Cancel batch
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
            </div>
            {cancel.isError && (
              <div className="mt-3">
                <ErrorDisplay error={cancel.error as Error} />
              </div>
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
                        {typeof item.metrics?.wape === 'number'
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
