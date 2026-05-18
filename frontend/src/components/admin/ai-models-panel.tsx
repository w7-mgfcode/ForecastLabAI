import { useState } from 'react'
import { Loader2, RefreshCw, Save, Cpu, Database, KeyRound, Activity } from 'lucide-react'
import {
  useAIConfig,
  useProviderHealth,
  useOllamaModels,
  useUpdateAIConfig,
} from '@/hooks/use-config'
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
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import type { AIModelConfig, AIModelConfigUpdate } from '@/types/api'

const AGENT_PROVIDERS = ['anthropic', 'openai', 'google-gla', 'google-vertex', 'ollama'] as const
const EMBEDDING_PROVIDERS = ['openai', 'ollama'] as const

interface FormState {
  agentProvider: string
  agentModel: string
  agentFallback: string
  agentTemperature: string
  agentMaxTokens: string
  agentThinkingBudget: string
  ragProvider: string
  ragModel: string
  ragDimension: string
  ollamaBaseUrl: string
  ollamaEmbeddingModel: string
}

function deriveForm(cfg: AIModelConfig): FormState {
  const [agentProvider, ...rest] = cfg.agent_default_model.split(':')
  return {
    agentProvider,
    agentModel: rest.join(':'),
    agentFallback: cfg.agent_fallback_model,
    agentTemperature: String(cfg.agent_temperature),
    agentMaxTokens: String(cfg.agent_max_tokens),
    agentThinkingBudget: cfg.agent_thinking_budget == null ? '' : String(cfg.agent_thinking_budget),
    ragProvider: cfg.rag_embedding_provider,
    ragModel: cfg.rag_embedding_model,
    ragDimension: String(cfg.rag_embedding_dimension),
    ollamaBaseUrl: cfg.ollama_base_url,
    ollamaEmbeddingModel: cfg.ollama_embedding_model,
  }
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>
      {children}
    </div>
  )
}

