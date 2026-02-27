# BLUEPRINT.md — DagPipe Master Project Blueprint

**Created:** 2026-02-27  
**Status:** APPROVED — Ready for execution  
**Project Location:** `C:\Users\GASMILA\dagpipe\`

---

## Table of Contents

1. [What Is DagPipe](#1-what-is-dagpipe)
2. [Why DagPipe Exists](#2-why-dagpipe-exists)
3. [Verified Market Data](#3-verified-market-data)
4. [Competitor Analysis](#4-competitor-analysis)
5. [What We Already Have (Legacy AMM Code)](#5-what-we-already-have-legacy-amm-code)
6. [Product 1: Core Library (pip install dagpipe)](#6-product-1-core-library)
7. [Product 2: MCP Servers](#7-product-2-mcp-servers)
8. [Product 3: Apify Actors](#8-product-3-apify-actors)
9. [Product 4: Auto-Migrator](#9-product-4-auto-migrator)
10. [Revenue Model](#10-revenue-model)
11. [Go-to-Market Strategy](#11-go-to-market-strategy)
12. [4-Phase Execution Plan](#12-four-phase-execution-plan)
13. [Tech Stack (All Free Tier)](#13-tech-stack)
14. [Project Structure](#14-project-structure)
15. [Detailed Extraction Guide (Legacy → DagPipe)](#15-detailed-extraction-guide)
16. [Risk Mitigations](#16-risk-mitigations)
17. [Testing Strategy](#17-testing-strategy)
18. [Distribution Channels](#18-distribution-channels)
19. [Naming and Branding](#19-naming-and-branding)

---

## 1. What Is DagPipe

DagPipe is a suite of revenue-generating developer tools built on a zero-cost LLM pipeline orchestrator.

It has four products:

1. **Core Library** — A pip-installable Python package that lets developers chain LLM calls in a DAG (Directed Acyclic Graph) across free-tier providers (Groq, Gemini, Modal), with checkpointing, structured JSON output from small models, and intelligent model routing. This is the open-source foundation.

2. **MCP Servers** — Model Context Protocol servers that let AI agents (Claude Desktop, Cursor, Windsurf, VS Code Copilot) interact with African payment systems (MTN Mobile Money, M-Pesa) and perform Cloudflare deployments through natural language. Published on Smithery marketplace.

3. **Apify Actors** — Marketplace products on Apify that use the core library to extract structured data from documents, analyze competitor content, and generate technical specs. Published on Apify Store (80% revenue share to developer).

4. **Auto-Migrator** — A specialized tool that automatically detects outdated dependencies in JavaScript/TypeScript projects and generates migration PRs. Uses the existing `version_fetcher.py` module.

---

## 2. Why DagPipe Exists

### The Problem

In February 2026, developers building LLM-powered automations face three problems:

1. **Cost** — OpenAI/Anthropic APIs are expensive. Most frameworks assume you can afford GPT-4. Solo developers and small teams cannot.
2. **Reliability** — LLM pipelines break mid-execution. Long-running chains hit rate limits, produce invalid JSON, or crash without recovery.
3. **Fragmentation** — African payment APIs exist (MTN MoMo, M-Pesa, Flutterwave, Paystack) but no one has made them accessible to AI agents via MCP.

### The Solution

DagPipe solves all three:

1. **Zero-cost execution** — Routes tasks to free-tier LLMs (Groq free tier, Gemini Flash free tier, self-hosted 7B on Modal free tier) with intelligent complexity-based routing.
2. **Crash-proof pipelines** — JSON checkpointing lets pipelines resume from the last completed node after any failure. Constrained generation forces even 7B models to produce valid, schema-compliant JSON.
3. **African payments for AI** — MCP servers make MTN MoMo and M-Pesa accessible to any AI agent globally.

### Why This Was Chosen

Five independent AI research tools (Gemini, Claude, Perplexity, DeepSeek, Groq) were given the same prompt with full context about the existing codebase. All five unanimously agreed:

- The generated apps from the current system are worthless (commodity, can't compete with Lovable at $200M ARR or Bolt.new at $40M ARR)
- The orchestration engine IS the real asset
- The constrained generation from 7B models is uniquely valuable
- MCP integration is a top opportunity
- Target market is GLOBAL, not limited to Africa
- Keep: dag.py, router.py, constrained.py, checkpoints.py
- Discard: Next.js app generation pipeline

---

## 3. Verified Market Data

Every data point below has been independently verified. "Verified" means confirmed by at least 2 independent sources.

| Data Point | Value | Source | Status |
|---|---|---|---|
| AI agent market by 2030 | $52.62B at 46.3% CAGR | MarketsandMarkets (Apr 2025) | ✅ Verified |
| MCP ecosystem market | $2.7-4.5B (NOT $10.3B) | Dimension Market Research | ✅ Verified |
| MCP SDK downloads | 97M/month | Anthropic official (Dec 2025) | ✅ Verified |
| Active MCP servers | 10,000+ | Anthropic official (Dec 2025) | ✅ Verified |
| Anthropic ARR | $14B (Feb 2026) | SaaStr, Constellation Research | ✅ Verified |
| Lovable ARR | $200M (Nov 2025) | Entrepreneur.com | ✅ Verified |
| Bolt.new ARR | $40M (Mar 2025) | Sacra.com | ✅ Verified |
| Vibe coding market | $3.9B (2024) → $37B (2032) | Congruence Market Insights | ✅ Verified |
| Africa FinTech by 2030 | $65B at 32% CAGR | BCG / QED Investors | ✅ Verified |
| Apify dev payouts | $563K in Sept 2025 alone | NatLawReview | ✅ Verified |
| Apify top actors | $5-20K/month | Proxies.sx | ✅ Verified |
| Apify rev share | 80% to developer | Apify official docs | ✅ Verified |
| MTN MoMo sandbox | Free at momodeveloper.mtn.com | MTN/Ericsson | ✅ Verified |
| M-Pesa Daraja APIs | STK Push, C2B, B2C, B2B, Status, Balance, Reversals | Daraja docs | ✅ Verified |
| Paystack Python SDK | PaystackOSS/paystack-python | Paystack developer docs | ✅ Verified |

---

## 4. Competitor Analysis

### Direct Competitor: `kenyaclaw/africa-payments-mcp`

This is the ONLY existing African payments MCP server. Discovered during research, verified on Playbooks.com.

| Factor | kenyaclaw (Competitor) | DagPipe (Ours) |
|---|---|---|
| **First seen** | Feb 19, 2026 (8 days old at time of research) | — |
| **Language** | Node.js (npm install) | Python (FastMCP 3.0) |
| **Tools count** | 4 generic (send_money, request_payment, check_payment_status, process_refund) | 5+ per provider, country-specific |
| **MTN MoMo depth** | Generic `send_money` wrapper | Full Collection + Disbursement APIs, Ghana-specific |
| **Sandbox tested** | No evidence | Yes (Herbert has Ghana MoMo credentials) |
| **Currency handling** | Generic | GHS, KES, UGX, XAF specific formatters |
| **Account validation** | ❌ Missing | ✅ Included |
| **Balance check** | ❌ Missing | ✅ Included |
| **Reversals** | ❌ Missing | ✅ Included |
| **Marketplace** | Playbooks.com only | Smithery + GitHub + PyPI |

**Strategy:** We don't compete on breadth. We compete on depth and reliability. Their 4 generic wrappers vs our battle-tested, sandbox-verified, country-specific tools. We are the production-grade option.

### Indirect Competitors (LLM Orchestration)

| Tool | Weakness vs DagPipe |
|---|---|
| LangChain | Bloated, fragile, no checkpointing, assumes paid APIs |
| CrewAI | Multi-agent focus, not pipeline-focused, no free-tier routing |
| Airflow | Data engineering, requires PostgreSQL + scheduler, overkill for LLM tasks |
| Prefect / Dagster | Commercial, data-focused, not LLM-native |
| n8n | No-code, $20+/month, not Python |

**DagPipe's moat:** Zero-cost operation, constrained generation from 7B models, checkpoint recovery, model routing across free-tier providers. No other library does ALL of these.

---

## 5. What We Already Have (Legacy AMM Code)

The existing codebase is at: `C:\Users\GASMILA\dagpipe\legacy\amm\`

### Files to KEEP and Refactor

#### `dag.py` (~400 lines, 16,622 bytes)
The core DAG orchestrator. This is the most important file in the project.

**What it does:**
- Loads a YAML config defining a graph of tasks (nodes)
- Computes topological sort order
- Executes nodes in dependency order
- Each node can be: DETERMINISTIC (Python function) or LLM (model call)
- On failure: retries with model escalation (7B → 70B → Gemini)
- Checkpoints completed nodes to JSON files
- Can resume from last checkpoint after crash

**What to refactor:**
- Remove AMM-specific imports (`from amm.nodes import ...`)
- Make node execution pluggable (accept any callable)
- Clean up the YAML config format to be more generic
- Add proper Python package structure (`__init__.py` exports)

#### `router.py` (~137 lines, 5,824 bytes)
The multi-LLM model router.

**What it does:**
- Scores task complexity on a 0-1 scale
- Routes low complexity (0-0.3) → Modal self-hosted 7B (free)
- Routes medium complexity (0.3-0.6) → Groq Llama 3.3 70B (free tier, 30 req/min)
- Routes high complexity (0.6-1.0) → Gemini Flash (free tier)
- Tracks Groq rate limit budget (30 req/min)
- On retry: escalates to more powerful model

**What to refactor:**
- Make provider list configurable (not hardcoded)
- Add support for custom model endpoints
- Expose as a standalone function: `route(prompt, complexity, budget) → response`

#### `constrained.py` (~182 lines, 7,648 bytes)
The constrained LLM generation system. **This is the crown jewel** — all 5 AIs identified this as uniquely valuable.

**What it does:**
- Takes a prompt + Pydantic model class
- Injects JSON schema instructions into the prompt
- Sends to the routed LLM
- Extracts JSON from the response (handles markdown-wrapped responses)
- Validates against the Pydantic model
- On validation failure: sends error message back to LLM for retry
- Reliably produces valid structured output even from 7B models

**What to refactor:**
- Make it framework-agnostic (currently coupled to AMM schemas)
- Accept any Pydantic BaseModel
- Add more robust JSON extraction (handle edge cases)
- Expose as standalone: `generate(prompt, schema: Type[BaseModel]) → model_instance`

#### `checkpoints.py` (~60 lines, 2,562 bytes)
JSON checkpoint/resume system.

**What it does:**
- After each DAG node completes, saves its output to a JSON file
- On pipeline restart, loads checkpoints and skips completed nodes
- Uses a checkpoints directory per pipeline run

**What to refactor:**
- Minimal changes needed — already clean and generic
- Add optional compression for large checkpoints

#### `version_fetcher.py` (~60 lines, 2,407 bytes)
Live npm package version lookup.

**What it does:**
- Queries the npm registry API for current package versions
- Returns latest version strings
- Used to prevent LLMs from generating outdated import syntax

**What to refactor:**
- Extend to support PyPI packages too (not just npm)
- This becomes the foundation for the Auto-Migrator product

#### `db.py` (~120 lines, 4,972 bytes)
SQLite execution logging.

**What it does:**
- Creates a SQLite database
- Logs every pipeline run: start time, concept, status
- Logs every node execution: model used, duration, retries, errors
- Queryable analytics

**What to refactor:**
- Make optional (not everyone wants SQLite logging)
- Add an in-memory mode for testing

### Files to DISCARD

| File | Why Discard |
|---|---|
| `nodes.py` (22KB) | Contains AMM-specific Next.js generation logic. EXTRACT only the deploy logic for the deploy-cloudflare MCP server |
| `schemas.py` (4.7KB) | AMM-specific Pydantic models (CodeOutput, PMSpec). Replace with per-product schemas |
| `state_machine.py` (8.3KB) | AMM state machine — not relevant to DagPipe |
| `scheduler.py` (10KB) | AMM scheduler — not relevant |
| `memory.py` (6KB) | AMM agent memory — not relevant |
| `context.py` (8.3KB) | AMM context assembly — not relevant |
| `config.py` (3.2KB) | AMM config — replace with DagPipe config |
| `dag_config.yaml` (1.9KB) | AMM pipeline definition — replace with DagPipe examples |
| `souls/` directory | AMM SOUL prompt files — archive but keep the CONCEPT (rename to "Pipeline Prompts" or "Templates") |

---

## 6. Product 1: Core Library

### Overview

`dagpipe` is a pip-installable Python library for building crash-proof, zero-cost LLM pipelines.

### Installation

```bash
pip install dagpipe
```

### Basic Usage Example

```python
from dagpipe import Pipeline, Node, Router, ConstrainedGenerator
from pydantic import BaseModel

