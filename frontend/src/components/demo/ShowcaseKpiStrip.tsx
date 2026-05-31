/**
 * PRP-41 — top-of-page KPI strip for the Showcase page.
 *
 * Renders 5 tiles derived from the cumulative step.data emitted across the
 * pipeline. Hidden until at least one step has reached a terminal status
 * (anything other than `idle`).
 *
 * Sources:
 *   runs_registered       -- count steps in {register, stale_alias_trigger,
 *                            safer_promote_flow, v2_train} where step.data.run_id is set
 *   aliases_live          -- ops_snapshot.step.data.total_aliases (preferred);
 *                            fallback to counting steps with .data.alias
 *   batch_items_completed -- batch_preset.step.data.completed_items
 *   scenario_plans_saved  -- scenario_simulate_and_save.step.data.scenario_id +
 *                            multi_plan_compare.step.data.winner_scenario_id
 *   rag_chunks_indexed    -- rag_index_subset.step.data.total_chunks
 */

import type { DemoStep } from '@/hooks/use-demo-pipeline'
import { Card, CardContent } from '@/components/ui/card'

const TERMINAL_STATUSES = new Set(['pass', 'fail', 'skip', 'warn'])
const REGISTER_STEP_NAMES = new Set([
  'register',
  'stale_alias_trigger',
  'safer_promote_flow',
  'v2_train',
])

interface KpiStripProps {
  steps: DemoStep[]
}

interface Tile {
  label: string
  value: number | string | null
}

function tilesFromSteps(steps: DemoStep[]): Tile[] {
  const byName = new Map<string, DemoStep>()
  for (const s of steps) byName.set(s.name, s)

  const runsRegistered = steps.filter(
    (s) => REGISTER_STEP_NAMES.has(s.name) && typeof s.data.run_id === 'string',
  ).length

  // Prefer ops_snapshot total_aliases; fallback to per-step alias count.
  const ops = byName.get('ops_snapshot')
  const aliasesFromOps =
    ops && typeof ops.data.total_aliases === 'number' ? ops.data.total_aliases : null
  const aliasesFallback = steps.filter(
    (s) => typeof s.data.alias === 'string' && s.data.alias.length > 0,
  ).length
  const aliasesLive = aliasesFromOps ?? aliasesFallback

  const batch = byName.get('batch_preset')
  const batchCompleted =
    batch && typeof batch.data.completed_items === 'number'
      ? batch.data.completed_items
      : null

  // scenario plans saved = (scenario_simulate_and_save with scenario_id) +
  // (multi_plan_compare with winner_scenario_id AND ranked.length>=2).
  const ssave = byName.get('scenario_simulate_and_save')
  const mcompare = byName.get('multi_plan_compare')
  let plansSaved = 0
  if (ssave && typeof ssave.data.scenario_id === 'string' && ssave.data.scenario_id) plansSaved += 1
  const ranked = mcompare?.data.ranked
  if (
    mcompare &&
    typeof mcompare.data.winner_scenario_id === 'string' &&
    Array.isArray(ranked) &&
    ranked.length >= 2
  ) {
    plansSaved += 1
  }

  const ragIndex = byName.get('rag_index_subset')
  const chunks =
    ragIndex && typeof ragIndex.data.total_chunks === 'number'
      ? ragIndex.data.total_chunks
      : null

  return [
    { label: 'Runs registered', value: runsRegistered },
    { label: 'Aliases live', value: aliasesLive },
    { label: 'Batch items', value: batchCompleted },
    { label: 'Plans saved', value: plansSaved },
    { label: 'RAG chunks', value: chunks },
  ]
}

export function ShowcaseKpiStrip({ steps }: KpiStripProps) {
  const hasAnyTerminal = steps.some((s) => TERMINAL_STATUSES.has(s.status))
  if (!hasAnyTerminal) return null

  const tiles = tilesFromSteps(steps)
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {tiles.map((tile) => (
        <Card key={tile.label}>
          <CardContent className="space-y-1 p-4 text-center">
            <div className="text-xs text-muted-foreground">{tile.label}</div>
            <div className="font-mono text-2xl font-semibold">
              {tile.value === null || tile.value === undefined ? '—' : String(tile.value)}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
