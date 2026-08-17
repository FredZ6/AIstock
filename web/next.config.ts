import type { NextConfig } from 'next'

const config: NextConfig = {
  outputFileTracingRoot: new URL('.', import.meta.url).pathname,
}

export default config