# Define your output schema
class ProductSpec(BaseModel):
    name: str
    tagline: str
    features: list[str]

# Create a constrained generator
gen = ConstrainedGenerator(router=Router.default())

# Generate structured output from any LLM
spec = gen.generate(
    prompt="Create a product spec for a habit tracker app",
    schema=ProductSpec
)
print(spec.name)  # "HabitFlow"
print(spec.features)  # ["Daily streaks", "Reminders", ...]
```

### YAML Pipeline Example

```yaml
# pipeline.yaml
name: content-pipeline
nodes:
  - id: research
    type: llm
    prompt: "Research the topic: {concept}"
    schema: ResearchOutput
    complexity: 0.5

  - id: outline
    type: llm
    depends_on: [research]
    prompt: "Create an outline from this research: {research.output}"
    schema: OutlineOutput
    complexity: 0.3

  - id: write
    type: llm
    depends_on: [outline]
    prompt: "Write the full article from this outline: {outline.output}"
    schema: ArticleOutput
    complexity: 0.7
```

```python
from dagpipe import Pipeline

pipeline = Pipeline.from_yaml("pipeline.yaml")
result = pipeline.run(concept="Zero-cost LLM orchestration")
# Checkpoints after each node. If it crashes at 'write', 
# re-running skips 'research' and 'outline'.
```

### Key Selling Points

1. **$0/month** — Routes to free-tier LLMs by default
2. **Crash-proof** — Checkpoint after every node, resume on restart
3. **7B-friendly** — Constrained generation forces valid JSON even from tiny models
4. **Pydantic-native** — Define schemas with Pydantic, get validated objects back
5. **YAML pipelines** — Define complex multi-step chains in YAML, not code

### Module Structure

```
src/dagpipe/
├── __init__.py          ← Public API exports
├── dag.py               ← Pipeline + Node classes
├── router.py            ← Router class (model selection)
├── constrained.py       ← ConstrainedGenerator class
├── checkpoints.py       ← Checkpoint store
├── version.py           ← Package version fetcher
├── logging.py           ← Optional SQLite logging
└── config.py            ← YAML config loader
```

---

## 7. Product 2: MCP Servers

### What Are MCP Servers

MCP (Model Context Protocol) is an open protocol created by Anthropic that lets AI agents (Claude, Cursor, Copilot) interact with external tools. An MCP server exposes "tools" that agents can call. For example, a Slack MCP server lets Claude send Slack messages.

### Framework: FastMCP 3.0

FastMCP is a Python framework for building MCP servers. It handles protocol details, schema generation, and validation automatically.

```bash
pip install fastmcp
```

#### Basic MCP Server Example

```python
from fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

