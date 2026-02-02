import { useState } from 'react'
import { ChevronDown, ChevronRight, Wrench, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import type { ToolCall } from '@/types/api'

interface ToolCallDisplayProps {
  toolCall: ToolCall
  className?: string
}

export function ToolCallDisplay({ toolCall, className }: ToolCallDisplayProps) {
  const [isOpen, setIsOpen] = useState(false)

  const statusIcon = {
    pending: <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />,
    running: <Loader2 className="h-3 w-3 animate-spin text-blue-500" />,
    completed: <CheckCircle2 className="h-3 w-3 text-green-500" />,
    failed: <XCircle className="h-3 w-3 text-red-500" />,
  }

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className={cn('rounded-md border bg-muted/30', className)}
    >
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted/50">
        {isOpen ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
        <Wrench className="h-4 w-4 text-muted-foreground" />
        <span className="font-medium">{toolCall.tool_name}</span>
        <span className="ml-auto">{statusIcon[toolCall.status]}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t px-3 py-2 space-y-2">
          {/* Arguments */}
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">Arguments:</p>
            <pre className="text-xs bg-background rounded p-2 overflow-x-auto">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>

          {/* Result (if completed) */}
          {toolCall.result !== undefined && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Result:</p>
              <pre className="text-xs bg-background rounded p-2 overflow-x-auto max-h-40">
                {typeof toolCall.result === 'string'
                  ? toolCall.result
                  : JSON.stringify(toolCall.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

interface ToolCallProgressProps {
  toolName: string
  status: 'starting' | 'running' | 'completed' | 'failed'
}

export function ToolCallProgress({ toolName, status }: ToolCallProgressProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-muted-foreground bg-muted/30 rounded-md">
      {status === 'running' || status === 'starting' ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : status === 'completed' ? (
        <CheckCircle2 className="h-3 w-3 text-green-500" />
      ) : (
        <XCircle className="h-3 w-3 text-red-500" />
      )}
      <Wrench className="h-3 w-3" />
      <span>
        {status === 'starting' && `Calling ${toolName}...`}
        {status === 'running' && `Running ${toolName}...`}
        {status === 'completed' && `${toolName} completed`}
        {status === 'failed' && `${toolName} failed`}
      </span>
    </div>
  )
}
