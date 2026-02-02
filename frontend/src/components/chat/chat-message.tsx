import { User, Bot, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/card'
import { ToolCallDisplay } from './tool-call-display'
import type { ChatMessage as ChatMessageType, Citation } from '@/types/api'

interface ChatMessageProps {
  message: ChatMessageType
  className?: string
}

export function ChatMessage({ message, className }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={cn(
        'flex gap-3 px-4 py-3',
        isUser ? 'flex-row-reverse' : '',
        className
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-full',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-muted-foreground'
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div
        className={cn(
          'flex flex-col gap-2 max-w-[80%]',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        {/* Message Text */}
        <Card
          className={cn(
            'px-4 py-2',
            isUser
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted'
          )}
        >
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </Card>

        {/* Tool Calls */}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="w-full space-y-2">
            {message.tool_calls.map((toolCall, idx) => (
              <ToolCallDisplay key={idx} toolCall={toolCall} />
            ))}
          </div>
        )}

        {/* Citations */}
        {message.citations && message.citations.length > 0 && (
          <CitationsList citations={message.citations} />
        )}

        {/* Timestamp */}
        <span className="text-xs text-muted-foreground">
          {new Date(message.timestamp).toLocaleTimeString()}
        </span>
      </div>
    </div>
  )
}

interface CitationsListProps {
  citations: Citation[]
}

function CitationsList({ citations }: CitationsListProps) {
  return (
    <div className="space-y-1 w-full">
      <p className="text-xs font-medium text-muted-foreground">Sources:</p>
      <div className="space-y-1">
        {citations.map((citation, idx) => (
          <div
            key={idx}
            className="flex items-start gap-2 text-xs text-muted-foreground bg-muted/50 rounded px-2 py-1"
          >
            <ExternalLink className="h-3 w-3 mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="font-medium truncate">{citation.source_path}</p>
              <p className="text-xs opacity-75 line-clamp-2">{citation.snippet}</p>
              <p className="text-xs opacity-50">
                Relevance: {(citation.relevance_score * 100).toFixed(0)}%
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

interface StreamingMessageProps {
  content: string
  isComplete?: boolean
}

export function StreamingMessage({ content, isComplete = false }: StreamingMessageProps) {
  return (
    <div className="flex gap-3 px-4 py-3">
      <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Bot className="h-4 w-4" />
      </div>
      <div className="flex flex-col gap-2 max-w-[80%]">
        <Card className="px-4 py-2 bg-muted">
          <p className="text-sm whitespace-pre-wrap">
            {content}
            {!isComplete && <span className="animate-pulse">▊</span>}
          </p>
        </Card>
      </div>
    </div>
  )
}
