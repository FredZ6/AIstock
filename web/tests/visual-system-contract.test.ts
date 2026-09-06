import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'app/globals.css'), 'utf8')

describe('visual system contract', () => {
  it('defines one shared spacing, radius, and surface vocabulary', () => {
    for (const token of [
      '--space-page:',
      '--space-section:',
      '--space-row:',
      '--radius-section:',
      '--radius-control:',
      '--surface-section:',
      '--surface-interactive:',
    ]) {
      expect(css).toContain(token)
    }
  })

  it('keeps the product canvas quiet and compact navigation discoverable', () => {
    const bodyRule = css.match(/body\s*\{[^}]+\}/s)?.[0] ?? ''
    const darkBodyRule = css.match(/:root\[data-theme="dark"\]\s+body\s*\{[^}]+\}/s)?.[0] ?? ''

    expect(bodyRule).not.toContain('radial-gradient')
    expect(darkBodyRule).not.toContain('radial-gradient')
    expect(css).not.toMatch(/\.primary-nav::-webkit-scrollbar\s*\{[^}]*display:\s*none/s)
  })
})
