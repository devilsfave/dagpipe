# E-Commerce Price Extractor

**Only pay on successful extraction — $0.05 per verified result, nothing charged on failure or retries.**

Extract structured pricing and product data from any e-commerce page using a Groq-compatible LLM. Works with Groq (free tier — no credit card), OpenAI, Together AI, Fireworks AI, and Ollama. Built on [DagPipe](https://github.com/devilsfave/dagpipe) — the crash-proof, free-tier LLM pipeline library.

```bash
pip install dagpipe-core
```

## AI Agent Compatible

This actor is AEO-native. The `input_schema.json` and `output_schema.json` expose exact field types, defaults, and constraints in machine-readable format. Any AI agent connected to the Apify MCP server — Claude Desktop, Cursor, VS Code — can discover, configure, and execute this actor autonomously without human input. No prompt engineering required.

## What It Does

1. **Scrapes** the page at your URL using a real browser-grade crawler (CheerioCrawler)
2. **Strips** all HTML, navigation, scripts, and boilerplate → clean plain text
3. **Prompts** a Groq-compatible LLM to extract data matching your schema
4. **Validates** the response with AJV (JSON Schema validator)
5. **Retries** up to 3 times if the LLM returns invalid JSON, injecting the error back into the prompt
6. **Returns** validated structured data in the Apify dataset

**Charge:** `$0.05` per successful extraction. Nothing charged on failure.

---

## ⚡ 60-Second Quickstart

1. Get a free Groq API key at [console.groq.com](https://console.groq.com/) — no credit card required.
2. Paste the input below into the actor's **Input** tab on Apify.
3. Click **Start** — price and product data arrives in your dataset in seconds.

```json
{
    "url": "https://example.com/product/widget-pro",
    "groq_api_key": "gsk_YOUR_GROQ_KEY_HERE"
}
```

**Expected output** (uses built-in e-commerce schema — no schema definition needed):
```json
{
    "url": "https://example.com/product/widget-pro",
    "extracted": {
        "product_name": "Widget Pro",
        "price": 29.99,
        "currency": "USD",
        "in_stock": true,
        "description": "The best widget on the market."
    },
    "model": "llama-3.3-70b-versatile",
    "attempts": 1
}
```

No infrastructure. No subscription. **You are only charged ($0.05) if the extraction succeeds.**

---

## Input Schema

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | ✅ | — | Page to scrape |
| `output_schema` | object | ✅ | — | JSON Schema defining the data to extract |
| `groq_api_key` | string | ✅ | — | API key (Groq, OpenAI, Together AI, etc.) |
| `model` | string | ❌ | `llama-3.3-70b-versatile` | Model name |
| `base_url` | string | ❌ | Groq endpoint | For OpenAI-compatible providers |

---

## Usage Examples

### Example 1: Groq (default, free tier)

Get a free API key at [console.groq.com](https://console.groq.com/).

```json
{
    "url": "https://example.com/product/widget-pro",
    "groq_api_key": "gsk_YOUR_GROQ_KEY_HERE",
    "output_schema": {
        "type": "object",
        "required": ["name", "price"],
        "properties": {
            "name":        { "type": "string" },
            "price":       { "type": "number" },
            "description": { "type": "string" },
            "in_stock":    { "type": "boolean" }
        }
    }
}
```

**Output:**
```json
{
    "url": "https://example.com/product/widget-pro",
    "extracted": {
        "name": "Widget Pro",
        "price": 29.99,
        "description": "The best widget on the market.",
        "in_stock": true
    },
    "model": "llama-3.3-70b-versatile",
    "attempts": 1
}
```

---

### Example 2: OpenAI-compatible endpoint (Together AI, Fireworks AI)

Use any OpenAI-compatible provider by setting `base_url`:

```json
{
    "url": "https://jobs.lever.co/anthropic/engineer",
    "groq_api_key": "YOUR_TOGETHER_AI_KEY",
    "base_url": "https://api.together.xyz/v1",
    "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "output_schema": {
        "type": "object",
        "required": ["title", "company", "location", "salary_range"],
        "properties": {
            "title":        { "type": "string" },
            "company":      { "type": "string" },
            "location":     { "type": "string" },
            "salary_range": { "type": "string" },
            "remote":       { "type": "boolean" },
            "requirements": {
                "type": "array",
                "items": { "type": "string" }
            }
        }
    }
}
```

Other compatible endpoints:
- **Fireworks AI:** `https://api.fireworks.ai/inference/v1`
- **OpenAI:** `https://api.openai.com/v1`

---

### Example 3: Ollama (local, completely free)

Run models locally at zero cost with [Ollama](https://ollama.com/):

```bash
# Start Ollama with a model
ollama serve
ollama pull llama3.3
```

```json
{
    "url": "https://news.ycombinator.com/item?id=12345",
    "groq_api_key": "ollama",
    "base_url": "http://localhost:11434/v1",
    "model": "llama3.3",
    "output_schema": {
        "type": "object",
        "required": ["title", "score", "comments_count"],
        "properties": {
            "title":          { "type": "string" },
            "score":          { "type": "integer" },
            "comments_count": { "type": "integer" },
            "author":         { "type": "string" },
            "url":            { "type": "string" }
        }
    }
}
```

> **Note:** When running the Actor on Apify cloud, Ollama requires a remote endpoint. For local testing, use `apify run` with `localhost`.

---

## Common Use Cases

| Use Case | Schema Fields |
|---|---|
| **Product extraction** | name, price, description, in_stock, SKU |
| **Job postings** | title, company, location, salary, requirements |
| **News articles** | headline, author, published_date, summary, tags |
| **Real estate listings** | address, price, bedrooms, bathrooms, sqft |
| **Restaurant menus** | restaurant_name, items (name, price, description) |
| **Resume parsing** | name, email, skills, experience, education |
| **Event listings** | name, date, venue, ticket_price, organizer |

---

## How Retry Logic Works

The actor uses the same retry-with-feedback pattern as [`constrained.py`](https://github.com/devilsfave/dagpipe) from the DagPipe core library:

1. **Attempt 1:** Send text + schema → LLM responds → AJV validates
2. **On failure:** Inject the exact AJV error message into the next prompt → retry
3. **Attempt 2:** LLM receives error and corrects → validate again
4. **After 3 failures:** Throw with a descriptive error message

This approach reliably extracts valid structured data even from smaller/cheaper models.

---

## Pricing

- **`$0.05` per successful extraction** (Pay-Per-Event)
- **Free if extraction fails** — you're never charged for failed attempts
- Groq's free tier provides 30 requests/minute at zero cost to you

## Scheduling

Example: Schedule against 50 competitor product URLs daily. Total cost: $2.50/day. Zero infrastructure. Zero maintenance.

---

## Technical Details

- **Scraper:** CheerioCrawler (zero-JS, fast, reliable)
- **Validation:** AJV v8 + ajv-formats (JSON Schema Draft-07/2019/2020 compatible)
- **LLM client:** OpenAI SDK (works with any OpenAI-compatible endpoint)
- **Retry strategy:** Error-feedback prompting (same pattern as DagPipe constrained.py)
- **Language:** TypeScript, Node.js 20+
- **Tests:** 9 vitest tests (100% passing)

---

## Built With

[DagPipe](https://github.com/devilsfave/dagpipe) — Zero-cost, crash-proof LLM pipeline orchestrator.

```bash
pip install dagpipe-core
```
