import { useState } from 'react'
import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react'
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
import { useVerifyArtifact } from '@/hooks/use-runs'
import { formatPercent } from '@/lib/api'
import type { FeatureFrameVersion, ModelRun } from '@/types/api'

/**
 * PRP-37 Slice C — safer Promote affordance. The button is disabled until
 * every gate is satisfied:
 *
 *   • Artifact verifies (computed_hash === stored_hash).
 *   • If the latest WAPE is HIGHER than the current champion's, the operator
 *     must acknowledge a checkbox explicitly.
 *   • If the latest run's feature_frame_version differs from the champion's,
 *     the operator must acknowledge that this silently changes the contract
 *     the alias represents.
 *
 * The alias-name input is preserved from the prior in-line Promote affordance
 * so muscle memory is unchanged.
 */

interface PromoteConfirmationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  run: ModelRun
  currentChampion?: ModelRun
  defaultAliasName?: string
  onConfirm: (aliasName: string) => Promise<void> | void
  isPromoting?: boolean
}

export function PromoteConfirmationDialog({
  open,
  onOpenChange,
  run,
  currentChampion,
  defaultAliasName = '',
  onConfirm,
  isPromoting,
}: PromoteConfirmationDialogProps) {
  const [aliasName, setAliasName] = useState(defaultAliasName)
  const [worseAcknowledged, setWorseAcknowledged] = useState(false)
  const [versionMismatchAck, setVersionMismatchAck] = useState(false)

  // Only verify while the dialog is open; useVerifyArtifact already gates on
  // its `enabled` argument so a closed dialog does not fetch.
  const verify = useVerifyArtifact(run.run_id, open && !!run.artifact_uri)

  const championWape = currentChampion?.metrics?.wape ?? null
  const runWape = run.metrics?.wape ?? null
  const worseWape =
    championWape !== null &&
    runWape !== null &&
    runWape > championWape

  const verifyFailed = verify.data?.verified === false

  const championVersion: FeatureFrameVersion =
    currentChampion?.feature_frame_version === 2 ? 2 : 1
  const runVersion: FeatureFrameVersion =
    run.feature_frame_version === 2 ? 2 : 1
  const versionMismatch =
    currentChampion !== undefined && championVersion !== runVersion

  const canConfirm =
    aliasName.trim().length > 0 &&
    !verifyFailed &&
    (!worseWape || worseAcknowledged) &&
    (!versionMismatch || versionMismatchAck) &&
    !isPromoting

  async function handleConfirm() {
    if (!canConfirm) return
    await onConfirm(aliasName.trim())
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setWorseAcknowledged(false)
          setVersionMismatchAck(false)
        }
        onOpenChange(next)
      }}
    >
      <AlertDialogContent data-testid="promote-confirmation-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>
            Promote run {run.run_id.slice(0, 8)} to an alias
          </AlertDialogTitle>
          <AlertDialogDescription>
            Point a deployment alias at this run. An existing alias of the
            same name is repointed; the comparable-run rule + artifact
            integrity gate this confirm.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <label
              htmlFor="promote-alias-name-prp37"
              className="text-sm font-medium"
            >
              Alias name
            </label>
            <Input
              id="promote-alias-name-prp37"
              value={aliasName}
              onChange={(event) => setAliasName(event.target.value)}
              placeholder="e.g. production"
              autoComplete="off"
              data-testid="promote-confirmation-alias-input"
            />
          </div>

          {verify.isFetching && (
            <p className="text-muted-foreground text-xs">
              Verifying artifact integrity…
            </p>
          )}

          {verify.data?.verified === true && (
            <div className="border-success/40 bg-success/10 text-foreground flex items-start gap-2 rounded-md border p-2 text-xs">
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
              Artifact verified — checksum matches the registry record.
            </div>
          )}

          {verifyFailed && (
            <div
              className="border-destructive/50 bg-destructive/10 text-destructive flex items-start gap-2 rounded-md border p-2 text-xs"
              data-testid="promote-confirmation-verify-failed"
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <div>
                <p className="font-semibold">Artifact verification failed</p>
                {verify.data?.stored_hash && (
                  <p className="font-mono">
                    stored: {verify.data.stored_hash.slice(0, 16)}…
                  </p>
                )}
                {verify.data?.computed_hash && (
                  <p className="font-mono">
                    computed: {verify.data.computed_hash.slice(0, 16)}…
                  </p>
                )}
                <p className="mt-1">Promotion blocked until the artifact is restored.</p>
              </div>
            </div>
          )}

          {worseWape && (
            <div
              className="border-destructive/50 bg-destructive/10 text-destructive space-y-1.5 rounded-md border p-2 text-xs"
              data-testid="promote-confirmation-worse-wape"
            >
              <p className="font-semibold flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5" />
                Latest WAPE is higher than the current champion
              </p>
              <p>
                Run {run.run_id.slice(0, 8)} WAPE{' '}
                <span className="font-mono">
                  {formatPercent(runWape, 2)}
                </span>{' '}
                vs current champion{' '}
                <span className="font-mono">
                  {formatPercent(championWape, 2)}
                </span>
                . Promoting overrides a better-performing alias.
              </p>
              <label className="flex items-center gap-2">
                <Checkbox
                  checked={worseAcknowledged}
                  onCheckedChange={(state) =>
                    setWorseAcknowledged(state === true)
                  }
                  data-testid="promote-confirmation-worse-ack"
                />
                <span>I understand I am promoting a worse run.</span>
              </label>
            </div>
          )}

          {versionMismatch && (
            <div
              className="border-warning/40 bg-warning/10 text-foreground space-y-1.5 rounded-md border p-2 text-xs"
              data-testid="promote-confirmation-version-mismatch"
            >
              <p className="font-semibold flex items-center gap-1.5">
                <ShieldAlert className="h-3.5 w-3.5 text-warning" />
                Feature frame version mismatch
              </p>
              <p>
                Champion is V{championVersion}; this run is V{runVersion}.
                Promoting silently changes the feature contract this alias
                represents.
              </p>
              <label className="flex items-center gap-2">
                <Checkbox
                  checked={versionMismatchAck}
                  onCheckedChange={(state) =>
                    setVersionMismatchAck(state === true)
                  }
                  data-testid="promote-confirmation-version-ack"
                />
                <span>I understand I am changing the feature contract.</span>
              </label>
            </div>
          )}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => void handleConfirm()}
            disabled={!canConfirm}
            data-testid="promote-confirmation-action"
          >
            {isPromoting ? 'Promoting…' : 'Promote'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
