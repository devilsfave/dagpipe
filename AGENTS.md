# AGENTS.md — DagPipe Project

> **Read `PROJECT_STATUS.md` BEFORE doing anything.** It has the current phase, what's done, and what to do next.

## What Is DagPipe

A zero-cost LLM pipeline orchestrator + suite of revenue-generating products:
1. **Core Library** — pip-installable DAG orchestrator that chains LLM calls across free-tier providers with checkpointing, structured output, and model routing
2. **MCP Servers** — Payment (MTN MoMo, M-Pesa) and deployment (Cloudflare) tools for AI agents
3. **Apify Actors** — Marketplace products for structured data extraction

## Owner Context

Herbert is in Ghana. He is NOT a developer — he uses AI agents (Antigravity, Cursor, Claude Code) to build. Sessions change frequently due to context window limits. **That's why `PROJECT_STATUS.md` and `HANDOFF.md` exist.** Update them religiously.

## Rules

1. Read `PROJECT_STATUS.md` before ANY work
2. Update `PROJECT_STATUS.md` after completing ANY task
3. Zero paid dependencies — every tool/API must have a free tier
4. Python 3.12 on Windows. Test with Windows paths
5. No file > 400 lines
6. Type hints on all function signatures
7. Write pytest tests for all new code
8. Run `pytest` before declaring work complete

## Project Structure

```
dagpipe/
├── AGENTS.md                ← THIS FILE
├── PROJECT_STATUS.md        ← CURRENT STATE (read first, update always)
├── HANDOFF.md               ← SESSION TRANSITION TEMPLATE
├── pyproject.toml           ← Package config (pip installable)
├── README.md                ← Public-facing (GitHub/PyPI)
├── src/
│   └── dagpipe/
│       ├── __init__.py
│       ├── dag.py           ← Core DAG orchestrator (from amm/dag.py)
│       ├── router.py        ← Multi-LLM router (from amm/router.py)
│       ├── constrained.py   ← Pydantic-validated output (from amm/constrained.py)
│       ├── checkpoints.py   ← JSON checkpoint/resume (from amm/checkpoints.py)
│       └── version.py       ← Live package version fetch (from amm/version_fetcher.py)
├── servers/
│   ├── mtn-momo/            ← MCP: MTN Mobile Money
│   ├── mpesa-daraja/        ← MCP: M-Pesa Kenya
│   └── deploy-cloudflare/   ← MCP: Cloudflare deployment
├── actors/
│   └── structured-extract/  ← Apify: PDF/doc data extraction
├── tests/
│   ├── test_dag.py
│   ├── test_router.py
│   ├── test_constrained.py
│   └── test_checkpoints.py
├── templates/               ← YAML pipeline templates (Gumroad product)
│   └── content-pipeline.yaml
└── docs/
    └── strategy.md          ← Link to implementation_plan.md
```

## Source Code to Reuse

The legacy AMM codebase is at `C:\Users\GASMILA\dagpipe\legacy\amm\`. Key files:

| Legacy File | Reuse As | Lines | Notes |
|---|---|---|---|
| `dag.py` | `src/dagpipe/dag.py` | ~400 | Core DAG engine. Refactor: remove AMM-specific imports, make generic |
| `router.py` | `src/dagpipe/router.py` | ~137 | Model router. Keep: complexity scoring, free-tier budget tracking |
| `constrained.py` | `src/dagpipe/constrained.py` | ~182 | Crown jewel. Keep: Pydantic validation, retry with error feedback |
| `checkpoints.py` | `src/dagpipe/checkpoints.py` | ~60 | JSON checkpoint/resume. Keep as-is |
| `version_fetcher.py` | `src/dagpipe/version.py` | ~60 | Live npm versions. Keep for auto-migrator |
| `db.py` | `src/dagpipe/logging.py` | ~120 | SQLite logging. Refactor: make optional |
| `nodes.py` | `servers/deploy-cloudflare/` | ~550 | Extract ONLY the deploy logic |

## Revenue Phases

| Phase | What | When | Revenue Target |
|---|---|---|---|
| 1 | Freelance MVP service | Week 1-4 | $1.5K/mo |
| 2 | Open-source library on PyPI/GitHub | Month 1-2 | $500-1.5K/mo |
| 3 | MCP servers + Apify actors | Month 2-4 | $500-2K/mo |
| 4 | Auto-migrator vertical | Month 3-6 | $3-8K/mo |

## Tech Stack

| Tool | Purpose | Cost |
|---|---|---|
| Python 3.12 | Core | Free |
| FastMCP 3.0 | MCP servers | Free |
| Pydantic | Schema validation | Free |
| pytest | Testing | Free |
| Modal | 7B LLM hosting | Free (30 GPU-sec/day) |
| Groq | Llama 3.3 70B | Free (30 req/min) |
| Gemini Flash | Backup LLM | Free tier |
| Smithery | MCP marketplace | Free listing |
| Apify | Actor marketplace | Free + 80% rev share |
| Cloudflare | Deployment | Free (500 builds/mo) |
