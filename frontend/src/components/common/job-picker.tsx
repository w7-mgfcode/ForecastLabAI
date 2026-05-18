import { useEffect, useMemo, useState } from 'react'
import { format } from 'date-fns'
import { Search } from 'lucide-react'
import { useJobs } from '@/hooks/use-jobs'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Job, JobType } from '@/types/api'

interface JobPickerProps {
  /** Job type to list — 'train', 'predict', or 'backtest'. */
  jobType: Extract<JobType, 'train' | 'predict' | 'backtest'>
  /** Currently loaded job ID (empty string when nothing is loaded). */
  selectedJobId: string
  /** Called with a job ID when the user picks one or enters one manually. */
  onSelect: (jobId: string) => void
  /** Auto-select the most recent completed job once the list first loads. */
  autoSelectLatest?: boolean
}

/** Compact label for a job option: short id, model (when known), and timestamp. */
function jobLabel(job: Job): string {
  const shortId = job.job_id.slice(0, 8)
  const when = format(new Date(job.created_at), 'MMM d, HH:mm')
  const model = typeof job.params.model_type === 'string' ? job.params.model_type : null
  return model ? `${shortId} · ${model} · ${when}` : `${shortId} · ${when}`
}

/**
 * Job selector for the visualization pages: a dropdown of completed jobs of a
 * given type, plus a manual job-ID entry box for pasting an ID from elsewhere.
 */
export function JobPicker({
  jobType,
  selectedJobId,
  onSelect,
  autoSelectLatest = false,
}: JobPickerProps) {
  const [manualId, setManualId] = useState('')

  const { data, isLoading } = useJobs({
    page: 1,
    pageSize: 50,
    jobType,
    status: 'completed',
  })
  // Memoised so the auto-select effect below has a stable dependency.
  const jobs = useMemo(() => data?.jobs ?? [], [data])

  // Auto-select the most recent completed job once, when the list first
  // arrives and nothing has been selected yet (jobs come newest-first).
  useEffect(() => {
    if (autoSelectLatest && !selectedJobId && jobs.length > 0) {
      onSelect(jobs[0].job_id)
    }
  }, [autoSelectLatest, selectedJobId, jobs, onSelect])

  const handleManualLoad = () => {
    const trimmed = manualId.trim()
    if (trimmed) onSelect(trimmed)
  }

  // Only bind the dropdown to selectedJobId when it refers to a listed job, so
  // a manually-pasted (and possibly unlisted) ID doesn't break the trigger.
  const dropdownValue = jobs.some((j) => j.job_id === selectedJobId) ? selectedJobId : ''

  return (
    <div className="space-y-3">
      <Select
        value={dropdownValue}
        onValueChange={onSelect}
        disabled={isLoading || jobs.length === 0}
      >
        <SelectTrigger className="max-w-md">
          <SelectValue
            placeholder={
              isLoading
                ? 'Loading jobs…'
                : jobs.length === 0
                  ? `No completed ${jobType} jobs yet`
                  : 'Pick a job…'
            }
          />
        </SelectTrigger>
        <SelectContent>
          {jobs.map((job) => (
            <SelectItem key={job.job_id} value={job.job_id}>
              {jobLabel(job)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          or paste an ID:
        </span>
        <Input
          placeholder="Enter job ID (e.g., abc12345...)"
          value={manualId}
          onChange={(e) => setManualId(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleManualLoad()
          }}
          className="max-w-xs"
        />
        <Button onClick={handleManualLoad} disabled={!manualId.trim()}>
          <Search className="h-4 w-4 mr-2" />
          Load
        </Button>
      </div>
    </div>
  )
}