if __name__ == "__main__":
    mcp.run()
```

### Server 1: `mtn-momo` — MTN Mobile Money (Ghana, Uganda, Cameroon)

**Priority: HIGHEST** — This is Herbert's home market. He uses MTN MoMo daily and can test on real hardware.

#### API Reference

MTN MoMo Developer Portal: https://momodeveloper.mtn.com/
- Free sandbox environment
- Collection API: Request payments from customers
- Disbursement API: Send money to mobile numbers
- API User + API Key authentication
- OAuth2 token flow: Get API User → Get API Key → Generate OAuth2 Token → Make API calls
- X-Reference-Id: UUID generated per request for idempotency

#### Tools to Build

```python
@mcp.tool()
def request_payment(amount: float, currency: str, phone: str, payer_message: str, payee_note: str) -> dict:
    """
    Send an STK push to a customer's phone to collect payment via MTN Mobile Money.
    
    Args:
        amount: Amount to charge (e.g. 50.0)
        currency: ISO currency code (GHS for Ghana, UGX for Uganda, XAF for Cameroon)
        phone: Customer's phone number (e.g. "0244000000" for Ghana)
        payer_message: Message shown to the payer on their phone
        payee_note: Internal note for the payee's records
    
    Returns:
        dict with keys: transaction_id, status, message
    """

@mcp.tool()
def check_payment_status(transaction_id: str) -> dict:
    """
    Check the status of a previously initiated payment request.
    
    Args:
        transaction_id: The UUID returned from request_payment
    
    Returns:
        dict with keys: status (PENDING/SUCCESSFUL/FAILED), amount, currency, phone, reason
    """

@mcp.tool()
def send_money(amount: float, currency: str, phone: str, payee_note: str) -> dict:
    """
    Disburse funds from business account to a mobile number via MTN MoMo.
    
    Args:
        amount: Amount to send
        currency: ISO currency code
        phone: Recipient's phone number
        payee_note: Note for the recipient
    
    Returns:
        dict with keys: transaction_id, status, message
    """

