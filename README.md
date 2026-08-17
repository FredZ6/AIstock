# AI Agent 美股科技研究与模拟投资平台

Evidence-grounded US technology research and paper-trading simulation. The current M0
foundation runs in **Fixture Mode** without provider credentials and cannot connect to a live
broker.

## Requirements

- Python 3.12
- uv
- Node.js 22 or newer
- pnpm 11
- Docker with Compose

## Quick start

```bash
make bootstrap
make verify
make up
```

Copy `.env.example` to `.env` only when overriding local defaults. Provider credentials are not
required for M0.

## Safety boundary

This repository is for research and paper trading only. It contains no live-broker URL,
credential, switch, endpoint, or order execution path.

