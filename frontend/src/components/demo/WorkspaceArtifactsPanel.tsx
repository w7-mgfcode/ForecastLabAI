/**
 * E4 (#393) — re-attach deep-link card grid for a LOADED workspace.
 *
 * Mirrors InspectArtifactsPanel's card shape but reads the persisted
 * `created_objects` soft references + grain columns from the workspace row
 * instead of live step.data — the run is long gone; the row is the memory.
 */

import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ROUTES } from '@/lib/constants'
import type { WorkspaceDetail } from '@/types/api'

interface ArtifactCard {
  label: string
  blurb: string
  href: string | null
  disabledReason?: string
}

interface WorkspaceArtifactsPanelProps {
  workspace: WorkspaceDetail
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

function buildCards(ws: WorkspaceDetail): ArtifactCard[] {
  const objects = ws.created_objects
  const winningRunId = asString(objects.winning_run_id)
  const v2RunId = asString(objects.v2_run_id)
  const batchId = asString(objects.batch_id)
  const alias = asString(objects.alias)
  const sessionId = asString(objects.agent_session_id)
  const planIds = Array.isArray(objects.scenario_plan_ids)
    ? objects.scenario_plan_ids.filter((id): id is string => typeof id === 'string')
    : []
  const hasGrain = ws.store_id !== null && ws.product_id !== null

  const cards: ArtifactCard[] = []

  cards.push({
    label: 'Winning run',
    blurb: 'Registry detail for the run this workspace promoted.',
    href: winningRunId ? `${ROUTES.EXPLORER.RUNS}/${winningRunId}` : null,
    disabledReason: 'The run never registered a winner.',
  })
  cards.push({
    label: 'V2 feature-frame run',
    blurb: 'The prophet_like V2 run with feature groups + safety classes.',
    href: v2RunId ? `${ROUTES.EXPLORER.RUNS}/${v2RunId}` : null,
    disabledReason: 'No V2 run recorded (demo_minimal flow or v2_train skipped).',
  })
  planIds.forEach((planId, index) => {
    cards.push({
      label: `Scenario plan ${index + 1}`,
      blurb: 'Saved what-if plan from the planning phase.',
      href: `${ROUTES.VISUALIZE.PLANNER}?scenario_id=${planId}`,
    })
  })
  if (planIds.length === 0) {
    cards.push({
      label: 'Scenario plans',
      blurb: 'Saved what-if plans from the planning phase.',
      href: null,
      disabledReason: 'No plans recorded (planning phase skipped or failed).',
    })
  }
  cards.push({
    label: 'Portfolio batch',
    blurb: 'Run-by-run results for the batch preset sweep.',
    href: batchId ? `${ROUTES.VISUALIZE.BATCH}/${batchId}` : null,
    disabledReason: 'No batch recorded (demo_minimal flow or batch skipped).',
  })
  cards.push({
    label: 'Deployment alias',
    blurb: alias ? `Ops view of the ${alias} alias.` : 'Ops view of aliases.',
    href: alias ? ROUTES.OPS : null,
    disabledReason: 'No alias recorded.',
  })
  cards.push({
    label: 'Forecast on grain',
    blurb: 'Visualize the trained model on the recorded showcase grain.',
    href: hasGrain
      ? `${ROUTES.VISUALIZE.FORECAST}?store_id=${ws.store_id}&product_id=${ws.product_id}`
      : null,
    disabledReason: 'The run failed before a grain was discovered.',
  })
  cards.push({
    label: 'Backtest on grain',
    blurb: 'Horizon-bucket metrics on the recorded showcase grain.',
    href: hasGrain
      ? `${ROUTES.VISUALIZE.BACKTEST}?store_id=${ws.store_id}&product_id=${ws.product_id}`
      : null,
    disabledReason: 'The run failed before a grain was discovered.',
  })
  cards.push({
    label: 'Agent session',
    blurb: 'The chat surface — the recorded session has likely expired.',
    href: sessionId ? ROUTES.CHAT : null,
    disabledReason: 'No agent session recorded (no LLM key or step skipped).',
  })

  return cards
}

export function WorkspaceArtifactsPanel({ workspace }: WorkspaceArtifactsPanelProps) {
  const cards = buildCards(workspace)
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <h2 className="text-lg font-semibold">
          Workspace artifacts
          <span className="ml-2 font-mono text-sm text-muted-foreground">
            {workspace.name ?? workspace.workspace_id.slice(0, 8)}
          </span>
        </h2>
        <p className="text-sm text-muted-foreground">
          Everything this kept run created, re-attached from its workspace row.
          Cards greyed out when the run did not record the matching object.
        </p>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