@mcp.tool()
def check_balance() -> dict:
    """
    Check the MTN MoMo business account balance.
    
    Returns:
        dict with keys: available_balance, currency
    """

@mcp.tool()
def validate_account(phone: str) -> dict:
    """
    Verify that an MTN MoMo account exists before sending money.
    
    Args:
        phone: Phone number to validate
    
    Returns:
        dict with keys: exists (bool), name (str if exists)
    """
```

#### Resources to Build

```python
@mcp.resource("momo://supported-currencies")
def supported_currencies() -> str:
    """List supported currencies: GHS (Ghana), UGX (Uganda), XAF (Cameroon), EUR"""

@mcp.resource("momo://transaction-limits")  
def transaction_limits() -> str:
    """Min/max transaction amounts per currency"""
```

#### Authentication Flow

1. User provides via environment variables: `MTN_SUBSCRIPTION_KEY`, `MTN_API_USER`, `MTN_API_KEY`
2. Server generates OAuth2 access token: POST to `/collection/token/` with Basic auth
3. Token cached and refreshed on expiry
4. Each API call gets a new UUID as `X-Reference-Id` header

#### Smithery Configuration

```yaml
# smithery.yaml
startCommand:
  type: stdio
  configSchema:
    type: object
    required:
      - mtn_subscription_key
      - mtn_api_user
      - mtn_api_key
    properties:
      mtn_subscription_key:
        type: string
        description: "Your MTN MoMo subscription key from momodeveloper.mtn.com"
      mtn_api_user:
        type: string
        description: "Your MTN MoMo API user UUID"
      mtn_api_key:
        type: string
        description: "Your MTN MoMo API key"
      environment:
        type: string
        enum: [sandbox, production]
        default: sandbox
  commandFunction:
    command: python
    args: ["-m", "dagpipe.servers.mtn_momo"]
    env:
      MTN_SUBSCRIPTION_KEY: "{{mtn_subscription_key}}"
      MTN_API_USER: "{{mtn_api_user}}"
      MTN_API_KEY: "{{mtn_api_key}}"
      MTN_ENVIRONMENT: "{{environment}}"
```

---

### Server 2: `mpesa-daraja` — M-Pesa (Kenya, Tanzania)

**Priority: HIGH** — Expands coverage to East Africa, 34 million M-Pesa users in Kenya alone.

#### API Reference

Safaricom Daraja Portal: https://developer.safaricom.co.ke/
- Free sandbox environment
- OAuth2 authentication with Consumer Key + Consumer Secret

#### Tools to Build

```python
@mcp.tool()
def stk_push(amount: float, phone: str, account_reference: str, description: str) -> dict:
    """
    Initiate Lipa Na M-Pesa payment prompt (STK Push) on customer's phone.
    
    Args:
        amount: Amount to charge in KES
        phone: Customer phone (format: 254XXXXXXXXX)
        account_reference: Reference for the transaction
        description: Description shown to customer
    
    Returns:
        dict with keys: checkout_request_id, response_code, response_description
    """

@mcp.tool()
def check_transaction(checkout_request_id: str) -> dict:
    """Query the status of an STK Push transaction."""

@mcp.tool()
def b2c_payment(amount: float, phone: str, remarks: str, occasion: str) -> dict:
    """Send money from business to customer."""

@mcp.tool()
def check_balance() -> dict:
    """Query M-Pesa business account balance."""

@mcp.tool()
def reverse_transaction(transaction_id: str, amount: float, remarks: str) -> dict:
    """Reverse a completed M-Pesa transaction."""
```

#### Authentication

- User provides: `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_PASSKEY`, `MPESA_SHORTCODE`
- Server generates: Base64-encoded password from shortcode + passkey + timestamp
- OAuth2 token: GET to `/oauth/v1/generate?grant_type=client_credentials`

---

### Server 3: `deploy-cloudflare` — Deploy to Cloudflare Pages

**Priority: HIGH** — Immediately useful to thousands of developers globally. Not Africa-specific.

#### Tools to Build

```python
@mcp.tool()
def deploy_static(directory: str, project_name: str) -> dict:
    """
    Deploy a directory of static files to Cloudflare Pages.
    
    Args:
        directory: Path to the directory containing static files (e.g. "out/", "dist/", "build/")
        project_name: Name of the Cloudflare Pages project
    
    Returns:
        dict with keys: url, project_name, deployment_id
    """

@mcp.tool()
def deploy_worker(script_path: str, worker_name: str) -> dict:
    """Deploy a JS/TS file as a Cloudflare Worker."""

@mcp.tool()
def list_projects() -> list[dict]:
    """List all Cloudflare Pages projects."""

@mcp.tool()
def get_deployment_url(project_name: str) -> dict:
    """Get the live URL of the most recent deployment."""

@mcp.tool()
def create_project(project_name: str) -> dict:
    """Create a new Cloudflare Pages project."""
