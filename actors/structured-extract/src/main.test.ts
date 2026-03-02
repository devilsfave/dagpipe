/**
 * Tests for the Structured Data Extractor Actor
 *
 * Uses vitest with mocked Groq calls (no real network requests).
 * Tests: happy path, retry path, full failure, schema mismatch.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ─────────────────────────────────────────────────────────────────────────────
// INLINE HELPERS (same logic as main.ts — extracted for testability)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Extracts a JSON object from an LLM response string.
 * Handles markdown code blocks and surrounding text.
 */
function extractJson(raw: string): string {
    let text = raw.trim();
    if (text.startsWith('```json')) text = text.slice(7);
    else if (text.startsWith('```')) text = text.slice(3);
    if (text.endsWith('```')) text = text.slice(0, -3);
    text = text.trim();
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start !== -1 && end !== -1 && end > start) {
        return text.slice(start, end + 1);
    }
    return text;
}

// ─────────────────────────────────────────────────────────────────────────────
// MOCK LLM CALLER — simulates the Groq API call
// ─────────────────────────────────────────────────────────────────────────────

interface MockCall {
    response: string;
}

/**
 * Simulates extractWithRetry using a sequence of mock LLM responses.
 * Each call to the mock consumes the next item in the responses array.
 * Uses AJV to validate responses, retries up to MAX_RETRIES times.
 */
async function simulateExtraction(
    outputSchema: Record<string, unknown>,
    mockResponses: string[],
    maxRetries = 3,
): Promise<{ extracted: Record<string, unknown>; attempts: number }> {
    // AJV v8 ships CJS-style `export =` types — cast to any to fix NodeNext construct/call signature errors
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const AjvCtor = ((await import('ajv')) as any).default as new (opts?: object) => any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const addFormats = ((await import('ajv-formats')) as any).default as (ajv: any) => void;

    const ajv = new AjvCtor({ strict: false });
    addFormats(ajv);
    const validate = ajv.compile(outputSchema);

    let callIndex = 0;
    let lastError: string | null = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        if (callIndex >= mockResponses.length) {
            throw new Error(`No more mock responses (attempt ${attempt})`);
        }

        const raw = mockResponses[callIndex++];
        const jsonStr = extractJson(raw);

        let parsed: Record<string, unknown>;
        try {
            parsed = JSON.parse(jsonStr) as Record<string, unknown>;
        } catch (e) {
            lastError = `JSON parse error: ${String(e)}`;
            continue;
        }

        const valid = validate(parsed);
        if (valid) {
            return { extracted: parsed, attempts: attempt };
        }

        lastError = ajv.errorsText(validate.errors);
    }

    throw new Error(`Extraction failed after ${maxRetries} attempts. Last error: ${lastError}`);
}

// ─────────────────────────────────────────────────────────────────────────────
// TEST SCHEMA
// ─────────────────────────────────────────────────────────────────────────────

const PRODUCT_SCHEMA: Record<string, unknown> = {
    type: 'object',
    required: ['name', 'price'],
    properties: {
        name: { type: 'string' },
        price: { type: 'number' },
        description: { type: 'string' },
    },
};

// ─────────────────────────────────────────────────────────────────────────────
// TESTS
// ─────────────────────────────────────────────────────────────────────────────

describe('extractJson helper', () => {
    it('handles raw JSON', () => {
        expect(extractJson('{"name":"foo"}')).toBe('{"name":"foo"}');
    });

    it('strips markdown json fence', () => {
        expect(extractJson('```json\n{"name":"foo"}\n```')).toBe('{"name":"foo"}');
    });

    it('strips plain markdown fence', () => {
        expect(extractJson('```\n{"name":"foo"}\n```')).toBe('{"name":"foo"}');
    });

    it('extracts outermost JSON from surrounding text', () => {
        expect(extractJson('Here is the result: {"name":"foo"} Done.')).toBe('{"name":"foo"}');
    });
});

describe('simulateExtraction (mocked Groq)', () => {
    it('happy path: first call returns valid JSON → success in 1 attempt', async () => {
        const responses = ['{"name":"Widget Pro","price":29.99,"description":"Best widget"}'];

        const { extracted, attempts } = await simulateExtraction(PRODUCT_SCHEMA, responses);

        expect(attempts).toBe(1);
        expect(extracted).toEqual({
            name: 'Widget Pro',
            price: 29.99,
            description: 'Best widget',
        });
    });

    it('retry path: first call returns bad JSON, second call succeeds → 2 attempts', async () => {
        const responses = [
            'This is not JSON at all',
            '{"name":"Widget Pro","price":49.0}',
        ];

        const { extracted, attempts } = await simulateExtraction(PRODUCT_SCHEMA, responses);

        expect(attempts).toBe(2);
        expect(extracted.name).toBe('Widget Pro');
        expect(extracted.price).toBe(49.0);
    });

    it('schema mismatch: price is string not number → AJV catches it, retry with corrected JSON', async () => {
        const responses = [
            // price is wrong type (string instead of number)
            '{"name":"Widget","price":"not-a-number"}',
            // correct on second attempt
            '{"name":"Widget","price":9.99}',
        ];

        const { extracted, attempts } = await simulateExtraction(PRODUCT_SCHEMA, responses);

        expect(attempts).toBe(2);
        expect(typeof extracted.price).toBe('number');
        expect(extracted.price).toBe(9.99);
    });

    it('full failure: all 3 retries return invalid JSON → throws error', async () => {
        const responses = [
            'not json',
            'still not json',
            'definitely not json',
        ];

        await expect(simulateExtraction(PRODUCT_SCHEMA, responses, 3)).rejects.toThrow(
            'Extraction failed after 3 attempts',
        );
    });

    it('full failure with invalid schema: missing required field all 3 times → throws', async () => {
        const responses = [
            // missing required "price" field
            '{"name":"Widget"}',
            '{"name":"Widget"}',
            '{"name":"Widget"}',
        ];

        await expect(simulateExtraction(PRODUCT_SCHEMA, responses, 3)).rejects.toThrow(
            'Extraction failed after 3 attempts',
        );
    });
});
