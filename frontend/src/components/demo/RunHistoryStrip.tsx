/**
 * PRP-41 — localStorage-backed FIFO run history (5 entries max).
 *
 * Storage:
 *   key  : forecastlab.showcase.runs.v1   (versioned per R18; future schema
 *                                          changes pick a new key, never collide)
 *   cap  : 5 entries (FIFO eviction)
 *   shape: RunHistoryItem (id, runId, timestamp, scenario, status, wallClockS)
 *
 * SSR-guarded: every read/write checks `typeof window === 'undefined'` and
 * swallows JSON parse / quota-exceeded errors.
 */

import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { safeRandomUUID } from '@/lib/uuid-utils'
import type { DemoRunRequest, ScenarioPreset } from '@/types/api'
import type { DemoSummary } from '@/hooks/use-demo-pipeline'

const STORAGE_KEY = 'forecastlab.showcase.runs.v1'
const HISTORY_CAP = 5

export interface RunHistoryItem {
  id: string
  runId: string | null
  timestamp: string // ISO8601
  scenario: ScenarioPreset
  status: 'pass' | 'fail'
  wallClockS: number
}

function loadHistory(): RunHistoryItem[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as RunHistoryItem[]) : []
  } catch {
    return []
  }
}

function saveHistory(items: RunHistoryItem[]): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch {
    // quota exceeded / private mode -- silently drop.
  }
}

interface RunHistoryStripProps {
  /** Called when the operator clicks Replay on a historical entry. */
  onReplay: (req: DemoRunRequest) => void
  /** Latest pipeline_complete summary. When non-null, append to history once. */
  summary: DemoSummary | null
  /** Current scenario the picker is on. */
  scenario: ScenarioPreset
}

export function RunHistoryStrip({ onReplay, summary, scenario }: RunHistoryStripProps) {
  const [items, setItems] = useState<RunHistoryItem[]>(() => loadHistory())
  const [lastSummary, setLastSummary] = useState<DemoSummary | null>(null)

  // Append exactly once per pipeline_complete summary (R18). Done DURING render
  // (the React "storing information from previous renders" pattern) rather than
  // in an effect — calling setState synchronously inside an effect body causes
  // cascading renders and is flagged by react-hooks/set-state-in-effect.
  // E4 (#393) — kept runs (workspaceId != null) are owned by the server-backed
  // WorkspacePanel; localStorage records ephemeral runs only.
  if (summary && summary !== lastSummary && summary.workspaceId === null) {
    setLastSummary(summary)
    setItems((prev) =>
      [
        {
          id: safeRandomUUID(),
          runId: summary.winningRunId,
          timestamp: new Date().toISOString(),
          scenario,
          status: summary.overallStatus,
          wallClockS: summary.wallClockS,
        },
        ...prev,
      ].slice(0, HISTORY_CAP),
    )
  }

  // Persist the history to localStorage whenever it changes — syncing React
  // state to an external system is the sanctioned use of an effect.
  useEffect(() => {
    saveHistory(items)
  }, [items])

  const clear = useCallback(() => {
    setItems([])
  }, [])

  if (items.length === 0) return null

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Recent runs</h2>
          <Button variant="ghost" size="sm" onClick={clear}>
            Clear
          </Button>
        </div>
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between rounded-md border px-3 py-2 text-xs"
            >
              <div className="flex items-center gap-3 font-mono">
                <span>{new Date(item.timestamp).toLocaleString()}</span>
                <span className="rounded bg-muted px-2 py-0.5">{item.scenario}</span>
                <span
                  className={
                    item.status === 'pass'
                      ? 'text-success font-semibold'
                      : 'text-destructive font-semibold'
                  }
                >
                  {item.status.toUpperCase()}
                </span>
                <span>{item.wallClockS.toFixed(0)}s</span>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  onReplay({
                    scenario: item.scenario,
                    skip_seed: true,
                    reset: false,
                    seed: 42,
                  })
                }
              >
                Replay
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
