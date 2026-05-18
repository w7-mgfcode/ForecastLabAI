import { useState } from 'react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import {
  Library,
  Search,
  FileText,
  Loader2,
  Store,
  Package,
  TrendingUp,
  CalendarRange,
  Database,
  Tag,
  ArrowRight,
  FolderOpen,
} from 'lucide-react'
import { useRagSources, useRetrieve } from '@/hooks/use-rag-sources'
import { useSeederStatus } from '@/hooks/use-seeder'
import { useRuns, useAliases } from '@/hooks/use-runs'
import { LoadingState } from '@/components/common/loading-state'
import { ErrorDisplay } from '@/components/common/error-display'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError, getErrorMessage } from '@/lib/api'
import { ROUTES } from '@/lib/constants'
import { formatRelevance, chunkExcerpt, groupSourcesByType } from '@/lib/knowledge-utils'

export default function KnowledgePage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Knowledge</h1>
        <p className="mt-1 text-muted-foreground">
          Everything ForecastLabAI can currently draw on — the RAG knowledge base its assistant
          answers from, and the live data its experiment agent acts on.
        </p>
      </div>

      <KnowledgeBaseSection />
      <SemanticSearchSection />
      <LiveSystemStateSection />
    </div>
  )
}

// === Section 1 — Knowledge Base (indexed RAG sources, read-only) ===

