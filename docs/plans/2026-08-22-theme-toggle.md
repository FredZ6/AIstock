# Theme Toggle Implementation Plan

> **For Codex:** Use `superpowers:executing-plans`, `superpowers:test-driven-development`, and `ponytail` to implement this plan.

**Goal:** Add an accessible top-right button that switches between the existing light palette and a persistent dark palette.

**Architecture:** Keep theme state in `AppShell`, set `data-theme="dark"` on the document root, and persist the explicit choice in `localStorage`. Reuse the existing CSS variables so every page changes theme without component-specific branches or a new dependency.

**Tech Stack:** React 19, browser storage, CSS custom properties, Vitest, Testing Library.

---

### Task 1: Persistent theme toggle

**Files:**
- Modify: `web/tests/product-shell.test.tsx`
- Modify: `web/components/layout/app-shell.tsx`
- Modify: `web/app/globals.css`

1. Write a failing shell test that clicks `Switch to dark mode` and asserts `data-theme="dark"`, the inverse label, and persisted storage.
2. Run `pnpm --dir web exec vitest run tests/product-shell.test.tsx` and confirm it fails because the control does not exist.
3. Add the smallest client-side toggle using `useState`, `useEffect`, `document.documentElement.dataset.theme`, and `localStorage`.
4. Add one dark token override plus compact button layout; retain focus, active, reduced-motion, and responsive behavior.
5. Run the local test, complete Web tests, Playwright, and `make verify`.
