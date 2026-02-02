type StatusVariant = 'success' | 'warning' | 'error' | 'info' | 'pending'

// Helper function to get variant from status string
export function getStatusVariant(status: string): StatusVariant {
  const statusMap: Record<string, StatusVariant> = {
    success: 'success',
    completed: 'success',
    active: 'success',
    running: 'info',
    pending: 'pending',
    failed: 'error',
    error: 'error',
    cancelled: 'warning',
    archived: 'warning',
    awaiting_approval: 'warning',
    expired: 'error',
    closed: 'warning',
  }
  return statusMap[status.toLowerCase()] ?? 'pending'
}
