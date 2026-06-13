import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { WorkspaceLineageStrip } from './WorkspaceLineageStrip'
import type { WorkspaceLineage } from '@/hooks/use-workspaces'
import type { WorkspaceDetail } from '@/types/api'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

let mockLineage: { data: WorkspaceLineage | undefined } = { data: undefined }

vi.mock('@/hooks/use-workspaces', () => ({
  useWorkspaceLineage: () => mockLineage,
}))

const detailOf = (id: string, name: string | null): WorkspaceDetail =>
  ({ workspace_id: id, name }) as WorkspaceDetail

function renderStrip(onLoadAncestor = vi.fn()) {
  render(<WorkspaceLineageStrip workspaceId={'a'.repeat(32)} onLoadAncestor={onLoadAncestor} />)
  return onLoadAncestor
}

describe('WorkspaceLineageStrip', () => {
  it('renders nothing when the workspace has no lineage', () => {
    mockLineage = {
      data: {
        entries: [
          { workspace_id: 'a'.repeat(32), name: 'solo', deleted: false, detail: detailOf('a'.repeat(32), 'solo') },
        ],
        truncated: false,
      },
    }
    renderStrip()
    expect(screen.queryByTestId('workspace-lineage')).toBeNull()
  })

  it('renders the chain newest → original with clickable ancestors', () => {
    const parentDetail = detailOf('b'.repeat(32), 'parent')
    mockLineage = {
      data: {
        entries: [
          { workspace_id: 'a'.repeat(32), name: 'child', deleted: false, detail: detailOf('a'.repeat(32), 'child') },
          { workspace_id: 'b'.repeat(32), name: 'parent', deleted: false, detail: parentDetail },
          { workspace_id: 'c'.repeat(32), name: 'origin', deleted: false, detail: detailOf('c'.repeat(32), 'origin') },
        ],
        truncated: false,
      },
    }
    const onLoadAncestor = renderStrip()
    const strip = screen.getByTestId('workspace-lineage')
    const text = strip.textContent ?? ''
    // Order: current first, then parents.
    expect(text.indexOf('child')).toBeLessThan(text.indexOf('parent'))
    expect(text.indexOf('parent')).toBeLessThan(text.indexOf('origin'))
    fireEvent.click(screen.getByText('parent'))
    expect(onLoadAncestor).toHaveBeenCalledWith(parentDetail)
  })

  it('renders the deleted-ancestor sentinel without erroring', () => {
    mockLineage = {
      data: {
        entries: [
          { workspace_id: 'a'.repeat(32), name: 'child', deleted: false, detail: detailOf('a'.repeat(32), 'child') },
          { workspace_id: 'b'.repeat(32), name: null, deleted: true, detail: null },
        ],
        truncated: false,
      },
    }
    renderStrip()
    expect(screen.getByTestId('workspace-lineage').textContent).toContain('(original deleted)')
  })

  it('renders a trailing ellipsis when the chain is depth-capped', () => {
    mockLineage = {
      data: {
        entries: [
          { workspace_id: 'a'.repeat(32), name: 'child', deleted: false, detail: detailOf('a'.repeat(32), 'child') },
          { workspace_id: 'b'.repeat(32), name: 'parent', deleted: false, detail: detailOf('b'.repeat(32), 'parent') },
        ],
        truncated: true,
      },
    }
    renderStrip()
    expect(screen.getByTestId('workspace-lineage').textContent).toContain('…')
  })
})
