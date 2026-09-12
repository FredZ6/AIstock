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

  it('uses the theme light-blue surface for Today highlights', () => {
    expect(css).toContain(
      '--surface-highlight: oklch(95.5% 0.025 252);',
    )
    expect(css).toMatch(
      /:root\[data-theme="dark"\]\s*\{[^}]*--surface-highlight:\s*oklch\(24% 0\.032 252\)/s,
    )
    expect(css).toMatch(
      /:root\[data-theme="dark"\]\s+\.state-surface\[data-state="degraded"\][^{]*\{[^}]*background:\s*var\(--surface-highlight\)/s,
    )

    for (const selector of [
      '\\.state-surface\\[data-state="degraded"\\][^{]*',
      '\\.metric-list div',
      '\\.watchlist-heatmap li',
      '\\.watchlist-heatmap li\\[data-direction="negative"\\]',
    ]) {
      expect(css).toMatch(
        new RegExp(`${selector}\\s*\\{[^}]*background:\\s*var\\(--surface-highlight\\)`, 's'),
      )
    }
  })

  it('contains the TradingView overview in a keyboard-scrollable mobile viewport', () => {
    expect(css).toMatch(
      /@media \(max-width: 48rem\)[\s\S]*\.market-widget-symbol-overview \.tradingview-widget-container\s*\{[^}]*overflow-x:\s*auto/s,
    )
    expect(css).toMatch(
      /@media \(max-width: 48rem\)[\s\S]*\.market-widget-symbol-overview \.tradingview-widget-container__widget\s*\{[^}]*min-width:/s,
    )
  })
})
