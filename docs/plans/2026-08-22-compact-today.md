# Compact Today Implementation Plan

> **For Codex:** Use `superpowers:executing-plans`, `superpowers:test-driven-development`, `apple-design`, and `ponytail`.

**Goal:** Surface market and portfolio facts earlier without removing fixture or provider-safety context.

**Architecture:** Move Fixture Mode into the Today header metadata and add an opt-in compact presentation to the existing shared state boundary. Use Today-scoped CSS to reduce title, spacing, and status height while preserving semantic roles and screen-reader detail.

**Tech Stack:** React 19, CSS, Vitest, Testing Library, Playwright.

---

1. Add a failing Today test requiring Fixture Mode inside the heading and a compact degraded status.
2. Run the focused test and confirm RED.
3. Move the fixture note, add the smallest `compact` StateBoundary prop, and add responsive CSS.
4. Run focused tests, `make verify`, and desktop/mobile browser checks.
