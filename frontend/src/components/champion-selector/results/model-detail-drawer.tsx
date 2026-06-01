import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import type { ModelRankEntry } from '@/types/api'

interface ModelDetailDrawerProps {
  entry: ModelRankEntry | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function fmt(value: number | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value.toFixed(3)
}

const METRIC_KEYS: { key: string; label: string }[] = [
  { key: 'wape', label: 'WAPE' },
  { key: 'smape', label: 'sMAPE' },
  { key: 'mae', label: 'MAE' },
  { key: 'rmse', label: 'RMSE' },
  { key: 'bias', label: 'Bias' },
]

/**
 * Per-model detail drawer (Slice B). Opens from a ranking-row click; shows one
 * candidate's metrics, params, and exclusion reason (read-only).
 */
export function ModelDetailDrawer({ entry, open, onOpenChange }: ModelDetailDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid="model-detail-drawer">
        {entry && (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                {entry.model_type}
                {!entry.included && (
                  <Badge variant="outline">{entry.exclusion_reason ?? 'excluded'}</Badge>
                )}
              </SheetTitle>
              <SheetDescription>
                {entry.rank !== null ? `Ranked #${entry.rank}` : 'Not ranked'}
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-4 px-4 pb-4">
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Metrics</p>
                <table className="w-full text-sm">
                  <tbody>
                    {METRIC_KEYS.map((m) => (
                      <tr key={m.key} className="border-t">
                        <td className="py-1 text-muted-foreground">{m.label}</td>
                        <td className="py-1 text-right tabular-nums">
                          {fmt(entry.metrics?.[m.key])}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Parameters</p>
                <pre className="overflow-x-auto rounded-md bg-muted p-2 text-xs">
                  {JSON.stringify(entry.params, null, 2)}
                </pre>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