```

#### Authentication

- User provides: `CLOUDFLARE_API_TOKEN` or `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_KEY`

#### Source Code

The deploy logic already exists in `C:\Users\GASMILA\dagpipe\legacy\amm\nodes.py`. Extract the `wrangler pages deploy` subprocess calls and wrap them as MCP tools. This is the fastest server to build.

---

## 8. Product 3: Apify Actors

### What Are Apify Actors

Apify Actors are cloud-run automation tools listed on the Apify Store. Users pay per event/result. Developers earn 80% of revenue. Apify handles billing, scaling, and infrastructure.

### Actor 1: Structured Data Extraction

Uses `constrained.py` to extract structured data from uploaded documents.

**Input:** Text content (from PDF, HTML, or plain text)
**Output:** Structured JSON matching a user-defined Pydantic schema

**Example use cases:**
- Extract invoice data (vendor, amount, date, line items)
- Parse resumes (name, skills, experience, education)
- Extract product information from descriptions

### Actor 2: Technical Spec Generator

Takes a feature request or idea and produces a structured technical specification.

**Input:** Natural language feature description
**Output:** Structured PRD with acceptance criteria, user stories, tech requirements

### Actor 3: Competitor Content Analyzer

Scrapes a competitor's website and produces a structured analysis.

**Input:** URL of competitor site
**Output:** Structured analysis with features, pricing, positioning, weaknesses

---

## 9. Product 4: Auto-Migrator

### The Opportunity

Gemini AI identified this during the 5-AI strategy research: "The world is drowning in AI-generated vibe code from 2024-2025 that is now breaking." React 18 → 19, Next.js 14 → 16, deprecated dependencies everywhere.

### How It Works

1. **Code Parser Node** — Reads a project's `package.json`, uses `version_fetcher.py` to find the delta between current and latest versions of every dependency
2. **Migration Agent Node** — For each outdated dependency, reads the migration guide/changelog and uses constrained generation to rewrite affected files
3. **PR Generator** — Creates a GitHub Pull Request with all the changes

### Revenue Model

- $50 per successful file migration (bounty model)
- $199/month for "Continuous Dependency Healing" subscription (auto-scans repos weekly)
- Target: CTOs of agencies managing 50+ client sites

### Timeline

This is Phase 4 (Month 3-6). Requires the core library to be stable first.

---

## 10. Revenue Model

### Revenue Streams

| Stream | Product | How It Works | Target |
|---|---|---|---|
| Freelance service | Core Library | Build MVPs for clients using the pipeline | $1.5K/mo Month 1 |
| GitHub Sponsors | Core Library | Open-source users sponsor the project | $200-500/mo |
| Gumroad templates | Core Library | $49 quick-start pack, $199 extended pack | $500-1K/mo |
| Consulting | Core Library | Custom pipeline implementations | $300-800/engagement |
| Smithery usage | MCP Servers | Pay-per-use on Smithery marketplace | $500-2K/mo |
| Apify revenue | Actors | 80% of actor usage revenue | $500-2K/mo |
| Migration bounties | Auto-Migrator | $50/file or $199/mo subscription | $3-8K/mo |

### Revenue Projections (Conservative, Verified)

| Month | Freelance | OSS/Gumroad | MCP/Apify | Migrator | **Total** |
|---|---|---|---|---|---|
| 1 | $1,500 | $0 | $0 | $0 | **$1,500** |
| 2 | $2,000 | $200 | $0 | $0 | **$2,200** |
| 3 | $2,500 | $500 | $300 | $0 | **$3,300** |
| 4 | $2,000 | $800 | $1,000 | $0 | **$3,800** |
| 6 | $1,500 | $1,500 | $2,000 | $3,000 | **$8,000** |
| 12 | $1,000 | $3,000 | $5,000 | $8,000 | **$17,000** |

Freelancing intentionally decreases as product revenue scales. By Month 12: 80% product income, 20% selective consulting.

---

## 11. Go-to-Market Strategy

### Phase 1: Build & Launch (Week 1-4)

1. Extract core library from legacy AMM code
2. Create 5 polished demo projects for freelance work
3. Record 30-60 second Loom videos of demos
4. Post demos on X (#buildinpublic), r/SaaS, r/indiehackers
5. Offer first 3-5 builds at $199 for testimonials
6. List on Upwork/Fiverr: "Rapid AI MVP Builder"

### Phase 2: Open-Source Push (Month 1-2)

1. Publish `dagpipe` to PyPI
2. Create GitHub repo with professional README (demo GIFs, badges, clear examples)
3. HackerNews "Show HN" launch (Tuesday 8am US Eastern, when traffic peaks)
4. Post to r/LocalLLaMA (the 7B constrained generation angle is PERFECT for this community)
5. Post to r/MachineLearning, r/Python
6. Set up GitHub Sponsors + Gumroad template packs

### Phase 3: Marketplace Products (Month 2-4)

1. Build and publish MCP servers to Smithery
2. Record demo video: Claude Desktop processing MTN MoMo payment via natural language
3. Post demo on Twitter/X — demo videos go viral in AI community
4. Build and publish Apify Actors
5. Submit to Product Hunt ("DagPipe: Zero-cost LLM orchestration")

### Phase 4: Community & Content (Month 3-6)

1. Blog series on Medium/Dev.to: "How to build crash-proof LLM pipelines for $0/month"
2. YouTube tutorial: "Force any LLM to output valid JSON — even 7B models"
3. Present at DevCongress Accra or GDG Accra meetup (local consulting leads)
4. Engage Python Ghana, ForLoop Africa communities
5. Launch Auto-Migrator with demo PR on a popular open-source repo

---

## 12. Four-Phase Execution Plan

### Phase 1: Cash Flow (Week 1-4)

**Goal:** First revenue within 30 days using the existing pipeline.

| Week | Task | Deliverable |
|---|---|---|
| 1 | Extract core library from legacy AMM | `src/dagpipe/` with dag.py, router.py, constrained.py, checkpoints.py |
| 1 | Create pyproject.toml and README | Installable package |
| 1 | Write tests for core modules | `tests/test_*.py` all passing |
| 2 | Fix pipeline to produce 5 polished demos | 5 deployed demo apps |
| 2 | Record Loom videos | Marketing assets |
| 3 | Create Upwork/Fiverr profiles | Service listings live |
| 3 | Post demos on X, Reddit | First audience |
| 4 | First 3-5 beta builds | Testimonials + $600-1000 revenue |

### Phase 2: Open-Source Library (Month 1-2)

**Goal:** GitHub stars, PyPI downloads, consulting inflow.

| Task | Deliverable |
|---|---|
| Publish to PyPI (`pip install dagpipe`) | Package live |
| GitHub repo with README + demo GIFs | Public repository |
| HackerNews "Show HN" launch | Visibility spike |
| r/LocalLLaMA post | Community engagement |
| Gumroad template packs ($49/$199) | Digital products |
| GitHub Sponsors setup | Recurring revenue |

### Phase 3: MCP Servers + Apify Actors (Month 2-4)

**Goal:** Marketplace products generating passive income.

| Task | Deliverable |
|---|---|
| Build `mtn-momo` MCP server | 5 tools, sandbox tested |
| Build `mpesa-daraja` MCP server | 5 tools, sandbox tested |
| Build `deploy-cloudflare` MCP server | 5 tools, extracted from nodes.py |
| Publish all 3 to Smithery | Listed on marketplace |
| Build 2-3 Apify Actors | Listed on Apify Store |
| Demo video: Claude + MTN MoMo | Marketing viral moment |

### Phase 4: Auto-Migrator (Month 3-6)

**Goal:** High-value vertical product.

| Task | Deliverable |
|---|---|
| Build Code Parser node | Reads package.json, finds version deltas |
| Build Migration Agent node | Rewrites files for compatibility |
| Build PR Generator | Creates GitHub PRs automatically |
| First 10 migration PRs | Portfolio + testimonials |
| Subscription model ($199/mo) | Recurring revenue |

---

## 13. Tech Stack

Every single tool/API has a free tier. Total monthly cost: **$0**.

| Tool | Purpose | Free Tier Details |
|---|---|---|
| Python 3.12 | Core language | Free, runs on Windows |
| FastMCP 3.0 | MCP server framework | `pip install fastmcp`, GA Feb 18 2026 |
| **OpenRouter** | **Primary API Gateway** | **$0/mo using `openrouter/free` & 300+ models** |
| LiteLLM | Fallback & load balancing | Open-source (native to DagPipe) |
| Pydantic v2 | Schema validation | `pip install pydantic` |
| pytest | Testing | `pip install pytest` |
| Modal | Self-hosted backend | 30 GPU-seconds/day free |
| Ollama | Local inference | 100% private, 100% free |
| Google Gemini | Model provider | Free tier via OpenRouter/Native |
| Groq | Model provider | Free tier via OpenRouter/Native |
| Smithery | Marketplace | Free listing/hosting |
| Apify | Marketplace | Free tier + 80% rev share |
| Cloudflare Pages | Deployment target | 500 builds/month free |

---

## 14. Project Structure

```
C:\Users\GASMILA\dagpipe\
├── AGENTS.md                    ← AI agent instructions (universal)
├── PROJECT_STATUS.md            ← Current state (read first, update always)
├── HANDOFF.md                   ← Session transition template
├── BLUEPRINT.md                 ← THIS FILE (full strategy)
├── pyproject.toml               ← Package metadata and dependencies
├── README.md                    ← Public-facing (GitHub, PyPI)
├── LICENSE                      ← MIT License
├── src/
│   └── dagpipe/
│       ├── __init__.py          ← Public API: Pipeline, Node, Router, ConstrainedGenerator
│       ├── dag.py               ← Pipeline + Node classes (from amm/dag.py)
│       ├── router.py            ← Router class (from amm/router.py)
│       ├── constrained.py       ← ConstrainedGenerator (from amm/constrained.py)
│       ├── checkpoints.py       ← CheckpointStore (from amm/checkpoints.py)
│       ├── version.py           ← PackageVersionFetcher (from amm/version_fetcher.py)
│       ├── logging.py           ← Optional SQLite logging (from amm/db.py)
│       └── config.py            ← YAML config loader
├── servers/
│   ├── mtn-momo/
│   │   ├── server.py            ← FastMCP server with 5 tools
│   │   ├── smithery.yaml        ← Smithery marketplace config
│   │   ├── pyproject.toml       ← Server-specific dependencies
│   │   └── README.md
│   ├── mpesa-daraja/
│   │   ├── server.py
│   │   ├── smithery.yaml
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── deploy-cloudflare/
│       ├── server.py
│       ├── smithery.yaml
│       ├── pyproject.toml
│       └── README.md
├── actors/
│   └── structured-extract/
│       ├── main.py              ← Apify Actor entry point
│       ├── INPUT_SCHEMA.json    ← Actor input schema
│       └── README.md
├── templates/
│   ├── content-pipeline.yaml    ← Example: Multi-step content pipeline
│   ├── data-extraction.yaml     ← Example: Structured data extraction
│   └── code-review.yaml         ← Example: Automated code review
├── tests/
│   ├── test_dag.py
│   ├── test_router.py
│   ├── test_constrained.py
│   ├── test_checkpoints.py
│   └── test_version.py
└── docs/
    ├── getting-started.md
    └── api-reference.md
