import { useState, useRef, useEffect, useCallback } from 'react'
import { Bot, Plus } from 'lucide-react'
import { useWebSocket } from '@/hooks/use-websocket'
import { ChatMessage, StreamingMessage } from '@/components/chat/chat-message'
import { ChatInput, ApprovalPrompt } from '@/components/chat/chat-input'
import { ToolCallProgress } from '@/components/chat/tool-call-display'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { api } from '@/lib/api'
import { WS_URL } from '@/lib/constants'
import type { ChatMessage as ChatMessageType, AgentStreamEvent, AgentType, AgentSession } from '@/types/api'

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [agentType, setAgentType] = useState<AgentType>('rag_assistant')
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [pendingAction, setPendingAction] = useState<{ action: string; details?: Record<string, unknown> } | null>(null)
  const [currentToolCall, setCurrentToolCall] = useState<string | null>(null)
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [isApproving, setIsApproving] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)

  // WebSocket connection
  const wsUrl = sessionId ? `${WS_URL}?session_id=${sessionId}` : null

  const handleMessage = useCallback((data: unknown) => {
    const event = data as AgentStreamEvent

    switch (event.event_type) {
      case 'text_delta':
        setIsStreaming(true)
        setStreamingContent((prev) => prev + (event.data.content as string))
        break

      case 'tool_call_start':
        setCurrentToolCall(event.data.tool_name as string)
        break

      case 'tool_call_end':
        setCurrentToolCall(null)
        break

      case 'approval_required':
        setPendingAction({
          action: event.data.action as string,
          details: event.data.details as Record<string, unknown>,
        })
        break

      case 'complete':
        // Finalize the streaming message
        if (streamingContent || event.data.content) {
          const content = (event.data.content as string) || streamingContent
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content,
              tool_calls: event.data.tool_calls as ChatMessageType['tool_calls'],
              citations: event.data.citations as ChatMessageType['citations'],
              timestamp: new Date().toISOString(),
            },
          ])
        }
        setStreamingContent('')
        setIsStreaming(false)
        setCurrentToolCall(null)
        break

      case 'error':
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `Error: ${event.data.message as string}`,
            timestamp: new Date().toISOString(),
          },
        ])
        setStreamingContent('')
        setIsStreaming(false)
        setCurrentToolCall(null)
        break
    }
  }, [streamingContent])

  const { status: wsStatus, send } = useWebSocket(wsUrl, {
    onMessage: handleMessage,
    autoConnect: !!sessionId,
  })

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, streamingContent])

  const createSession = async () => {
    setIsCreatingSession(true)
    try {
      const session = await api<AgentSession>('/agents/sessions', {
        method: 'POST',
        body: { agent_type: agentType },
      })
      setSessionId(session.session_id)
      setMessages([])
    } catch (error) {
      console.error('Failed to create session:', error)
    } finally {
      setIsCreatingSession(false)
    }
  }

  const handleSend = (content: string) => {
    // Add user message
    setMessages((prev) => [
      ...prev,
      { role: 'user', content, timestamp: new Date().toISOString() },
    ])

    // Send via WebSocket
    send({ type: 'chat', content })
  }

  const handleApprove = async () => {
    if (!sessionId || !pendingAction) return
    setIsApproving(true)
    try {
      await api(`/agents/sessions/${sessionId}/approve`, {
        method: 'POST',
        body: { approved: true },
      })
      setPendingAction(null)
    } catch (error) {
      console.error('Failed to approve:', error)
    } finally {
      setIsApproving(false)
    }
  }

  const handleReject = async () => {
    if (!sessionId || !pendingAction) return
    setIsApproving(true)
    try {
      await api(`/agents/sessions/${sessionId}/approve`, {
        method: 'POST',
        body: { approved: false },
      })
      setPendingAction(null)
    } catch (error) {
      console.error('Failed to reject:', error)
    } finally {
      setIsApproving(false)
    }
  }

  const handleNewSession = () => {
    setSessionId(null)
    setMessages([])
    setStreamingContent('')
    setPendingAction(null)
  }

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              Start Chat Session
            </CardTitle>
            <CardDescription>
              Choose an agent type to start a new conversation
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Agent Type</label>
              <Select value={agentType} onValueChange={(v) => setAgentType(v as AgentType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="rag_assistant">
                    RAG Assistant - Documentation Q&A
                  </SelectItem>
                  <SelectItem value="experiment">
                    Experiment Agent - Model Testing
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={createSession}
              disabled={isCreatingSession}
              className="w-full"
            >
              {isCreatingSession ? 'Creating...' : 'Start Session'}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b">
        <div>
          <h1 className="text-xl font-bold">Agent Chat</h1>
          <p className="text-sm text-muted-foreground">
            {agentType === 'rag_assistant' ? 'RAG Assistant' : 'Experiment Agent'} •{' '}
            {wsStatus === 'connected' ? (
              <span className="text-green-600">Connected</span>
            ) : (
              <span className="text-yellow-600">{wsStatus}</span>
            )}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleNewSession}>
          <Plus className="h-4 w-4 mr-2" />
          New Session
        </Button>
      </div>

      {/* Messages */}
      <ScrollArea ref={scrollRef} className="flex-1 py-4">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
            <Bot className="h-12 w-12 mb-4" />
            <p className="font-medium">Start a conversation</p>
            <p className="text-sm">
              {agentType === 'rag_assistant'
                ? 'Ask questions about the documentation or codebase.'
                : 'Ask the agent to run experiments or compare models.'}
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <ChatMessage key={idx} message={msg} />
        ))}

        {/* Streaming content */}
        {isStreaming && streamingContent && (
          <StreamingMessage content={streamingContent} />
        )}

        {/* Tool call in progress */}
        {currentToolCall && (
          <div className="px-4 py-2">
            <ToolCallProgress toolName={currentToolCall} status="running" />
          </div>
        )}

        {/* Approval prompt */}
        {pendingAction && (
          <ApprovalPrompt
            action={pendingAction.action}
            details={pendingAction.details}
            onApprove={handleApprove}
            onReject={handleReject}
            isLoading={isApproving}
          />
        )}
      </ScrollArea>

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        isLoading={isStreaming}
        disabled={wsStatus !== 'connected' || !!pendingAction}
        placeholder={
          pendingAction
            ? 'Please approve or reject the pending action...'
            : 'Type your message...'
        }
      />
    </div>
  )
}
