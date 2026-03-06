# DagPipe Generator — Crash-Proof LLM Pipelines

Turn plain-English descriptions into robust, crash-proof LLM orchestration pipelines using the open-source [DagPipe](https://github.com/devilsfave/dagpipe) framework.

## 🚀 Overview

Building multi-step LLM workflows that involve crawling, scraping, summarizing, or transforming data is often fragile. A single failure mid-run means starting over and wasting tokens. **DagPipe** solves this by turning workflows into a resilient Directed Acyclic Graph (DAG) with:

1.  **JSON Checkpointing**: Resume exactly from the last successful node if anything fails.
2.  **Cognitive Routing**: Automatically route easy tasks to free/cheap models (like Llama 3 8B) and complex tasks to large models (like Llama 3 70B).
3.  **Schema Enforcement**: Guaranteed structured JSON output with automatic retry loops and error feedback.

This actor takes your plain-English goal and generates a complete, ready-to-run Python script (`runner.py`) using the DagPipe library.

## 💡 How It Works

1.  **Provide a Description**: Tell the actor what you want your pipeline to do. (e.g., *"Read a tech blog post, extract key points into a JSON schema, use an LLM to translate it to Spanish, and then save it to disk."*)
2.  **Add Your Groq API Key**: You need a free Groq API key to power the Llama 3 models that will design your pipeline.
3.  **Download Your Code**: The actor mathematically designs the DAG, structures the nodes, and packages everything into a convenient ZIP archive.

## 📦 What's Included in the Output

The actor outputs the path to a generated `.zip` file stored in Apify's Key-Value store. Inside the zip, you will find:
*   `runner.py`: The executable pipeline script.
*   `pipeline.yaml`: The DAG structure and logic.
*   `requirements.txt`: Python dependencies needed to run it locally.
*   `README.md`: Instructions on how to execute your new pipeline.

## 💸 Pay-Per-Event Pricing

This actor uses a straightforward Pay-Per-Event (PPE) model. It costs exactly **$0.05 per successful run**. You only pay for successful pipeline generations that result in a downloadable zip file.

## 🔧 Input Configuration

| Field | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| `description` | `string` | A plain English explanation of your desired pipeline. | **Yes** |
| `groq_api_key` | `string` | Your Groq API key for powering the pipeline design generation. | **Yes** |

## 🌟 Example Usage

**Input:**
```json
{
  "description": "I need a pipeline that monitors a list of competitor URLs, scrapes the pricing page daily, compares it to my database schema, and emails me an alert if their price drops below my current tier.",
  "groq_api_key": "gsk_your_api_key_here..."
}
```

The resulting zip file will scaffold the entire workflow with error handling and retries built-in!
