# MinIO orphan cleanup — 2026-09-02

## Scope and classification

- Bucket: `fixture-raw`
- Inventory before cleanup: 3,375 objects
- PostgreSQL raw-object keys: 3,429
- Reporter candidates before classification: 23
- Confirmed integration-test leftovers: 20
- Retained operational recovery envelopes: 3

The 20 deleted candidates were written by alerting integration scenarios and were left
behind when their isolated PostgreSQL transactions/databases were discarded. Symbols
`AMD`, `CUT`, `GAP`, `LATE`, `OBJ`, and `REV` map directly to
`backend/tests/integration/alerting/test_market_replay.py`; the `NVDA` objects use the
same legacy test writer and dated fixture payloads. Every candidate had zero exact
references in `raw_data_object` at deletion review time.

The three `live/ALPACA/stream-recovery/` objects were retained. Each recovery envelope
points to a `live/ALPACA/stream/iex/` raw object that exists in MinIO and has committed
PostgreSQL lineage. Recovery envelopes are operational metadata, not
`raw_data_object.raw_object_key` values, so the orphan reporter now excludes that
prefix while continuing to report the corresponding raw object if persistence fails.

## Deleted exact keys

| Key | Bytes | SHA-256 |
| --- | ---: | --- |
| `alpaca-stream/amd/2026/08/20/9c300500b040bb87436d1362ca9c60fb31f5dfa3febad8966b842e7557f5ebc2.json` | 119 | `9c300500b040bb87436d1362ca9c60fb31f5dfa3febad8966b842e7557f5ebc2` |
| `alpaca-stream/cut/2026/08/20/6d82e54e7974df16daae97f656592f5c19f25e08b82658cb9472da365cd3d566.json` | 119 | `6d82e54e7974df16daae97f656592f5c19f25e08b82658cb9472da365cd3d566` |
| `alpaca-stream/cut/2026/08/20/87bd9a45496459bbfb1f28b81705198a55cbb0d731f630f557820b5fada9ee2d.json` | 119 | `87bd9a45496459bbfb1f28b81705198a55cbb0d731f630f557820b5fada9ee2d` |
| `alpaca-stream/gap/2026/08/19/cc83209c36bc0df3dab99d487452bbb76a9f95c78494b4c7f698de16b1dae8f8.json` | 119 | `cc83209c36bc0df3dab99d487452bbb76a9f95c78494b4c7f698de16b1dae8f8` |
| `alpaca-stream/gap/2026/08/20/2b83ddab4d1c420b8677ee6a6fa27d9a7f2e9e9820e2622b8dc21ace04b26c1b.json` | 119 | `2b83ddab4d1c420b8677ee6a6fa27d9a7f2e9e9820e2622b8dc21ace04b26c1b` |
| `alpaca-stream/gap/2026/08/20/45877e88b2151c1d1d74d19587d7e65a8f88b4bdcaa2e4165ca700aa8591a20f.json` | 119 | `45877e88b2151c1d1d74d19587d7e65a8f88b4bdcaa2e4165ca700aa8591a20f` |
| `alpaca-stream/late/2026/08/20/033b5c6497ba9a71727a8e280cfd68977c3adaa75e0d3d5c2f5400c22770abf7.json` | 120 | `033b5c6497ba9a71727a8e280cfd68977c3adaa75e0d3d5c2f5400c22770abf7` |
| `alpaca-stream/late/2026/08/20/89d23482e711b547148cbeea9fde73b07dbf9394542528a48bc8ac6af97af69c.json` | 122 | `89d23482e711b547148cbeea9fde73b07dbf9394542528a48bc8ac6af97af69c` |
| `alpaca-stream/nvda/2026/08/19/a0ba58a5a7ee2f16145d8695283bed6020e9cade90c790ab270714080628adfd.json` | 118 | `a0ba58a5a7ee2f16145d8695283bed6020e9cade90c790ab270714080628adfd` |
| `alpaca-stream/nvda/2026/08/20/0a88245bf9efad88adaefc182238117695faf653fab2aec7a4447f720b948707.json` | 120 | `0a88245bf9efad88adaefc182238117695faf653fab2aec7a4447f720b948707` |
| `alpaca-stream/nvda/2026/08/20/38ad892e9c4853f4764e399349618e779c3045c6968ee4412f30942b8027ac38.json` | 122 | `38ad892e9c4853f4764e399349618e779c3045c6968ee4412f30942b8027ac38` |
| `alpaca-stream/nvda/2026/08/20/607dcaef25a365369c86c6f5dc26e0a983af5ed8454a0df12843da4bd351e3ee.json` | 122 | `607dcaef25a365369c86c6f5dc26e0a983af5ed8454a0df12843da4bd351e3ee` |
| `alpaca-stream/nvda/2026/08/20/674112cd130b5b67e686a46f32b12ade1029cdc6bb0f07170074076f5e168593.json` | 120 | `674112cd130b5b67e686a46f32b12ade1029cdc6bb0f07170074076f5e168593` |
| `alpaca-stream/nvda/2026/08/20/82404f140212d3caa8bd4e9a6a4c64e2612fb4824799ad593f83105e661f3287.json` | 124 | `82404f140212d3caa8bd4e9a6a4c64e2612fb4824799ad593f83105e661f3287` |
| `alpaca-stream/nvda/2026/08/20/b09a09b3a90bb647ece3fe9f86a111e6b90e58594fbc244d7ed81c72c25f816f.json` | 121 | `b09a09b3a90bb647ece3fe9f86a111e6b90e58594fbc244d7ed81c72c25f816f` |
| `alpaca-stream/nvda/2026/08/20/e6c1c76dddfd8c850afe637772b764971d1e7d2a206676b5e5c72bbb3c75b39c.json` | 120 | `e6c1c76dddfd8c850afe637772b764971d1e7d2a206676b5e5c72bbb3c75b39c` |
| `alpaca-stream/nvda/2026/08/20/ec14b55a8ef4efd88c48b458949412db916df0bbbcfe07e0b3e0fceb65877619.json` | 120 | `ec14b55a8ef4efd88c48b458949412db916df0bbbcfe07e0b3e0fceb65877619` |
| `alpaca-stream/obj/2026/08/20/31ec4b974cff043332f2281a51b4df3b882ccec4e9bc2e328a491d5a8c3c9edb.json` | 119 | `31ec4b974cff043332f2281a51b4df3b882ccec4e9bc2e328a491d5a8c3c9edb` |
| `alpaca-stream/rev/2026/08/20/c6eff998ce537f7fa37f9bf0d3b17e752714034438ff0fb4702ffa977a3c9ad8.json` | 119 | `c6eff998ce537f7fa37f9bf0d3b17e752714034438ff0fb4702ffa977a3c9ad8` |
| `alpaca-stream/rev/2026/08/20/cf9b2440fb2fe1572eb9a4ad6d8059238bee53503ddf11c73048f2d0f918ca05.json` | 129 | `cf9b2440fb2fe1572eb9a4ad6d8059238bee53503ddf11c73048f2d0f918ca05` |