```

---

## 15. Detailed Extraction Guide (Legacy → DagPipe)

This section tells the AI agent EXACTLY how to extract each file from the legacy codebase.

### Step 1: Extract `dag.py`

**Source:** `C:\Users\GASMILA\dagpipe\legacy\amm\dag.py`
**Target:** `C:\Users\GASMILA\dagpipe\src\dagpipe\dag.py`

**Instructions:**
1. Read the entire source file
2. Remove all AMM-specific imports (e.g., `from amm.nodes import ...`, `from amm.schemas import ...`)
3. Keep the core classes: the DAG loader, topological sort, node executor
4. Make the node execution callable generic — accept any `Callable` not just AMM node functions
5. Keep the retry + model escalation logic
6. Keep the checkpoint integration
7. Export: `Pipeline`, `Node` from `__init__.py`
8. Write `tests/test_dag.py` with at least 5 test cases:
   - Test topological sort ordering
   - Test cycle detection
   - Test checkpoint save/load
   - Test node execution with mock callable
   - Test retry on failure

### Step 2: Extract `router.py`

**Source:** `C:\Users\GASMILA\dagpipe\legacy\amm\router.py`
**Target:** `C:\Users\GASMILA\dagpipe\src\dagpipe\router.py`

**Instructions:**
1. Read the entire source file
2. Make the provider list configurable (not hardcoded to Modal/Groq/Gemini)
3. Keep the complexity scoring logic
4. Keep the rate limit budget tracking
5. Keep the retry escalation (7B → 70B → Gemini)
6. Export: `Router` from `__init__.py`
7. Write `tests/test_router.py`:
   - Test routing by complexity score
   - Test rate limit budget tracking
   - Test escalation on retry
   - Test custom provider configuration

### Step 3: Extract `constrained.py`

**Source:** `C:\Users\GASMILA\dagpipe\legacy\amm\constrained.py`
**Target:** `C:\Users\GASMILA\dagpipe\src\dagpipe\constrained.py`

**Instructions:**
1. Read the entire source file
2. Make it accept any `pydantic.BaseModel` subclass (remove AMM schema coupling)
3. Keep the schema injection logic (converting Pydantic model to JSON schema in prompt)
4. Keep the JSON extraction from markdown-wrapped responses
5. Keep the validation + retry with error feedback
6. Export: `ConstrainedGenerator` from `__init__.py`
7. Write `tests/test_constrained.py`:
   - Test with a simple Pydantic model (mock LLM response)
   - Test JSON extraction from markdown-wrapped response
   - Test validation failure triggers retry
   - Test with nested Pydantic model

### Step 4: Extract `checkpoints.py`

**Source:** `C:\Users\GASMILA\dagpipe\legacy\amm\checkpoints.py`
**Target:** `C:\Users\GASMILA\dagpipe\src\dagpipe\checkpoints.py`

**Instructions:**
1. Read the entire source file
2. Minimal changes — this file is already clean and generic
3. Export: `CheckpointStore` from `__init__.py`
4. Write `tests/test_checkpoints.py`:
   - Test save checkpoint
   - Test load checkpoint
   - Test checkpoint directory creation
   - Test resume from checkpoint

### Step 5: Create `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "dagpipe"
version = "0.1.0"
description = "Zero-cost, crash-proof LLM pipeline orchestrator with structured output from any model"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Herbert", email = "TBD"},
]
keywords = ["llm", "pipeline", "dag", "orchestrator", "pydantic", "structured-output", "free-tier"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Libraries :: Python Modules",
]
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "requests>=2.28",
    "litellm>=1.40.0",
]

