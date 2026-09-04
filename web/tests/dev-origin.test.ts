import { expect, it } from 'vitest'

import config from '../next.config'

it('permits only the supported loopback development origins', () => {
  expect(config.allowedDevOrigins).toEqual(['localhost', '127.0.0.1'])
})
