import { Link } from 'react-router-dom'
import {
  Bot,
  Search,
  FlaskConical,
  ShieldCheck,
  Workflow,
  Gauge,
  MessageSquare,
  ArrowRight,
  Settings,
  AlertTriangle,
} from 'lucide-react'
import { useAIConfig } from '@/hooks/use-config'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ROUTES } from '@/lib/constants'

// Tool inventories — kept verbatim in sync with the agent definitions
// (app/features/agents/agents/experiment.py + rag_assistant.py). The
// `approval` flag mirrors agent_require_approval (create_alias / archive_run).
interface ToolInfo {
  name: string
  desc: string
  approval?: boolean
}

const RAG_TOOLS: ToolInfo[] = [
  { name: 'tool_retrieve_context', desc: 'Semantic search over the indexed knowledge base.' },
  { name: 'tool_list_sources', desc: 'List indexed sources and chunk counts.' },
  { name: 'tool_format_citations', desc: 'Turn retrieval results into stable citations.' },
  { name: 'tool_check_evidence', desc: 'Decide whether the evidence is sufficient to answer.' },
]

const EXPERIMENT_TOOLS: ToolInfo[] = [
  { name: 'tool_list_runs', desc: 'Browse existing model runs in the registry.' },
  { name: 'tool_get_run', desc: 'Fetch the full detail of one model run.' },
  { name: 'tool_run_backtest', desc: 'Run a time-series backtest for a store / product.' },
  {
    name: 'tool_compare_backtest_results',
    desc: 'Compare two backtest results and recommend a winner.',
  },
  { name: 'tool_compare_runs', desc: 'Diff two registered runs (config + metrics).' },
  { name: 'tool_create_alias', desc: 'Promote a successful run to a deployment alias.', approval: true },
  { name: 'tool_archive_run', desc: 'Archive a model run.', approval: true },
]

const SESSION_STEPS = [
  'Open Chat, pick an agent type, and click "Start Session".',
  'Type a message and send it.',
  'Watch the reply stream token-by-token; tool calls appear as chips (start → end).',
  'If the agent proposes a guarded action, an approval prompt appears — approve or reject it.',
  '"New Session" starts a fresh conversation with a clean history.',
]

const RAG_PROMPTS = [
  'What forecasting models does ForecastLabAI support?',
  'How does backtesting prevent data leakage?',
  'What is in your knowledge base?',
]

const EXPERIMENT_PROMPTS = [
  'Backtest a seasonal_naive model for store 1 product 1 over the last 90 days and compare it to the naive baseline.',
  'List the most recent model runs and tell me which has the lowest WAPE.',
]