export function AIModelsPanel() {
  const { data: config, isLoading, error, refetch } = useAIConfig()
  const updateConfig = useUpdateAIConfig()

  // `form` holds operator edits; it is null until the first edit. The
  // displayed form is `form ?? deriveForm(config)` — no state-seeding effect.
  const [form, setForm] = useState<FormState | null>(null)
  const [keys, setKeys] = useState({ openai: '', anthropic: '', google: '' })
  const [forceDimension, setForceDimension] = useState(false)

  const agentProvider =
    form?.agentProvider ?? config?.agent_default_model.split(':')[0] ?? ''
  const ollamaModels = useOllamaModels(agentProvider === 'ollama')

  if (error) return <ErrorDisplay error={error} onRetry={refetch} />
  if (isLoading || !config) return <LoadingState message="Loading AI configuration..." />

  const f = form ?? deriveForm(config)
  const update = (patch: Partial<FormState>) =>
    setForm((prev) => ({ ...(prev ?? deriveForm(config)), ...patch }))

  const save = async (body: AIModelConfigUpdate, label: string) => {
    try {
      await updateConfig.mutateAsync(body)
      toast.success(`${label} saved — applied live, no restart needed`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `${label} update failed`)
    }
  }

  const saveAgent = () =>
    save(
      {
        agent_default_model: `${f.agentProvider}:${f.agentModel.trim()}`,
        agent_fallback_model: f.agentFallback.trim(),
        agent_temperature: Number(f.agentTemperature),
        agent_max_tokens: Number(f.agentMaxTokens),
        ...(f.agentThinkingBudget.trim()
          ? { agent_thinking_budget: Number(f.agentThinkingBudget) }
          : {}),
      },
      'Agent LLM'
    )

  const saveEmbeddings = () =>
    save(
      {
        rag_embedding_provider: f.ragProvider as 'openai' | 'ollama',
        rag_embedding_model: f.ragModel.trim(),
        rag_embedding_dimension: Number(f.ragDimension),
        ollama_base_url: f.ollamaBaseUrl.trim(),
        ollama_embedding_model: f.ollamaEmbeddingModel.trim(),
        force: forceDimension,
      },
      'RAG embeddings'
    )

  const saveKeys = async () => {
    const body: AIModelConfigUpdate = {}
    if (keys.openai.trim()) body.openai_api_key = keys.openai.trim()
    if (keys.anthropic.trim()) body.anthropic_api_key = keys.anthropic.trim()
    if (keys.google.trim()) body.google_api_key = keys.google.trim()
    if (Object.keys(body).length === 0) {
      toast.warning('Enter at least one API key to save')
      return
    }
    await save(body, 'API keys')
    setKeys({ openai: '', anthropic: '', google: '' })
  }

  const busy = updateConfig.isPending

  return (
    <div className="space-y-6">
      {/* Agent LLM */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-4 w-4" /> Agent LLM
          </CardTitle>
          <CardDescription>
            The model backing the chat agent. Pick <strong>ollama</strong> to run fully local.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Provider">
              <Select
                value={f.agentProvider}
                onValueChange={(v) => update({ agentProvider: v })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AGENT_PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field label="Model">
              {f.agentProvider === 'ollama' ? (
                <Select
                  value={f.agentModel}
                  onValueChange={(v) => update({ agentModel: v })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select a pulled model" />
                  </SelectTrigger>
                  <SelectContent>
                    {ollamaModels.data?.length ? (
                      ollamaModels.data.map((m) => (
                        <SelectItem key={m.name} value={m.name}>
                          {m.name}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value={f.agentModel || 'none'} disabled>
                        {ollamaModels.isError
                          ? 'Ollama unreachable'
                          : 'No local models found'}
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  value={f.agentModel}
                  onChange={(e) => update({ agentModel: e.target.value })}
                  placeholder="claude-sonnet-4-5"
                />
              )}
            </Field>

            <Field label="Fallback model (provider:model)">
              <Input
                value={f.agentFallback}
                onChange={(e) => update({ agentFallback: e.target.value })}
                placeholder="openai:gpt-4o"
              />
            </Field>

            <Field label={`Temperature (${f.agentTemperature})`}>
              <Input
                type="number"
                min={0}
                max={2}
                step={0.05}
                value={f.agentTemperature}
                onChange={(e) => update({ agentTemperature: e.target.value })}
              />
            </Field>

            <Field label="Max tokens">
              <Input
                type="number"
                min={1}
                value={f.agentMaxTokens}
                onChange={(e) => update({ agentMaxTokens: e.target.value })}
              />
            </Field>

            <Field label="Thinking budget (optional)">
              <Input
                type="number"
                min={1}
                value={f.agentThinkingBudget}
                placeholder="disabled"
                onChange={(e) => update({ agentThinkingBudget: e.target.value })}
              />
            </Field>
          </div>
          <div className="flex justify-end">
            <Button onClick={saveAgent} disabled={busy}>
              {busy ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Save Agent LLM
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* RAG Embeddings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-4 w-4" /> RAG Embeddings
          </CardTitle>
          <CardDescription>
            Embedding provider for the knowledge base. Changing the dimension with
            indexed chunks requires a re-index.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Provider">
              <Select
                value={f.ragProvider}
                onValueChange={(v) => update({ ragProvider: v })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EMBEDDING_PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field label="Embedding model (OpenAI)">
              <Input
                value={f.ragModel}
                onChange={(e) => update({ ragModel: e.target.value })}
                placeholder="text-embedding-3-small"
              />
            </Field>

            <Field label="Embedding dimension">
              <Input
                type="number"
                min={1}
                value={f.ragDimension}
                onChange={(e) => update({ ragDimension: e.target.value })}
              />
            </Field>

            <Field label="Ollama embedding model">
              <Input
                value={f.ollamaEmbeddingModel}
                onChange={(e) => update({ ollamaEmbeddingModel: e.target.value })}
                placeholder="nomic-embed-text"
              />
            </Field>

            <Field label="Ollama base URL">
              <Input
                value={f.ollamaBaseUrl}
                onChange={(e) => update({ ollamaBaseUrl: e.target.value })}
                placeholder="http://localhost:11434"
              />
            </Field>
          </div>
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox
                checked={forceDimension}
                onCheckedChange={(c) => setForceDimension(c === true)}
              />
              Force dimension change (re-index required)
            </label>
            <Button onClick={saveEmbeddings} disabled={busy}>
              {busy ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Save Embeddings
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* API Keys */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4" /> Provider API Keys
          </CardTitle>
          <CardDescription>
            Set or replace cloud provider keys. Stored values are never displayed —
            only a masked preview. Ollama needs no key.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {(['openai', 'anthropic', 'google'] as const).map((provider) => {
            const status = config.api_keys.find((k) => k.provider === provider)
            return (
              <Field
                key={provider}
                label={`${provider} API key`}
              >
                <div className="flex items-center gap-2">
                  <Input
                    type="password"
                    value={keys[provider]}
                    placeholder={status?.is_set ? `current: ${status.masked}` : 'not set'}
                    onChange={(e) =>
                      setKeys((k) => ({ ...k, [provider]: e.target.value }))
                    }
                  />
                  <Badge variant={status?.is_set ? 'default' : 'secondary'}>
                    {status?.is_set ? 'Set' : 'Unset'}
                  </Badge>
                </div>
              </Field>
            )
          })}
          <div className="flex justify-end">
            <Button onClick={saveKeys} disabled={busy}>
              {busy ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Save API Keys
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Provider Health */}
      <ProviderHealthCard />
    </div>
  )
}

function ProviderHealthCard() {
  const { data: health, isLoading, error, refetch, isFetching } = useProviderHealth()

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4" /> Provider Health
          </CardTitle>
          <CardDescription>
            Ollama is probed live; cloud providers report API-key presence.
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {error ? (
          <ErrorDisplay error={error} onRetry={refetch} />
        ) : isLoading ? (
          <LoadingState message="Checking providers..." />
        ) : (
          <div className="space-y-2">
            {health?.map((h) => (
              <div
                key={h.provider}
                className="flex items-center justify-between py-2 border-b last:border-0"
              >
                <div>
                  <p className="font-medium">{h.provider}</p>
                  <p className="text-xs text-muted-foreground">
                    {h.detail}
                    {h.models.length > 0 && ` • models: ${h.models.join(', ')}`}
                  </p>
                </div>
                <Badge variant={h.reachable ? 'default' : 'destructive'}>
                  {h.reachable ? 'Reachable' : 'Unreachable'}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