function KnowledgeBaseSection() {
  const { data, isLoading, error, refetch } = useRagSources()

  if (error) {
    return <ErrorDisplay error={error} onRetry={refetch} title="Could not load the knowledge base" />
  }
  if (isLoading) {
    return <LoadingState message="Loading the knowledge base..." />
  }

  const sources = data?.sources ?? []
  const byType = groupSourcesByType(sources)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Library className="h-5 w-5 text-muted-foreground" />
          <CardTitle>Knowledge Base</CardTitle>
        </div>
        <CardDescription>
          {data?.total_sources ?? 0} sources • {data?.total_chunks ?? 0} chunks
          {sources.length > 0 && (
            <>
              {' • '}
              {Object.entries(byType)
                .map(([type, items]) => `${items.length} ${type}`)
                .join(', ')}
            </>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {sources.length > 0 ? (
          <div className="space-y-3">
            {sources.map((source) => (
              <div
                key={source.source_id}
                className="flex items-center justify-between gap-4 border-b py-2 last:border-0"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <p className="truncate font-medium">{source.source_path}</p>
                    <p className="text-xs text-muted-foreground">
                      {source.chunk_count} chunks • Indexed{' '}
                      {format(new Date(source.indexed_at), 'MMM d, yyyy')}
                    </p>
                  </div>
                </div>
                <Badge variant="secondary" className="shrink-0">
                  {source.source_type}
                </Badge>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
            <FolderOpen className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No documents indexed yet</p>
              <p className="text-sm text-muted-foreground">
                The RAG assistant has nothing to answer from. Index documents in Admin → RAG
                Sources, or run the RAG seeder scenario.
              </p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link to={ROUTES.ADMIN}>
                Go to Admin → RAG Sources
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// === Section 2 — Semantic Search (POST /rag/retrieve) ===

function SemanticSearchSection() {
  const [query, setQuery] = useState('')
  const retrieve = useRetrieve()

  const trimmed = query.trim()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!trimmed || retrieve.isPending) return
    retrieve.mutate({ query: trimmed, top_k: 5 })
  }

  const searchUnavailable = retrieve.error instanceof ApiError && retrieve.error.status === 502
  const results = retrieve.data?.results ?? []

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Search className="h-5 w-5 text-muted-foreground" />
          <CardTitle>Semantic Search</CardTitle>
        </div>
        <CardDescription>
          Search the indexed knowledge base the way the RAG assistant does — by meaning, not
          keywords.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. How does backtesting prevent data leakage?"
            aria-label="Semantic search query"
          />
          <Button type="submit" disabled={!trimmed || retrieve.isPending}>
            {retrieve.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            <span className="ml-2">Search</span>
          </Button>
        </form>

        {searchUnavailable && (
          <p className="rounded-md border border-dashed bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            Semantic search is unavailable — configure an embedding provider in{' '}
            <Link to={ROUTES.ADMIN} className="font-medium underline underline-offset-2">
              Admin → AI Models
            </Link>
            . The source list above does not need embeddings and still works.
          </p>
        )}

        {retrieve.isError && !searchUnavailable && (
          <p className="rounded-md border border-dashed bg-muted/40 px-4 py-3 text-sm text-destructive">
            {getErrorMessage(retrieve.error)}
          </p>
        )}

        {retrieve.isSuccess && results.length === 0 && (
          <p className="rounded-md border border-dashed bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            No matching content found. Try rephrasing the query.
          </p>
        )}

        {results.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              {results.length} match{results.length === 1 ? '' : 'es'} •{' '}
              {retrieve.data?.total_chunks_searched ?? 0} chunks searched in{' '}
              {Math.round(retrieve.data?.search_time_ms ?? 0)} ms
            </p>
            {results.map((chunk) => (
              <div key={chunk.chunk_id} className="rounded-lg border p-3">
                <div className="mb-1.5 flex items-center justify-between gap-3">
                  <p className="truncate font-mono text-xs text-muted-foreground">
                    {chunk.source_path}
                    <span className="ml-1 text-muted-foreground/70">({chunk.source_type})</span>
                  </p>
                  <Badge variant="outline" className="shrink-0">
                    {formatRelevance(chunk.relevance_score)} match
                  </Badge>
                </div>
                <p className="text-sm leading-relaxed">{chunkExcerpt(chunk)}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// === Section 3 — Live System State (what the experiment agent acts on) ===

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number
}) {
  return (
    <div className="rounded-lg bg-muted p-3 text-center">
      <Icon className="mx-auto mb-1 h-4 w-4 text-muted-foreground" />
      <p className="text-lg font-bold">{typeof value === 'number' ? value.toLocaleString() : value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

function LiveSystemStateSection() {
  const { data: status, isLoading: statusLoading } = useSeederStatus()
  const { data: runs, isLoading: runsLoading } = useRuns({ page: 1, pageSize: 1 })
  const { data: aliases, isLoading: aliasesLoading } = useAliases()

  const dateRange =
    status?.date_range_start && status?.date_range_end
      ? `${status.date_range_start} → ${status.date_range_end}`
      : 'No data'

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-muted-foreground" />
          <CardTitle>Live System State</CardTitle>
        </div>
        <CardDescription>
          The seeded data and registered models the experiment agent can query through its tools.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Seeded data tiles */}
        {statusLoading ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard icon={Store} label="Stores" value={status?.stores ?? 0} />
            <StatCard icon={Package} label="Products" value={status?.products ?? 0} />
            <StatCard icon={TrendingUp} label="Sales records" value={status?.sales ?? 0} />
            <StatCard icon={CalendarRange} label="Date range" value={dateRange} />
          </div>
        )}

        {/* Registry summary */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border p-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-medium">Registered model runs</p>
            </div>
            <p className="mt-2 text-2xl font-bold">
              {runsLoading ? '—' : (runs?.total ?? 0).toLocaleString()}
            </p>
            <Link
              to={ROUTES.EXPLORER.RUNS}
              className="mt-1 inline-flex items-center text-xs text-muted-foreground underline underline-offset-2"
            >
              Browse all runs
              <ArrowRight className="ml-1 h-3 w-3" />
            </Link>
          </div>

          <div className="rounded-lg border p-4">
            <div className="flex items-center gap-2">
              <Tag className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-medium">Deployment aliases</p>
            </div>
            {aliasesLoading ? (
              <p className="mt-2 text-sm text-muted-foreground">Loading…</p>
            ) : aliases && aliases.length > 0 ? (
              <ul className="mt-2 space-y-1">
                {aliases.map((alias) => (
                  <li key={alias.alias_name} className="flex items-center justify-between text-sm">
                    <span className="font-medium">{alias.alias_name}</span>
                    <Badge variant="secondary">{alias.model_type}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">No aliases yet.</p>
            )}
          </div>
        </div>

        {/* Explainer */}
        <p className="text-sm text-muted-foreground">
          The RAG assistant answers from the Knowledge Base above; the experiment agent acts on this
          Live System State. Learn how to use them in the{' '}
          <Link to={ROUTES.GUIDE} className="font-medium text-foreground underline underline-offset-2">
            Agent Guide
          </Link>
          , or start a conversation in{' '}
          <Link to={ROUTES.CHAT} className="font-medium text-foreground underline underline-offset-2">
            Chat
          </Link>
          .
        </p>
      </CardContent>
    </Card>
  )
}
