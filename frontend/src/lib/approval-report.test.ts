import { describe, it, expect } from 'vitest'
import { formatApprovalReport } from './approval-report'
import type { ApprovalResponse } from '@/types/api'

describe('formatApprovalReport', () => {
  it('reports a successful execution', () => {
    const res: ApprovalResponse = {
      action_id: 'a1',
      approved: true,
      status: 'executed',
      result: { alias_name: 'champion' },
    }
    const msg = formatApprovalReport('create_alias', res)
    expect(msg).toContain('✅')
    expect(msg).toContain('create_alias')
    expect(msg).toContain('executed successfully')
  })

  it('reports an approved-but-failed execution with the error cause', () => {
    // The backend marks a failed execution `rejected` with the cause in result.error.
    const res: ApprovalResponse = {
      action_id: 'a2',
      approved: true,
      status: 'rejected',
      result: { error: 'Run not found: 3c5d', error_type: 'ValueError' },
    }
    const msg = formatApprovalReport('create_alias', res)
    expect(msg).toContain('❌')
    expect(msg).toContain('could not be executed')
    expect(msg).toContain('Run not found: 3c5d')
  })

  it('reports an operator rejection (no execution)', () => {
    const res: ApprovalResponse = {
      action_id: 'a3',
      approved: false,
      status: 'rejected',
      result: null,
    }
    const msg = formatApprovalReport('archive_run', res)
    expect(msg).toContain('🚫')
    expect(msg).toContain('Rejected')
    expect(msg).toContain('No action was taken')
  })

  it('reports an expired approval', () => {
    const res: ApprovalResponse = {
      action_id: 'a4',
      approved: true,
      status: 'expired',
      result: null,
    }
    const msg = formatApprovalReport('save_scenario', res)
    expect(msg).toContain('⏰')
    expect(msg).toContain('expired')
  })

  it('does not throw on a non-object result', () => {
    const res: ApprovalResponse = {
      action_id: 'a5',
      approved: true,
      status: 'executed',
      result: 'ok',
    }
    expect(() => formatApprovalReport('create_alias', res)).not.toThrow()
  })
})
