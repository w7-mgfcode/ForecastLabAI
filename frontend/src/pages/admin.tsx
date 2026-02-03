import { useState } from 'react'
import { format } from 'date-fns'
import {
  Trash2,
  Plus,
  Database,
  Tag,
  Loader2,
  Flame,
  CheckCircle,
  RefreshCw,
  Store,
  Package,
  Calendar,
  TrendingUp,
  Warehouse,
  History,
  Percent,
} from 'lucide-react'
import { useRagSources, useDeleteRagSource, useIndexDocument } from '@/hooks/use-rag-sources'
import { useAliases, useDeleteAlias, useCreateAlias } from '@/hooks/use-runs'
import {
  useSeederStatus,
  useSeederScenarios,
  useGenerateData,
  useDeleteData,
  useVerifyData,
} from '@/hooks/use-seeder'
import { ErrorDisplay } from '@/components/common/error-display'
import { LoadingState } from '@/components/common/loading-state'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from 'sonner'
import type { ScenarioInfo, VerifyCheck, VerifyCheckStatus } from '@/types/api'

export default function AdminPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Admin Panel</h1>

      <Tabs defaultValue="rag">
        <TabsList>
          <TabsTrigger value="rag">
            <Database className="h-4 w-4 mr-2" />
            RAG Sources
          </TabsTrigger>
          <TabsTrigger value="aliases">
            <Tag className="h-4 w-4 mr-2" />
            Deployment Aliases
          </TabsTrigger>
          <TabsTrigger value="seeder">
            <Flame className="h-4 w-4 mr-2" />
            Data Seeder
          </TabsTrigger>
        </TabsList>

        <TabsContent value="rag" className="mt-6">
          <RagSourcesPanel />
        </TabsContent>

        <TabsContent value="aliases" className="mt-6">
          <AliasesPanel />
        </TabsContent>

        <TabsContent value="seeder" className="mt-6">
          <SeederPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function RagSourcesPanel() {
  const { data, isLoading, error, refetch } = useRagSources()
  const deleteSource = useDeleteRagSource()
  const indexDocument = useIndexDocument()

  const [newSource, setNewSource] = useState({ type: 'markdown', path: '' })
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  const handleIndex = async () => {
    if (!newSource.path.trim()) return
    await indexDocument.mutateAsync({
      source_type: newSource.type,
      source_path: newSource.path.trim(),
    })
    setNewSource({ type: 'markdown', path: '' })
    setIsDialogOpen(false)
  }

  const handleDelete = async (sourceId: string) => {
    await deleteSource.mutateAsync(sourceId)
  }

  if (error) {
    return <ErrorDisplay error={error} onRetry={refetch} />
  }

  if (isLoading) {
    return <LoadingState message="Loading RAG sources..." />
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Indexed Documents</CardTitle>
          <CardDescription>
            {data?.total_sources ?? 0} sources • {data?.total_chunks ?? 0} chunks
          </CardDescription>
        </div>
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="h-4 w-4 mr-2" />
              Index Document
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Index New Document</DialogTitle>
              <DialogDescription>
                Add a document to the RAG knowledge base
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Document Type</label>
                <Select
                  value={newSource.type}
                  onValueChange={(v) => setNewSource((s) => ({ ...s, type: v }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="markdown">Markdown</SelectItem>
                    <SelectItem value="openapi">OpenAPI</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">File Path</label>
                <Input
                  placeholder="e.g., docs/README.md"
                  value={newSource.path}
                  onChange={(e) => setNewSource((s) => ({ ...s, path: e.target.value }))}
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                onClick={handleIndex}
                disabled={!newSource.path.trim() || indexDocument.isPending}
              >
                {indexDocument.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Index
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent>
        {data?.sources.length ? (
          <div className="space-y-3">
            {data.sources.map((source) => (
              <div
                key={source.source_id}
                className="flex items-center justify-between py-2 border-b last:border-0"
              >
                <div>
                  <p className="font-medium">{source.source_path}</p>
                  <p className="text-xs text-muted-foreground">
                    {source.source_type} • {source.chunk_count} chunks •{' '}
                    Indexed {format(new Date(source.indexed_at), 'MMM d, yyyy')}
                  </p>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="icon-sm">
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete Source</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will remove the document and all its chunks from the knowledge base.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={() => handleDelete(source.source_id)}>
                        Delete
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-8">
            No documents indexed yet.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function AliasesPanel() {
  const { data: aliases, isLoading, error, refetch } = useAliases()
  const deleteAlias = useDeleteAlias()
  const createAlias = useCreateAlias()

  const [newAlias, setNewAlias] = useState({ name: '', runId: '', description: '' })
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  const handleCreate = async () => {
    if (!newAlias.name.trim() || !newAlias.runId.trim()) return
    await createAlias.mutateAsync({
      alias_name: newAlias.name.trim(),
      run_id: newAlias.runId.trim(),
      description: newAlias.description.trim() || undefined,
    })
    setNewAlias({ name: '', runId: '', description: '' })
    setIsDialogOpen(false)
  }

  const handleDelete = async (aliasName: string) => {
    await deleteAlias.mutateAsync(aliasName)
  }

  if (error) {
    return <ErrorDisplay error={error} onRetry={refetch} />
  }

  if (isLoading) {
    return <LoadingState message="Loading aliases..." />
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Deployment Aliases</CardTitle>
          <CardDescription>
            Named pointers to successful model runs
          </CardDescription>
        </div>
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="h-4 w-4 mr-2" />
              Create Alias
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Deployment Alias</DialogTitle>
              <DialogDescription>
                Create a named pointer to a successful model run
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Alias Name</label>
                <Input
                  placeholder="e.g., production, staging"
                  value={newAlias.name}
                  onChange={(e) => setNewAlias((s) => ({ ...s, name: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Run ID</label>
                <Input
                  placeholder="Enter the run ID"
                  value={newAlias.runId}
                  onChange={(e) => setNewAlias((s) => ({ ...s, runId: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Description (optional)</label>
                <Input
                  placeholder="Optional description"
                  value={newAlias.description}
                  onChange={(e) => setNewAlias((s) => ({ ...s, description: e.target.value }))}
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                onClick={handleCreate}
                disabled={!newAlias.name.trim() || !newAlias.runId.trim() || createAlias.isPending}
              >
                {createAlias.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent>
        {aliases?.length ? (
          <div className="space-y-3">
            {aliases.map((alias) => (
              <div
                key={alias.alias_name}
                className="flex items-center justify-between py-2 border-b last:border-0"
              >
                <div>
                  <p className="font-medium">{alias.alias_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {alias.model_type} • Run: {alias.run_id.substring(0, 8)}... •{' '}
                    {alias.description || 'No description'}
                  </p>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="icon-sm">
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete Alias</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will remove the deployment alias. The underlying model run will not be affected.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={() => handleDelete(alias.alias_name)}>
                        Delete
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-8">
            No deployment aliases created yet.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function SeederPanel() {
  const { data: status, isLoading, error, refetch } = useSeederStatus()
  const { data: scenarios } = useSeederScenarios()
  const generateMutation = useGenerateData()
  const deleteMutation = useDeleteData()
  const verifyMutation = useVerifyData()

  const [selectedScenario, setSelectedScenario] = useState('retail_standard')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [verifyResult, setVerifyResult] = useState<{
    passed: boolean
    checks: VerifyCheck[]
    passed_count: number
    warning_count: number
    failed_count: number
  } | null>(null)

  const handleGenerate = async () => {
    try {
      const result = await generateMutation.mutateAsync({
        scenario: selectedScenario,
      })
      toast.success(
        `Generated ${result.records_created.sales?.toLocaleString() ?? 0} sales records in ${result.duration_seconds.toFixed(1)}s`
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Generation failed')
    }
  }

  const handleDelete = async () => {
    try {
      const result = await deleteMutation.mutateAsync({ scope: 'all' })
      setDeleteDialogOpen(false)
      toast.success(result.message)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const handleVerify = async () => {
    try {
      const result = await verifyMutation.mutateAsync()
      setVerifyResult(result)
      if (result.passed) {
        toast.success('All integrity checks passed')
      } else {
        toast.warning(`${result.failed_count} checks failed`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Verification failed')
    }
  }

  if (error) {
    return <ErrorDisplay error={error} onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      {/* Status Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Current Data Summary</CardTitle>
            <CardDescription>
              {status?.date_range_start && status?.date_range_end
                ? `${status.date_range_start} → ${status.date_range_end}`
                : 'No data yet'}
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="grid grid-cols-7 gap-4">
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-7 gap-4">
              <StatCard icon={Store} label="Stores" value={status?.stores ?? 0} />
              <StatCard icon={Package} label="Products" value={status?.products ?? 0} />
              <StatCard icon={Calendar} label="Calendar" value={status?.calendar ?? 0} />
              <StatCard icon={TrendingUp} label="Sales" value={status?.sales ?? 0} />
              <StatCard icon={Warehouse} label="Inventory" value={status?.inventory ?? 0} />
              <StatCard icon={History} label="Prices" value={status?.price_history ?? 0} />
              <StatCard icon={Percent} label="Promos" value={status?.promotions ?? 0} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Actions Card */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
          <CardDescription>Generate, delete, or verify synthetic data</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2 flex-wrap">
            <Button onClick={handleGenerate} disabled={generateMutation.isPending}>
              {generateMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Flame className="h-4 w-4 mr-2" />
              )}
              Generate New
            </Button>

            <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
              <AlertDialogTrigger asChild>
                <Button
                  variant="destructive"
                  disabled={deleteMutation.isPending || (status?.sales ?? 0) === 0}
                >
                  {deleteMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-2" />
                  )}
                  Delete All
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete All Data?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete all{' '}
                    {status?.sales?.toLocaleString() ?? 0} sales records,{' '}
                    {status?.stores ?? 0} stores, and {status?.products ?? 0} products. This
                    action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete}>Delete All Data</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>

            <Button
              variant="outline"
              onClick={handleVerify}
              disabled={verifyMutation.isPending || (status?.sales ?? 0) === 0}
            >
              {verifyMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <CheckCircle className="h-4 w-4 mr-2" />
              )}
              Verify
            </Button>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Scenario</label>
            <Select value={selectedScenario} onValueChange={setSelectedScenario}>
              <SelectTrigger className="w-[300px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {scenarios?.map((s: ScenarioInfo) => (
                  <SelectItem key={s.name} value={s.name}>
                    <div className="flex flex-col">
                      <span>{formatScenarioLabel(s.name)}</span>
                      <span className="text-xs text-muted-foreground">{s.description}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Verification Results */}
      {verifyResult && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Verification Results
              <Badge variant={verifyResult.passed ? 'default' : 'destructive'}>
                {verifyResult.passed ? 'Passed' : 'Failed'}
              </Badge>
            </CardTitle>
            <CardDescription>
              {verifyResult.passed_count} passed • {verifyResult.warning_count} warnings •{' '}
              {verifyResult.failed_count} failed
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {verifyResult.checks.map((check: VerifyCheck, idx: number) => (
                <div
                  key={idx}
                  className="flex items-center justify-between py-2 border-b last:border-0"
                >
                  <div>
                    <p className="font-medium">{check.name}</p>
                    <p className="text-xs text-muted-foreground">{check.message}</p>
                  </div>
                  <Badge variant={getCheckBadgeVariant(check.status)}>{check.status}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// Helper component for stat cards
function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: number
}) {
  return (
    <div className="text-center p-3 rounded-lg bg-muted">
      <Icon className="h-4 w-4 mx-auto mb-1 text-muted-foreground" />
      <p className="text-lg font-bold">{value.toLocaleString()}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

// Helper for scenario names
function formatScenarioLabel(name: string): string {
  return name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// Helper for badge variants
function getCheckBadgeVariant(status: VerifyCheckStatus): 'default' | 'secondary' | 'destructive' {
  switch (status) {
    case 'passed':
      return 'default'
    case 'warning':
      return 'secondary'
    case 'failed':
      return 'destructive'
  }
}
