import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import RootLayout from '../app/layout'

describe('document startup contract', () => {
  it('declares the language used by the English interface', () => {
    expect(renderToStaticMarkup(<RootLayout>Content</RootLayout>)).toContain('lang="en"')
  })

  it('applies the saved theme before body content without depending on hydration', () => {
    const markup = renderToStaticMarkup(<RootLayout>Content</RootLayout>)
    const script = markup.match(/<script[^>]*>([\s\S]*?)<\/script>/)
    expect(script).not.toBeNull()
    expect(markup.indexOf('<script')).toBeLessThan(markup.indexOf('<body'))
    const root = { dataset: { theme: '' } }
    const run = new Function('document', 'localStorage', script![1])
    run({ documentElement: root }, { getItem: () => 'dark' })
    expect(root.dataset.theme).toBe('dark')
    run({ documentElement: root }, { getItem: () => { throw new Error('blocked') } })
    expect(root.dataset.theme).toBe('light')
  })
})
