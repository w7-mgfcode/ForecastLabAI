import { useState } from 'react'
import { CheckCircle2, ShieldAlert } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import type { PromoteRequest } from '@/types/api'
import { PROMOTE_AUDIT_NOTE } from './constants'

const ALIAS_RE = /^[a-z0-9][a-z0-9\-_]*$/

interface PromoteChampionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** True when a non-recommended model was trained (requires explicit ack). */
  isOverride: boolean
  defaultAliasName?: string
  isPromoting: boolean
  /** Error message from the last promote attempt (null on success/idle). */
  promoteError: string | null
  /** The alias name on a successful promotion (null until promoted). */
  promotedAlias: string | null
  onConfirm: (body: PromoteRequest) => void
}

/**
 * Slice C — the approval-gated promote dialog. Requires an approver and a valid
 * alias name; a non-recommended model additionally requires the ack checkbox.
 * Mirrors `forecast-intelligence/promote-confirmation-dialog.tsx`, but calls the
 * model_selection `promote` flow (compare and promote stay separate).
 */
export function PromoteChampionDialog({
  open,
  onOpenChange,
  isOverride,
  defaultAliasName = '',
  isPromoting,
  promoteError,
  promotedAlias,
  onConfirm,
}: PromoteChampionDialogProps) {
  const [aliasName, setAliasName] = useState(defaultAliasName)
  const [approvedBy, setApprovedBy] = useState('')
  const [ack, setAck] = useState(false)

  const aliasValid = ALIAS_RE.test(aliasName.trim())
  const canConfirm =
    aliasValid &&
    approvedBy.trim().length > 0 &&
    (!isOverride || ack) &&
    !isPromoting

  function handleConfirm() {
    if (!canConfirm) return
    onConfirm({
      alias_name: aliasName.trim(),
      approved_by: approvedBy.trim(),
      acknowledge_non_recommended: isOverride ? ack : false,
    })
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setAck(false)
        onOpenChange(next)
      }}
    >
      <AlertDialogContent data-testid="promote-champion-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Promote champion to a registry alias</AlertDialogTitle>
          <AlertDialogDescription>{PROMOTE_AUDIT_NOTE}</AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <label htmlFor="promote-alias-name" className="text-sm font-medium">
              Alias name
            </label>
            <Input
              id="promote-alias-name"
              value={aliasName}
              onChange={(event) => setAliasName(event.target.value)}
              placeholder="e.g. champion-store5-prod8"
              autoComplete="off"
              data-testid="promote-alias-input"
            />
            {aliasName.length > 0 && !aliasValid && (
              <p className="text-xs text-destructive" data-testid="promote-alias-error">
                Lowercase letters, digits, hyphens and underscores only (must start
                with a letter or digit).
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label htmlFor="promote-approved-by" className="text-sm font-medium">
              Approved by
            </label>
            <Input
              id="promote-approved-by"
              value={approvedBy}
              onChange={(event) => setApprovedBy(event.target.value)}
              placeholder="your name"
              autoComplete="off"
              data-testid="promote-approver-input"
            />
          </div>

          {isOverride && (
            <label className="flex items-start gap-2 text-xs" data-testid="promote-ack-row">
              <Checkbox
                checked={ack}
                onCheckedChange={(state) => setAck(state === true)}
                data-testid="promote-ack-checkbox"
              />
              <span className="flex items-start gap-1.5">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                I understand I am promoting a non-recommended model.
              </span>
            </label>
          )}

          {promoteError && (
            <p className="text-xs text-destructive" data-testid="promote-error">
              {promoteError}
            </p>
          )}

          {promotedAlias && (
            <div
              className="flex items-start gap-2 rounded-md border border-success/40 bg-success/10 p-2 text-xs"
              data-testid="promote-success"
            >
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
              Promoted to alias <span className="font-mono">{promotedAlias}</span>.
            </div>
          )}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>Close</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={!canConfirm}
            data-testid="promote-confirm-action"
          >
            {isPromoting ? 'Promoting…' : 'Promote'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