export default function GuidePage() {
  const { data: config, isLoading: configLoading } = useAIConfig()

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Agent Guide</h1>
        <p className="mt-1 text-muted-foreground">How to use the Chat agents.</p>
      </div>

      {/* Live model callout */}
      {config && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-4 py-3 text-sm">
          <Bot className="h-4 w-4 text-muted-foreground" />
          <span>
            Agents currently run on{' '}
            <span className="font-mono font-semibold">{config.agent_default_model}</span>.
          </span>
          <Link
            to={ROUTES.ADMIN}
            className="inline-flex items-center text-muted-foreground underline underline-offset-2"
          >
            <Settings className="mr-1 h-3 w-3" />
            Manage in Admin → AI Models
          </Link>
        </div>
      )}

      {/* The two agents */}
      <div className="grid gap-6 md:grid-cols-2">
        <AgentCard
          icon={Search}
          title="RAG Assistant"
          agentId="rag_assistant"
          purpose="Evidence-grounded Q&A over the knowledge base. It answers only from retrieved
            evidence, cites sources as source_path:chunk_id, and says 'I don't have enough
            information' when coverage is missing."
          tools={RAG_TOOLS}
          footer={
            <Link
              to={ROUTES.KNOWLEDGE}
              className="inline-flex items-center text-sm text-muted-foreground underline underline-offset-2"
            >
              See what it can answer from → Knowledge
              <ArrowRight className="ml-1 h-3 w-3" />
            </Link>
          }
        />
        <AgentCard
          icon={FlaskConical}
          title="Experiment Agent"
          agentId="experiment"
          purpose="Plans and runs backtests, compares model performance against baselines, and
            recommends — or, with approval, deploys — a winning model."
          tools={EXPERIMENT_TOOLS}
          footer={
            <Link
              to={ROUTES.EXPLORER.RUNS}
              className="inline-flex items-center text-sm text-muted-foreground underline underline-offset-2"
            >
              See the runs it acts on → Model Runs
              <ArrowRight className="ml-1 h-3 w-3" />
            </Link>
          }
        />
      </div>

      {/* How a chat session works */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Workflow className="h-5 w-5 text-muted-foreground" />
            <CardTitle>How a chat session works</CardTitle>
          </div>
          <CardDescription>
            Each session is one conversation. Replies stream over a WebSocket — text arrives as{' '}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">text_delta</code> events and tool
            calls as <code className="rounded bg-muted px-1 py-0.5 text-xs">tool_call_start</code> /{' '}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">tool_call_end</code> events.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2">
            {SESSION_STEPS.map((step, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                  {i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      {/* Human-in-the-loop approval */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-muted-foreground" />
            <CardTitle>Human-in-the-loop approval</CardTitle>
          </div>
          <CardDescription>
            Tools that change registry state never run unattended.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p>
            When an agent calls a guarded tool, the run pauses and the Chat page shows an approval
            prompt. The action only proceeds once you approve it; rejecting it returns control to
            the agent. This keeps every mutation of the model registry under human control.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">Approval-gated tools:</span>
            {config ? (
              config.agent_require_approval.map((tool) => (
                <Badge key={tool} variant="outline" className="font-mono">
                  <AlertTriangle className="mr-1 h-3 w-3" />
                  {tool}
                </Badge>
              ))
            ) : configLoading ? (
              <Skeleton className="h-5 w-40" />
            ) : (
              <span className="text-xs text-muted-foreground">
                Unavailable — the configuration endpoint could not be reached.
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Session limits */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Gauge className="h-5 w-5 text-muted-foreground" />
            <CardTitle>Session limits</CardTitle>
          </div>
          <CardDescription>
            Live from <code className="rounded bg-muted px-1 py-0.5 text-xs">GET /config/ai</code>.
            These are the configured defaults — an operator can change them in Admin → AI Models.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {configLoading && <Skeleton className="h-48 w-full" />}
          {config && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Limit</TableHead>
                  <TableHead>Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">Token budget per session</TableCell>
                  <TableCell>{config.agent_max_tokens.toLocaleString()} tokens</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Tool calls per session</TableCell>
                  <TableCell>{config.agent_max_tool_calls}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Per-run timeout</TableCell>
                  <TableCell>{config.agent_timeout_seconds} seconds</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Retry attempts</TableCell>
                  <TableCell>{config.agent_retry_attempts}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Session time-to-live</TableCell>
                  <TableCell>{config.agent_session_ttl_minutes} minutes</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Approval-gated tools</TableCell>
                  <TableCell className="font-mono text-xs">
                    {config.agent_require_approval.join(', ') || 'none'}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          )}
          {!configLoading && !config && (
            <p className="text-sm text-muted-foreground">
              Session limits are unavailable right now — the configuration endpoint could not be
              reached.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Example prompts */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-muted-foreground" />
            <CardTitle>Example prompts</CardTitle>
          </div>
          <CardDescription>Copy one of these into Chat to get started.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-2">
          <PromptList title="RAG Assistant" prompts={RAG_PROMPTS} />
          <PromptList title="Experiment Agent" prompts={EXPERIMENT_PROMPTS} />
        </CardContent>
      </Card>

      {/* CTA */}
      <div className="flex justify-center pb-2">
        <Button asChild size="lg">
          <Link to={ROUTES.CHAT}>
            <MessageSquare className="mr-2 h-4 w-4" />
            Open Chat
          </Link>
        </Button>
      </div>
    </div>
  )
}

function AgentCard({
  icon: Icon,
  title,
  agentId,
  purpose,
  tools,
  footer,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  agentId: string
  purpose: string
  tools: ToolInfo[]
  footer: React.ReactNode
}) {
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-muted-foreground" />
          <CardTitle>{title}</CardTitle>
          <Badge variant="secondary" className="font-mono text-xs">
            {agentId}
          </Badge>
        </div>
        <CardDescription>{purpose}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <div>
          <p className="mb-2 text-sm font-medium">Tools</p>
          <ul className="space-y-2">
            {tools.map((tool) => (
              <li key={tool.name} className="text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{tool.name}</code>
                  {tool.approval && (
                    <Badge variant="outline" className="text-[10px]">
                      <AlertTriangle className="mr-1 h-3 w-3" />
                      requires approval
                    </Badge>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">{tool.desc}</p>
              </li>
            ))}
          </ul>
        </div>
        <div className="mt-auto pt-2">{footer}</div>
      </CardContent>
    </Card>
  )
}

function PromptList({ title, prompts }: { title: string; prompts: string[] }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{title}</p>
      {prompts.map((prompt) => (
        <code
          key={prompt}
          className="block rounded-md border bg-muted/50 px-3 py-2 text-xs leading-relaxed"
        >
          {prompt}
        </code>
      ))}
    </div>
  )
}
