import { useState } from 'react'
import { format } from 'date-fns'
import { Trash2, Plus, Database, Tag, Loader2 } from 'lucide-react'
import { useRagSources, useDeleteRagSource, useIndexDocument } from '@/hooks/use-rag-sources'
import { useAliases, useDeleteAlias, useCreateAlias } from '@/hooks/use-runs'
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
        </TabsList>

        <TabsContent value="rag" className="mt-6">
          <RagSourcesPanel />
        </TabsContent>

        <TabsContent value="aliases" className="mt-6">
          <AliasesPanel />
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
