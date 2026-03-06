import { Actor, log } from 'apify';
import { spawnSync } from 'child_process';
import { readFileSync, existsSync } from 'fs';
import * as path from 'path';

interface ActorInput {
    description: string;
    groq_api_key: string;
}

await Actor.init();

const input = await Actor.getInput<ActorInput>();
if (!input?.description) throw new Error('Input field "description" is required.');
if (!input?.groq_api_key) throw new Error('Input field "groq_api_key" is required.');

log.info("Starting Premium DagPipe Pipeline Generator...");

// Run python wrapper
const wrapperPath = path.resolve('src/wrapper.py');
if (!existsSync(wrapperPath)) {
    throw new Error(`Python wrapper missing at ${wrapperPath}`);
}

log.info("Executing Python generation engine...");

const isWin = process.platform === "win32";
const pyCommand = isWin ? "python" : "python3";
const pythonRun = spawnSync(pyCommand, [wrapperPath], {
    input: JSON.stringify(input),
    encoding: 'utf-8',
    env: { ...process.env, APIFY_DEV_STORAGE: process.env.APIFY_LOCAL_STORAGE_DIR || '/tmp' }
});

let outputStr = pythonRun.stdout?.trim() || "";
let errorStr = pythonRun.stderr?.trim() || "";

if (errorStr) {
    log.warning("Python Stderr (Non-fatal mostly): " + errorStr);
}

if (pythonRun.status !== 0) {
    throw new Error(`Python script failed with status ${pythonRun.status}: ${errorStr || outputStr}`);
}

let result;
try {
    // python outputs json on the last line or entirely
    result = JSON.parse(outputStr.split('\n').pop() || "{}");
} catch (e) {
    throw new Error(`Failed to parse Python output: ${outputStr}`);
}

if (result.status === 'error') {
    throw new Error(`Generator error: ${result.message}`);
}

log.info(`Pipeline generated successfully! Files included: ${result.files_included.join(', ')}`);

// Push to KeyValueStore for direct download
const zipPath = result.zip_path;
if (existsSync(zipPath)) {
    const zipData = readFileSync(zipPath);
    await Actor.setValue('latest_pipeline.zip', zipData, { contentType: 'application/zip' });

    // Provide a neat final output to the user with a direct download link
    const kvs = await Actor.openKeyValueStore();
    const storeId = kvs.id || (kvs as any).storeId;
    const downloadUrl = `https://api.apify.com/v2/key-value-stores/${storeId}/records/latest_pipeline.zip`;

    await Actor.pushData({
        message: "Pipeline successfully generated!",
        download_url: downloadUrl,
        files: result.files_included
    });

    // Charge BEFORE announcing success
    await Actor.charge({ eventName: 'generator-run', count: 1 });
    log.info("PPE charge fired successfully for event: generator-run");

    log.info(`Download your zip here: ${downloadUrl}`);
} else {
    throw new Error(`Zip file not found at expected path: ${zipPath}`);
}

log.info("Finished execution.");
await Actor.exit();
