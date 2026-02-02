import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { JobListResponse, Job, JobCreate, JobStatus, JobType } from '@/types/api'

interface UseJobsParams {
  page: number
  pageSize: number
  jobType?: JobType
  status?: JobStatus
  enabled?: boolean
}

export function useJobs({
  page,
  pageSize,
  jobType,
  status,
  enabled = true,
}: UseJobsParams) {
  return useQuery({
    queryKey: ['jobs', { page, pageSize, jobType, status }],
    queryFn: () =>
      api<JobListResponse>('/jobs', {
        params: {
          page,
          page_size: pageSize,
          job_type: jobType,
          status,
        },
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 5000, // Poll every 5 seconds
    enabled,
  })
}

export function useJob(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ['jobs', jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled: enabled && !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 2000 : false
    },
  })
}

export function useCreateJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: JobCreate) =>
      api<Job>('/jobs', { method: 'POST', body: data }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      api<void>(`/jobs/${jobId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}
