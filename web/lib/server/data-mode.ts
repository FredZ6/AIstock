import 'server-only'

export type WebDataMode = 'api' | 'fixture'

type Environment = Readonly<Record<string, string | undefined>>

export function readWebDataMode(environment: Environment): WebDataMode {
  const mode = environment.WEB_DATA_MODE
  if (mode !== 'api' && mode !== 'fixture') {
    throw new TypeError('WEB_DATA_MODE must be explicitly set to api or fixture')
  }
  return mode
}

export function readApiBaseUrl(environment: Environment): string {
  const value = environment.API_BASE_URL
  try {
    const url = new URL(value ?? '')
    if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new TypeError()
    return url.toString()
  } catch {
    throw new TypeError('API_BASE_URL must be an absolute HTTP(S) URL in API mode')
  }
}
