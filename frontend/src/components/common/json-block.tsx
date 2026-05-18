import { cn } from '@/lib/utils'

interface JsonBlockProps {
  value: unknown
  className?: string
}

/**
 * Read-only formatted-JSON viewer. Renders a muted em-dash for null/undefined,
 * otherwise a scrollable, pretty-printed <pre> block. Intentionally has no
 * syntax-highlighter dependency — it surfaces run/job JSONB payloads as-is.
 */
export function JsonBlock({ value, className }: JsonBlockProps) {
  if (value === null || value === undefined) {
    return <span className="text-sm text-muted-foreground">—</span>
  }

  return (
    <pre
      className={cn(
        'max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted/40 p-3 font-mono text-xs',
        className,
      )}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}
