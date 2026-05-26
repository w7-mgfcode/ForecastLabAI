/**
 * PRP-41 — post-run "Inspect Artifacts" panel for the Showcase page.
 *
 * Renders a grid of 10 deep-link cards covering every surface the demo
 * touches. Each card is disabled (with a tooltip-style hint) when the
 * required step.data ids are missing.
 */

import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ROUTES } from '@/lib/constants'
import type { DemoStep, DemoSummary } from '@/hooks/use-demo-pipeline'

interface InspectCard {
  label: string
  blurb: string
  href: string | null
  disabledReason?: string
}

interface InspectArtifactsPanelProps {
  steps: DemoStep[]
  summary: DemoSummary
}

function readGrain(steps: DemoStep[]): { store_id: number | null; product_id: number | null } {
  const status = steps.find((s) => s.name === 'status')
  return {
    store_id: typeof status?.data.store_id === 'number' ? status.data.store_id : null,
    product_id: typeof status?.data.product_id === 'number' ? status.data.product_id : null,
  }
}

function buildCards(steps: DemoStep[], summary: DemoSummary): InspectCard[] {
  const byName = new Map<string, DemoStep>()
  for (const s of steps) byName.set(s.name, s)
  const { store_id, product_id } = readGrain(steps)

  const train = byName.get('train')
  const backtest = byName.get('backtest')
  const v2 = byName.get('v2_train')
  const batch = byName.get('batch_preset')
  const scenario = byName.get('scenario_simulate_and_save')
  const compat = byName.get('champion_compat_compare')
  const ragIndex = byName.get('rag_index_subset')
  const hitl = byName.get('agent_hitl_flow')

  const cards: InspectCard[] = []

  // 1. Forecast deep link.
  cards.push({
    label: 'Forecast (V1+V2 ready)',
    blurb: 'Visualize the trained model on the showcase grain.',
    href:
      store_id !== null && product_id !== null && train?.status === 'pass'
        ? `${ROUTES.VISUALIZE.FORECAST}?store_id=${store_id}&product_id=${product_id}`
        : null,
    disabledReason: 'Train step did not surface a grain.',
  })
  // 2. Backtest deep link.
  cards.push({
    label: 'Backtest with horizon buckets',
    blurb: 'RMSE + per-bucket WAPE for the winning model.',
    href:
      store_id !== null && product_id !== null && backtest?.status === 'pass'
        ? `${ROUTES.VISUALIZE.BACKTEST}?store_id=${store_id}&product_id=${product_id}`
        : null,
    disabledReason: 'Backtest step did not surface a grain.',
  })
  // 3. Portfolio batch.
  {
    const batchId = typeof batch?.data.batch_id === 'string' ? batch.data.batch_id : null
    cards.push({
      label: 'Portfolio sweep',
      blurb: 'Run-by-run results for the batch preset.',
      href: batchId ? `${ROUTES.VISUALIZE.BATCH}/${batchId}` : null,
      disabledReason: 'Batch preset step skipped or failed.',
    })
  }
  // 4. Saved scenario plans.
  {
    const sid = typeof scenario?.data.scenario_id === 'string' ? scenario.data.scenario_id : null
    cards.push({
      label: 'Saved scenario plans',
      blurb: 'The price-cut plan saved during the planning phase.',
      href: sid ? `${ROUTES.VISUALIZE.PLANNER}?scenario_id=${sid}` : ROUTES.VISUALIZE.PLANNER,
    })
  }
  // 5. Multi-run registry.
  cards.push({
    label: 'Multi-run registry',
    blurb: 'Every run registered across this pipeline run.',
    href: ROUTES.EXPLORER.RUNS,
  })
  // 6. V2 feature frame.
  {
    const v2Run = summary.v2RunId ?? (typeof v2?.data.v2_run_id === 'string' ? v2.data.v2_run_id : null)
    cards.push({
      label: 'V2 Feature Frame panel',
      blurb: 'Inspect feature groups + safety classes for the V2 winner.',
      href: v2Run ? `${ROUTES.EXPLORER.RUNS}/${v2Run}` : null,
      disabledReason: 'V2 train step skipped or failed.',
    })
  }
  // 7. Champion-compat compare.
  {
    const v1 = typeof compat?.data.v1_run_id === 'string' ? compat.data.v1_run_id : null
    const v2id = typeof compat?.data.v2_run_id === 'string' ? compat.data.v2_run_id : null
    cards.push({
      label: '"Not comparable" diff',
      blurb: 'Side-by-side V1 vs V2 with the comparability verdict.',
      href:
        v1 && v2id ? `${ROUTES.EXPLORER.RUN_COMPARE}?a=${v1}&b=${v2id}` : null,
      disabledReason: 'Champion-compat compare step skipped.',
    })
  }
  // 8. Ops — stale alias + Model Health.
  cards.push({
    label: 'Stale-alias + Model Health',
    blurb: 'Operator-side view of staleness and drift.',
    href: ROUTES.OPS,
  })
  // 9. Indexed corpus.
  {
    const chunks =
      ragIndex && typeof ragIndex.data.total_chunks === 'number' ? ragIndex.data.total_chunks : 0
    cards.push({
      label: 'Indexed corpus + search probe',
      blurb: 'The 5 user-guide docs indexed by the knowledge phase.',
      href: chunks > 0 ? ROUTES.KNOWLEDGE : null,
      disabledReason: 'RAG index skipped (embedding provider unreachable).',
    })
  }
  // 10. Agent transcript.
  {
    const sid =
      typeof hitl?.data.session_id === 'string' && hitl.data.session_id
        ? hitl.data.session_id
        : null
    cards.push({
      label: 'Agent transcript',
      blurb: 'The HITL approval round-trip the agent ran.',
      href: sid ? ROUTES.CHAT : null,
      disabledReason: 'Agent HITL skipped (no LLM key).',
    })
  }

  return cards
}

export function InspectArtifactsPanel({ steps, summary }: InspectArtifactsPanelProps) {
  const cards = buildCards(steps, summary)
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <h2 className="text-lg font-semibold">Inspect what just happened</h2>
        <p className="text-sm text-muted-foreground">
          Deep-link into every artifact this run produced. Cards greyed out when
          the matching step skipped or failed.
        </p>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {cards.map((card) => {
            const isActive = typeof card.href === 'string' && card.href.length > 0
            return (
              <div
                key={card.label}
                className={isActive ? '' : 'opacity-50'}
                title={isActive ? undefined : card.disabledReason}
              >
                {isActive ? (
                  <Link
                    to={card.href!}
                    className="block h-full rounded-md border p-3 transition-colors hover:bg-muted"
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-sm font-semibold">{card.label}</span>
                      <ArrowUpRight className="h-3 w-3 shrink-0" />
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{card.blurb}</p>
                  </Link>
                ) : (
                  <div className="block h-full cursor-not-allowed rounded-md border p-3">
                    <div className="text-sm font-semibold">{card.label}</div>
                    <p className="mt-1 text-xs text-muted-foreground">{card.blurb}</p>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
