import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ModelFamilyBadge } from './model-family-badge'

afterEach(cleanup)

// MLZOO-D / PRP-31 — closes the test-requirements.md gap flagged by
// prp-quality-agent (M3). Three trivial cases: one per family.

describe('ModelFamilyBadge', () => {
  it('renders the baseline family with the secondary variant', () => {
    render(<ModelFamilyBadge family="baseline" />)
    const badge = screen.getByTestId('model-family-badge')
    expect(badge).toBeTruthy()
    expect(badge.getAttribute('data-family')).toBe('baseline')
    expect(badge.className).toContain('bg-secondary')
    expect(screen.getByText('Baseline')).toBeTruthy()
  })

  it('renders the tree family with the default (primary) variant', () => {
    render(<ModelFamilyBadge family="tree" />)
    const badge = screen.getByTestId('model-family-badge')
    expect(badge.getAttribute('data-family')).toBe('tree')
    expect(badge.className).toContain('bg-primary')
    expect(screen.getByText('Tree')).toBeTruthy()
  })

  it('renders the additive family with the outline variant', () => {
    render(<ModelFamilyBadge family="additive" />)
    const badge = screen.getByTestId('model-family-badge')
    expect(badge.getAttribute('data-family')).toBe('additive')
    expect(badge.className).toContain('border-border')
    expect(screen.getByText('Additive')).toBeTruthy()
  })
})
