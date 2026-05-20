import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { FeatureMetadataResponse } from '@/types/api'

/**
 * Load feature columns + learned importance for a registry run (MLZOO-D).
 *
 * Disabled until `runId` is set; `retry: false` because every error path
 * — 400 (baseline family), 404 (missing run), 422 (no artifact / missing
 * extra / HistGBR-no-importance gap) — is a final answer, not a transient.
 * Mirrors `useRunExplanation` (PRP-28) exactly so future maintainers see
 * the run-keyed/job-keyed pair as a structural twin.
 */
export function useRunFeatureMetadata(runId: string, enabled = true) {
  return useQuery({
    queryKey: ['feature-metadata', 'run', runId],
    queryFn: () =>
      api<FeatureMetadataResponse>(`/forecasting/runs/${runId}/feature-metadata`),
    enabled: enabled && !!runId,
    retry: false,
  })
}

/**
 * Load feature columns + learned importance for a completed train job.
 *
 * Use this — not {@link useRunFeatureMetadata} — when the caller has only a
 * `job_id`. `trainJob.result.run_id` is the **forecast-artifact key**
 * (`uuid.uuid4().hex[:12]`), NOT a registry UUID; calling
 * `useRunFeatureMetadata(trainJob.result.run_id, ...)` would 404 because the
 * `/forecasting/runs/{run_id}` endpoint treats its path param as a registry
 * UUID. Recorded in memory `[[scenario-run-id-vs-registry-run-id]]`.
 */
export function useJobFeatureMetadata(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ['feature-metadata', 'job', jobId],
    queryFn: () =>
      api<FeatureMetadataResponse>(`/forecasting/jobs/${jobId}/feature-metadata`),
    enabled: enabled && !!jobId,
    retry: false,
  })
}
