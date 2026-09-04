import type { ReactNode } from 'react'
import type { Metadata } from 'next'

import './globals.css'

export const metadata: Metadata = {
  title: 'AI Stock Research · Paper Trading',
  description: 'Evidence-bounded technology research and paper trading workspace.',
}

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: "try{document.documentElement.dataset.theme=localStorage.getItem('theme')==='dark'?'dark':'light'}catch{document.documentElement.dataset.theme='light'}" }} />
      </head>
      <body>{children}</body>
    </html>
  )
}
