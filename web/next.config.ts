import type { NextConfig } from 'next'

const config: NextConfig = {
  allowedDevOrigins: ['localhost', '127.0.0.1'],
  outputFileTracingRoot: new URL('.', import.meta.url).pathname,
}

export default config
