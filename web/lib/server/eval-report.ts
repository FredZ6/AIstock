import 'server-only'

import { readFile } from 'node:fs/promises'
import path from 'node:path'

import type { EvalAdminSnapshot } from '../product-types'

const artifactPath = 'evals/reports/latest/summary.json'
const selectedMetrics = [
  ['Tool selection F1', 'tool_selection_f1'],
  ['Research task success', 'research_task_success'],
  ['Evidence coverage', 'evidence_coverage'],
  ['Point-in-time leakage rate', 'point_in_time_leakage_rate'],
  ['Live trading calls', 'live_trading_call_count'],
] as const

type JsonRecord = Record<string, unknown>

function record(value: unknown, field: string): JsonRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(`${field} must be an object`)
  }
  return value as JsonRecord
}

function text(value: unknown, field: string): string {
  if (typeof value !== 'string') throw new TypeError(`${field} must be a string`)
  return value
}

export async function loadEvalReport(): Promise<EvalAdminSnapshot['evaluation']> {
  const absolutePath = path.resolve(process.cwd(), '..', artifactPath)
  let raw: string
  try {
    raw = await readFile(absolutePath, 'utf8')
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null
    throw error
  }

  try {
    const summary = record(JSON.parse(raw), 'summary')
    const dataset = record(summary.dataset, 'summary.dataset')
    const release = record(summary.release, 'summary.release')
    const metrics = record(summary.metrics, 'summary.metrics')
    const caseCount = dataset.case_count
    if (!Number.isInteger(caseCount) || Number(caseCount) < 1) {
      throw new TypeError('summary.dataset.case_count must be a positive integer')
    }
    if (typeof release.passed !== 'boolean') {
      throw new TypeError('summary.release.passed must be a boolean')
    }

    return {
      artifactPath,
      caseCount: Number(caseCount),
      datasetVersion: text(dataset.dataset_version, 'summary.dataset.dataset_version'),
      metrics: selectedMetrics.map(([label, key]) => ({
        label,
        value: text(record(metrics[key], `summary.metrics.${key}`).value, `summary.metrics.${key}.value`),
      })),
      mode: text(dataset.mode, 'summary.dataset.mode'),
      passed: release.passed,
      policyVersion: text(release.policy_version, 'summary.release.policy_version'),
    }
  } catch {
    return null
  }
}