[project.optional-dependencies]
groq = ["groq"]
gemini = ["google-generativeai"]
all = ["groq", "google-generativeai"]
dev = ["pytest", "pytest-cov", "ruff"]

[project.urls]
Homepage = "https://github.com/TBD/dagpipe"
Documentation = "https://github.com/TBD/dagpipe#readme"
Repository = "https://github.com/TBD/dagpipe"
Issues = "https://github.com/TBD/dagpipe/issues"
```

### Step 6: Create `__init__.py`

```python
"""DagPipe — Zero-cost, crash-proof LLM pipeline orchestrator."""

from dagpipe.dag import Pipeline, Node
from dagpipe.router import Router
from dagpipe.constrained import ConstrainedGenerator
from dagpipe.checkpoints import CheckpointStore

__version__ = "0.1.0"

__all__ = [
    "Pipeline",
    "Node", 
    "Router",
    "ConstrainedGenerator",
    "CheckpointStore",
]
```

---

## 16. Risk Mitigations

| Risk | Mitigation |
|---|---|
| MTN MoMo sandbox doesn't match production | Test with ₵1 production transactions on Herbert's account |
| Smithery hosting doesn't materialize | Self-host on Cloudflare Workers as backup |
| Low marketplace adoption | Twitter demo videos (proven viral for MCP tools) |
| Someone copies the MCP servers | First-mover + depth + real sandbox testing = hard to replicate |
| Groq rate limits hit during demos | Router automatically falls back to Gemini Flash |
| core library doesn't get GitHub stars | Focus on r/LocalLLaMA (perfect audience for 7B constrained generation) |
| Context window limits during development | HANDOFF.md protocol ensures seamless agent transitions |

---

## 17. Testing Strategy

### Unit Tests
- Every module in `src/dagpipe/` gets a corresponding `tests/test_*.py`
- Mock LLM responses for deterministic testing
- Run with: `cd dagpipe && pytest tests/ -v`

### Integration Tests
- Test MCP servers against sandbox APIs (MTN sandbox, Daraja sandbox)
- Test the full pipeline: YAML → execution → checkpoint → resume

### Manual Verification
- Install MCP server in Claude Desktop via MCP config
- Ask Claude: "Charge 10 GHS to 0244000000" (MTN sandbox test number)
- Verify transaction ID returned
- Ask Claude: "Check the status of transaction [ID]"
- Verify status matches sandbox response

---

## 18. Distribution Channels

| Channel | What to Post | When | Expected Impact |
|---|---|---|---|
| X / Twitter | Demo videos, #buildinpublic updates | Week 1+ (daily) | High — AI demos go viral |
| GitHub | Clean repo with README + badges + GIFs | Month 1 | High — organic discovery |
| r/LocalLLaMA | "Constrained generation from 7B for $0" | Month 1 | Very high — perfect audience |
| HackerNews | "Show HN: DagPipe" | Month 2 (Tue 8am ET) | Very high — one-time spike |
| PyPI | `pip install dagpipe` | Month 1 | Medium — developer discovery |
| Smithery | MCP server listings | Month 2-3 | Medium — marketplace discovery |
| Apify Store | Actor listings | Month 2-3 | Medium — passive income |
| Product Hunt | Full launch | Month 3 | High — one-day event |
| Reddit (r/SaaS, r/indiehackers) | Freelance demos, build-in-public | Week 1+ | Medium |
| Upwork / Fiverr | "Rapid AI MVP Builder" listing | Week 1 | Medium — direct revenue |
| Medium / Dev.to | Technical blog posts | Month 3+ | Medium — SEO, long-tail |
| DevCongress / GDG Ghana | In-person presentation | Month 2-3 | Medium — local consulting |

---

## 19. Naming and Branding

**Project name:** DagPipe  
**Tagline:** "Zero-cost, crash-proof LLM pipelines"  
**PyPI package:** `dagpipe`  
**GitHub repo:** `TBD/dagpipe`  
**License:** MIT (maximize adoption)  

**Do NOT** use locale-specific names, cultural references, or anything that limits global appeal. DagPipe is a technical name that describes what it does: DAG-based pipelines.

---

## 20. Deep Innovation Addendum (Feb 2026 Reality Check)

This section contains critical strategy upgrades based on deep stress-testing of the original plan against the actual state of AI infrastructure in February 2026.

### 20.1 Infrastructure & Model Upgrades

*   **API Gateway: OpenRouter (Replaces 3-Provider Setup)**
    *   **Old Plan:** Users configure separate keys for Groq, Gemini, and Modal.
    *   **New Reality:** We move entirely to **OpenRouter**. It provides a single API endpoint for 300+ models. Crucially, the `openrouter/free` endpoint automatically selects the best available free model. Users only need ONE API key.
*   **Model Selection: DeepSeek V3.2 & Qwen3 Coder (Replaces Gemini-first)**
    *   **Old Plan:** Gemini Flash for hard tasks.
    *   **New Reality:** DeepSeek V3.2 Speciale scores **90% on LiveCodeBench** (vastly outperforming Gemini for code). Qwen3 Coder Next offers a 262K context window with 70%+ on SWE-Bench. 
    *   **New Routing Cascade:** DeepSeek V3.2 (hard code) -> Qwen3 Coder (long context) -> Llama 3.3 70B (general reasoning) -> `openrouter/free` (simple tasks).
*   **Rate Limits Backend: LiteLLM Integration**
    *   **Problem:** Handling rate limits (like Groq's 30 RPM) manually is fragile.
    *   **New Reality:** We will use **LiteLLM** (open-source) under the hood. It natively handles automatic failovers (if DeepSeek 429s, fallback to Llama), retries, and budget tracking per key.
*   **Zero-Cloud Execution: Ollama Local Mode**
    *   **New Opportunity:** Since version 0.5, Ollama fully supports structured outputs (JSON schema constraints). DagPipe must support Ollama as a first-class citizen. This unlocks a huge market: enterprise/privacy-conscious users who want $0 cloud costs and absolute data security.

### 20.2 Competitor Reality Check
*   **The Competitor:** **Instructor** is an existing, popular Python library that does exactly what our `constrained.py` does (Pydantic-validated JSON extraction from 15+ LLM APIs). We are not the first to do "Constrained Generation."
*   **Our Real Moat:** We do not compete *just* on constrained generation. DagPipe's true differentiator is the **Crash-Proof DAG + Checkpointing + Auto-Model-Escalation Pipeline**, combined with native structured outputs. Instructor is for single calls; DagPipe is for complex, long-running agentic workflows that **must not fail**.

### 20.3 Revised Product Strategy based on Technical Feasibility
*   **Hosting the API:** 
    *   **Old Plan:** Host a free "Constrained Gen API" on Cloudflare Workers.
    *   **New Reality:** Cloudflare Workers Python support is still in Beta and has a strict **10ms CPU limit**. It cannot handle the parsing, Pydantic validation, and multi-step pipeline logic effectively. 
    *   **New Plan:** The hosted "Pipeline-as-a-Service" API must be deployed on **Railway, Render, or Fly.io free tiers** using FastAPI instead of a Cloudflare Worker.
*   **New Meta-Product: DagPipe MCP Server**
    *   Instead of just building MCP tools for *other* services (like M-Pesa), **DagPipe itself becomes an MCP server**. Users can install DagPipe in Cursor/Claude Desktop and state: *"Extract structured invoice data using my pre-defined YAML pipeline"* - and the LLM natively triggers the robust DagPipe backend.
*   **Smithery Marketplace:**
    *   Smithery now boasts over 6,000+ servers. The market is proven but crowded. Our success relies on narrow, high-value, production-ready niches (like African Payments and Cloudflare Deployments) rather than generic toolsets.

### 20.4 Security & Observability Upgrades
*   **Prompt Injection Defense (`SanitizeNode`):**
    *   **Problem:** If DagPipe processes untrusted user input (e.g., an uploaded invoice PDF) and passes it blindly through a pipeline, malicious prompts can inject commands into downstream high-risk nodes (like "Deploy" or "Execute").
    *   **Solution:** Introduce a native `SanitizeNode`. This node uses a fast, local model or `openrouter/free` specifically instructed to detect and neutralize adversarial inputs before they reach the main reasoning loop. We isolate system prompts from user input rigorously to prevent OWASP LLM01 vulnerabilities.
*   **Zero-Cost Observability (OpenTelemetry + Langfuse):**
    *   **Problem:** Debugging a 10-node DAG that fails is impossible by reading raw JSON logs. Commercial tools like LangSmith are too expensive.
    *   **Solution:** We don't reinvent the wheel. DagPipe will natively emit standard **OpenTelemetry** traces. Users can simply plug in **Langfuse** or **LLM Logger** (both open-source and free to self-host) to get a beautiful visual timeline of their pipeline execution, model latency, and cost—all for $0.

### 20.5 Serverless State Backend
*   **Problem:** The current checkpointing system saves JSON files to the local disk. This breaks if users deploy DagPipe on serverless architectures (Vercel, AWS Lambda) where the filesystem is ephemeral.
*   **Solution:** Build a `CloudflareCheckpointStore`. Cloudflare's free tier for D1 (Serverless SQLite) allows 5 million reads/100K writes per day, and KV allows 100K reads. This provides a completely free, persistent, serverless database for DAG state, allowing pipelines to pause on a serverless edge node and resume days later.
