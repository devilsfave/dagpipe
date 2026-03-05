/**
 * DagPipe — Structured Data Extractor Actor
 *
 * Scrapes one or more URLs with CheerioCrawler, sends plain text + a JSON Schema
 * to a Groq-compatible LLM, validates the response with AJV, retries
 * up to 3 times on failure, and charges $0.05 per successful extraction.
 *
 * Compatible with: Groq, OpenAI, Together AI, Fireworks, Ollama.
 */

import { Actor, log } from 'apify';
import { CheerioCrawler } from 'crawlee';
import OpenAI from 'openai';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

/** Input schema validated at runtime via AJV against .actor/input_schema.json */
interface ActorInput {
    start_urls: Array<{ url: string }> | string[];
    output_schema: Record<string, unknown>;
    groq_api_key: string;
    model?: string;
    base_url?: string;
}

/** Result pushed to Apify dataset on success */
interface ExtractionResult {
    url: string;
    extracted: Record<string, unknown>;
    model: string;
    attempts: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_MODEL = 'llama-3.3-70b-versatile';
const DEFAULT_BASE_URL = 'https://api.groq.com/openai/v1';
const MAX_RETRIES = 3;
const MAX_TEXT_CHARS = 12_000; // Truncate scraped text to avoid token overflow

// ─────────────────────────────────────────────────────────────────────────────
// SCRAPER
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetches a URL using CheerioCrawler and returns plain text content.
 * Strips all HTML tags, collapses whitespace, and truncates to MAX_TEXT_CHARS.
 *
 * @param url - The page URL to scrape.
 * @returns Clean plain text extracted from the page.
 */
async function scrapeUrl(url: string): Promise<string> {
    let pageText = '';

    const crawler = new CheerioCrawler({
        maxRequestsPerCrawl: 1,
        requestHandlerTimeoutSecs: 30,
        async requestHandler({ $ }) {
            // Remove script and style elements
            $('script, style, nav, footer, iframe, noscript').remove();

            // Extract text from body
            const raw = $('body').text();

            // Collapse whitespace
            pageText = raw.replace(/\s+/g, ' ').trim().slice(0, MAX_TEXT_CHARS);
        },
    });

    await crawler.run([url]);

    if (!pageText) {
        throw new Error(`Failed to extract text from URL: ${url}`);
    }

    return pageText;
}

// ─────────────────────────────────────────────────────────────────────────────
// LLM EXTRACTION WITH RETRY
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Calls a Groq-compatible LLM with the scraped text + JSON Schema instruction.
 * Validates the response with AJV. Retries up to MAX_RETRIES times,
 * injecting the validation error into the prompt on each retry.
 *
 * @param pageText - Plain text content scraped from the URL.
 * @param outputSchema - JSON Schema object to extract against.
 * @param client - Configured OpenAI-compatible client.
 * @param model - Model name to use.
 * @returns Validated extracted data and number of attempts used.
 */
async function extractWithRetry(
    pageText: string,
    outputSchema: Record<string, unknown>,
    client: OpenAI,
    model: string,
): Promise<{ extracted: Record<string, unknown>; attempts: number }> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ajv = new (Ajv as any)({ strict: false }) as { compile: (s: unknown) => any; errorsText: (e: unknown) => string; };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (addFormats as any)(ajv);
    const validate = ajv.compile(outputSchema);

    const schemaStr = JSON.stringify(outputSchema, null, 2);

    const baseInstruction = `You are a structured data extractor. Extract information from the provided text and return ONLY a valid JSON object matching this schema:

\`\`\`json
${schemaStr}
\`\`\`

Rules:
- Output ONLY the raw JSON object starting with { and ending with }
- Do NOT include markdown code fences, explanation, or any text outside the JSON
- Every required field must be present
- Match the exact data types specified in the schema

Text to extract from:
---
${pageText}
---`;

