import { Loader2, X } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'

interface CancelRunDialogProps {
  onConfirm: () => void
  isCancelling?: boolean
  disabled?: boolean
}

/**
 * Cancel-run confirmation (Slice B). Mirrors the batch cancel dialog and reuses
 * the honest pending-skip / running-yield copy.
 */
export function CancelRunDialog({ onConfirm, isCancelling, disabled }: CancelRunDialogProps) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          disabled={disabled || isCancelling}
          data-testid="cancel-run-trigger"
        >
          {isCancelling ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <X className="mr-2 h-4 w-4" />
          )}
          Cancel run
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Cancel this comparison?</AlertDialogTitle>
          <AlertDialogDescription>
            Candidates that haven&apos;t started will be skipped. A candidate
            already mid-fit stops at the next safe point — sklearn / LightGBM
            fits are uncancellable mid-call, so an in-flight fit may finish
            first. Results from candidates that already completed are kept.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep running</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} data-testid="cancel-run-confirm">
            Cancel run
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
