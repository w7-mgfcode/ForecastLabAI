import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface JsonBlockProps {
  value: unknown
  className?: string
}

// Matches a JSON string (group 1) with an optional key colon (group 2), a
// literal (group 3), or a number (group 4) in pretty-printed JSON.
const JSON_TOKEN =
  /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g

/**
 * Tokenises pretty-printed JSON into syntax-highlighted spans. Token colours use
 * the semantic status tokens — each verified to clear WCAG AA on the muted block
 * background in both light and dark themes.
 */
function highlightJson(json: string): ReactNode[] {
  const out: ReactNode[] = []
  let lastIndex = 0
  let key = 0
  let match: RegExpExecArray | null
  JSON_TOKEN.lastIndex = 0
  while ((match = JSON_TOKEN.exec(json)) !== null) {
    if (match.index > lastIndex) {
      out.push(json.slice(lastIndex, match.index))
    }
    const [token, str, colon, literal, num] = match
    let className = ''
    if (str !== undefined) {
      className = colon ? 'text-info' : 'text-success'
    } else if (literal !== undefined) {
      className = 'text-destructive'
    } else if (num !== undefined) {
      className = 'text-warning'
    }
    out.push(
      <span key={key++} className={className}>
        {token}
      </span>,
    )
    lastIndex = match.index + token.length
  }
  if (lastIndex < json.length) {
    out.push(json.slice(lastIndex))
  }
  return out
}

/**
 * Read-only formatted-JSON viewer. Renders a muted em-dash for null/undefined,
 * otherwise a scrollable, syntax-highlighted <pre> block surfacing run/job
 * JSONB payloads.
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
      {highlightJson(JSON.stringify(value, null, 2))}
    </pre>
  )
}