    let userMessage = baseInstruction;
    let lastError: string | null = null;

    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
        if (lastError && attempt > 1) {
            userMessage = `${baseInstruction}

⚠️ Your previous response was INVALID. AJV validation error:
${lastError}

Fix all errors and return ONLY the corrected JSON object.`;
        }

        log.info(`LLM extraction attempt ${attempt}/${MAX_RETRIES}`, { model });

        const response = await client.chat.completions.create({
            model,
            messages: [{ role: 'user', content: userMessage }],
            temperature: 0,
        });

        const raw = response.choices[0]?.message?.content ?? '';

        // Extract JSON from response (handles markdown-wrapped responses)
        const jsonStr = extractJson(raw);

        let parsed: Record<string, unknown>;
        try {
            parsed = JSON.parse(jsonStr) as Record<string, unknown>;
        } catch (e) {
            lastError = `JSON parse error: ${String(e)}. Raw response: ${raw.slice(0, 200)}`;
            log.warning(`Attempt ${attempt}: JSON parse failed`, { error: lastError });
            continue;
        }

        const valid = validate(parsed);
        if (valid) {
            return { extracted: parsed, attempts: attempt };
        }

        lastError = ajv.errorsText(validate.errors);
        log.warning(`Attempt ${attempt}: AJV validation failed`, { errors: lastError });
    }

    throw new Error(
        `Extraction failed after ${MAX_RETRIES} attempts. Last AJV error: ${lastError}`,
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Extracts a JSON object from an LLM response string.
 * Handles markdown code blocks and extraneous surrounding text.
 *
 * @param raw - Raw LLM response text.
 * @returns The extracted JSON string.
 */
function extractJson(raw: string): string {
    let text = raw.trim();

    // Strip markdown code fences
    if (text.startsWith('```json')) text = text.slice(7);
    else if (text.startsWith('```')) text = text.slice(3);
    if (text.endsWith('```')) text = text.slice(0, -3);
    text = text.trim();

    // Find the outermost JSON object
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start !== -1 && end !== -1 && end > start) {
        return text.slice(start, end + 1);
    }

    return text; // Let JSON.parse report the error
}

/**
 * Normalises a start_urls entry to a plain URL string.
 * Handles both { url: string } object format and raw string format.
 */
function resolveUrl(entry: { url: string } | string): string {
    if (typeof entry === 'string') return entry;
    return entry.url;
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────────────────────

await Actor.init();

const input = (await Actor.getInput<ActorInput>())!;

if (!input?.start_urls || input.start_urls.length === 0) {
    throw new Error('Input field "start_urls" is required and must contain at least one URL.');
}
if (!input?.output_schema) throw new Error('Input field "output_schema" is required.');
if (!input?.groq_api_key) throw new Error('Input field "groq_api_key" is required.');

const model = input.model ?? DEFAULT_MODEL;
const baseURL = input.base_url ?? DEFAULT_BASE_URL;
const outputSchema = input.output_schema;

log.info(`Starting structured extraction for ${input.start_urls.length} URL(s)`, { model });

// Configure OpenAI-compatible client (works with Groq, Together, Fireworks, Ollama)
const client = new OpenAI({
    apiKey: input.groq_api_key,
    baseURL,
});

// Process each URL independently — failures are logged and skipped
for (const entry of input.start_urls) {
    const url = resolveUrl(entry);

    try {
        // Step 1: Scrape the page
        log.info('Scraping URL...', { url });
        const pageText = await scrapeUrl(url);
        log.info(`Scraped ${pageText.length} characters of text`, { url });

        // Step 2: Extract structured data with retry
        const { extracted, attempts } = await extractWithRetry(pageText, outputSchema, client, model);

        // Step 3: Push result to dataset
        const result: ExtractionResult = { url, extracted, model, attempts };
        await Actor.pushData(result);

        // Step 4: Charge $0.05 per successful extraction (PPE)
        await Actor.charge({ eventName: 'extraction' });

        log.info('Extraction complete ✅', { url, attempts });
    } catch (err) {
        log.error(`Failed to process URL — skipping`, { url, error: String(err) });
    }
}

await Actor.exit();
