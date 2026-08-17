import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Home from '../app/page'

describe('home page', () => {
  it('shows the product name and fixture mode', () => {
    render(<Home />)
    expect(screen.getByRole('heading', { name: 'AI Agent 美股科技研究与模拟投资平台' })).toBeInTheDocument()
    expect(screen.getByText('Fixture Mode')).toBeInTheDocument()
  })
})
