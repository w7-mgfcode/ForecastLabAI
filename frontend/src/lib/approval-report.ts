import type { ApprovalResponse } from '@/types/api'

/**
 * Build a human-readable chat report for an approved/rejected agent action.
 *
 * The backend's `POST /approve` returns an {@link ApprovalResponse} for every
 * outcome, but the chat UI previously discarded it — so a click produced no
 * visible result ("nothing returned"). This formats a one-line report for ALL
 * outcomes so the operator always sees what happened:
 *
 * - `executed`                      → the action ran successfully.
 * - approved but `rejected` + error → the action was approved but execution
 *   failed (the backend marks a failed execution `rejected` and puts the cause
 *   in `result.error`).
 * - `rejected` (not approved)       → the operator rejected the action.
 * - `expired`                       → the approval window lapsed before it ran.
 *
 * @param actionLabel - The gated action name (e.g. `create_alias`).
 * @param res - The approval response from the backend.
 * @returns A markdown-ish one-line report for the chat transcript.
 */
export function formatApprovalReport(actionLabel: string, res: ApprovalResponse): string {
  const result =
    res.result && typeof res.result === 'object'
      ? (res.result as Record<string, unknown>)
      : undefined
  const errorDetail =
    result && 'error' in result ? String(result.error) : undefined

  if (res.status === 'executed') {
    return `✅ Approved — \`${actionLabel}\` executed successfully.`
  }
  if (res.approved && errorDetail) {
    return `❌ Approved, but \`${actionLabel}\` could not be executed: ${errorDetail}`
  }
  if (!res.approved) {
    return `🚫 Rejected \`${actionLabel}\`. No action was taken.`
  }
  if (res.status === 'expired') {
    return `⏰ The \`${actionLabel}\` approval expired before it could run.`
  }
  // Defensive fallback: approved, not executed, no error detail.
  return `\`${actionLabel}\` finished with status: ${res.status}.`
}