## Retained recovery envelopes

- `live/ALPACA/stream-recovery/iex/20260831T042506.693746Z-c67e491ecde006179aa4c85e6f0e28e3e8a7118191b45bd9c0e4d472cab78d3f.json`
- `live/ALPACA/stream-recovery/iex/20260831T121353.254669Z-41a375366f7c21c9ac21d813140c133037f4a146b1fd6a070b41624941b0c899.json`
- `live/ALPACA/stream-recovery/iex/20260831T121527.668732Z-c67e491ecde006179aa4c85e6f0e28e3e8a7118191b45bd9c0e4d472cab78d3f.json`

## Verification evidence

- Focused TDD regression: `2 passed, 10 deselected` (exit 0).
- Exact guarded deletion: 20 deleted, 3,355 MinIO objects remain, and all 3 recovery
  envelopes were retained (exit 0).
- Post-delete reporter: 0 actionable orphans; all 3 recovery targets exist in MinIO and
  all 3 have PostgreSQL lineage (exit 0).
- The first full gate recreated the same 20 objects and exposed the remaining root cause:
  `test_market_replay.py` used the runtime `fixture-raw` bucket. Its module fixture now
  creates a unique `alert-e2e-*` bucket and removes the bucket in teardown; the raw-byte
  assertion reads through that isolated store. The complete alerting file passed 10/10,
  and the runtime orphan report remained 0 afterward.
- Final fresh `make verify`: 320 files format clean; Ruff passed; strict Mypy passed over 279
  source files; Alembic found no drift; backend 715 passed / 4 skipped; frontend
  TypeScript and ESLint passed; Vitest 22 files / 125 tests passed; Next.js production
  build passed (exit 0).
- Post-gate runtime proof: 3,355 objects, 0 actionable orphans, 3 retained recovery
  envelopes, and all 3 target lineage rows intact (exit 0).
- The default Celery Worker was gracefully restarted to load the new reporter. Online
  task `50f2f84e-630d-4804-a1a2-1d9dbc4c6a48` completed successfully with result `0`.
