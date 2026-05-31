import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { MODEL_TYPE_LABELS } from './model-type-utils'
import { labelForGroup } from '@/lib/feature-frame-utils'
import type { FeatureGroup, FeatureFrameVersion } from '@/types/api'

/**
 * PRP-37 Slice C — multi-model × multi-feature-pack matrix picker for the
 * batch sweep page. Operator picks which (model, V, groups) tuples to fan
 * out into a BatchSubmitRequest. Capped at `max_rows` to avoid accidentally
 * submitting a 100-row matrix.
 */

export type MatrixRow = {
  model_type: string
  feature_frame_version: FeatureFrameVersion
  feature_groups: FeatureGroup[]
}

interface BatchMatrixPickerProps {
  availableModels: string[]
  availableGroups: FeatureGroup[]
  defaults: FeatureGroup[]
  value: MatrixRow[]
  onChange: (rows: MatrixRow[]) => void
  max_rows?: number
}

const DEFAULT_MAX = 24

export function BatchMatrixPicker({
  availableModels,
  availableGroups,
  defaults,
  value,
  onChange,
  max_rows = DEFAULT_MAX,
}: BatchMatrixPickerProps) {
  const limitReached = value.length >= max_rows

  function isRowEnabled(
    model_type: string,
    version: FeatureFrameVersion,
  ): boolean {
    return value.some(
      (row) =>
        row.model_type === model_type &&
        row.feature_frame_version === version,
    )
  }

  function toggleRow(model_type: string, version: FeatureFrameVersion) {
    const exists = isRowEnabled(model_type, version)
    if (exists) {
      onChange(
        value.filter(
          (row) =>
            !(
              row.model_type === model_type &&
              row.feature_frame_version === version
            ),
        ),
      )
      return
    }
    if (limitReached) return
    const groups = version === 2 ? defaults : []
    onChange([
      ...value,
      { model_type, feature_frame_version: version, feature_groups: groups },
    ])
  }

  function toggleGroupForRow(
    model_type: string,
    version: FeatureFrameVersion,
    group: FeatureGroup,
  ) {
    onChange(
      value.map((row) => {
        if (
          row.model_type !== model_type ||
          row.feature_frame_version !== version
        ) {
          return row
        }
        const has = row.feature_groups.includes(group)
        return {
          ...row,
          feature_groups: has
            ? row.feature_groups.filter((g) => g !== group)
            : [...row.feature_groups, group],
        }
      }),
    )
  }

  function applyDefaultsTo(
    model_type: string,
    version: FeatureFrameVersion,
  ) {
    onChange(
      value.map((row) =>
        row.model_type === model_type &&
        row.feature_frame_version === version
          ? { ...row, feature_groups: defaults }
          : row,
      ),
    )
  }

  return (
    <div className="space-y-3" data-testid="batch-matrix-picker">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground text-xs">
          Rows: <span className="font-mono">{value.length}</span> / {max_rows}
        </span>
        {limitReached && (
          <Badge
            variant="destructive"
            className="text-xs"
            data-testid="batch-matrix-limit-badge"
          >
            Max rows reached
          </Badge>
        )}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Model</TableHead>
            <TableHead>V1 (target-only)</TableHead>
            <TableHead>V2 (feature-aware)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {availableModels.map((model_type) => (
            <TableRow key={model_type}>
              <TableCell className="font-mono text-xs">
                {MODEL_TYPE_LABELS[model_type] ?? model_type}
              </TableCell>
              <TableCell>
                <Checkbox
                  checked={isRowEnabled(model_type, 1)}
                  onCheckedChange={() => toggleRow(model_type, 1)}
                  disabled={
                    !isRowEnabled(model_type, 1) && limitReached
                  }
                  aria-label={`Enable ${model_type} V1`}
                  data-testid={`batch-matrix-cell-${model_type}-v1`}
                />
              </TableCell>
              <TableCell>
                <Checkbox
                  checked={isRowEnabled(model_type, 2)}
                  onCheckedChange={() => toggleRow(model_type, 2)}
                  disabled={
                    !isRowEnabled(model_type, 2) && limitReached
                  }
                  aria-label={`Enable ${model_type} V2`}
                  data-testid={`batch-matrix-cell-${model_type}-v2`}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Per-row feature-group editors (V2 only). */}
      {value
        .filter((row) => row.feature_frame_version === 2)
        .map((row) => (
          <div
            key={`${row.model_type}-v2`}
            className="rounded-md border p-3"
            data-testid={`batch-matrix-row-config-${row.model_type}`}
          >
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">
                {MODEL_TYPE_LABELS[row.model_type] ?? row.model_type}
              </span>
              <Badge variant="default" className="text-xs">
                V2
              </Badge>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => applyDefaultsTo(row.model_type, 2)}
              >
                Reset to defaults
              </Button>
            </div>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 md:grid-cols-3">
              {availableGroups.map((group) => {
                const on = row.feature_groups.includes(group)
                return (
                  <label
                    key={group}
                    className="flex items-center gap-2 text-xs"
                  >
                    <Checkbox
                      checked={on}
                      onCheckedChange={() =>
                        toggleGroupForRow(row.model_type, 2, group)
                      }
                      aria-label={`${row.model_type} ${group}`}
                      data-testid={`batch-matrix-group-${row.model_type}-${group}`}
                    />
                    {labelForGroup(group)}
                  </label>
                )
              })}
            </div>
          </div>
        ))}
    </div>
  )
}
