const companyBySymbol: Record<string, string> = {
  AAPL: 'Apple Inc.',
  AMD: 'Advanced Micro Devices, Inc.',
  AVGO: 'Broadcom Inc.',
  BE: 'Bloom Energy Corporation',
  GOOG: 'Alphabet Inc.',
  INTC: 'Intel Corporation',
  META: 'Meta Platforms, Inc.',
  MRVL: 'Marvell Technology, Inc.',
  MSFT: 'Microsoft Corporation',
  MU: 'Micron Technology, Inc.',
  NBIS: 'Nebius Group N.V.',
  NVDA: 'NVIDIA Corporation',
  SKHY: 'Sky Harbour Group Corporation',
  SNDK: 'Sandisk Corporation',
  TSLA: 'Tesla, Inc.',
  TSM: 'Taiwan Semiconductor Manufacturing Company',
  WDC: 'Western Digital Corporation',
}

export function companyName(symbol: string) {
  return companyBySymbol[symbol] ?? 'Company name unavailable'
}
