import type { ReactNode } from 'react'
import type { Metadata } from 'next'

import './globals.css'

export const metadata: Metadata = {
  title: 'AI Stock Research · Paper Trading',
  description: 'Evidence-bounded technology research and paper trading workspace.',
}

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  )
}
