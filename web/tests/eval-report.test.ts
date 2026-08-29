import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('server-only', () => ({}))

import { loadEvalReport } from '../lib/server/eval-report'

const originalWorkingDirectory = process.cwd()
const temporaryRoots: string[] = []

afterEach(async () => {
  process.chdir(originalWorkingDirectory)
  await Promise.all(temporaryRoots.splice(0).map((root) => rm(root, { recursive: true })))
})

async function loadReportFrom(raw: string) {
  const root = await mkdtemp(path.join(tmpdir(), 'aistock-eval-report-'))
  temporaryRoots.push(root)
  const webDirectory = path.join(root, 'web')
  const reportDirectory = path.join(root, 'evals', 'reports', 'latest')
  await mkdir(webDirectory)
  await mkdir(reportDirectory, { recursive: true })
  await writeFile(path.join(reportDirectory, 'summary.json'), raw, 'utf8')
  process.chdir(webDirectory)
  return loadEvalReport()
}

describe('loadEvalReport', () => {
  it.each([
    ['malformed JSON', '{not-json'],
    ['invalid report schema', JSON.stringify({ dataset: {}, metrics: {}, release: {} })],
  ])('returns unavailable for %s instead of failing the page', async (_label, raw) => {
    await expect(loadReportFrom(raw)).resolves.toBeNull()
  })
})
