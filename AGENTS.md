# Repository instructions

- Notion v0.2 is the product and engineering source of truth.
- Implement milestone tasks in order with test-driven development.
- Use UTC internally and reject naive datetimes.
- Use `Decimal` for money; never use binary floating point.
- This product supports research and paper trading only. Never add live-broker endpoints,
  credentials, configuration flags, or execution paths.
- Historical queries must enforce `available_at <= decision_time`.
- Run `make verify` and record evidence in `docs/progress.md` before milestone review.

