"""Local Qwen LLM connector via Ollama.

Communicates with the local Ollama instance at http://127.0.0.1:11434.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

OLLAMA_HOST = "http://127.0.0.1:11434"


def list_local_models() -> list[str]:
    """Fetch the list of model names currently available in Ollama."""
    try:
        url = f"{OLLAMA_HOST}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def generate_rag_answer(query: str, chunks: list[dict[str, Any]], model_name: str) -> str:
    """Generate an answer using retrieved document contexts.

    Formats the retrieved chunks into a prompt and calls Ollama.
    """
    if not chunks:
        return "No context available to answer the query. Please upload documents first."

    # Construct context block
    context_parts = []
    for i, chunk in enumerate(chunks, start=1):
        source = chunk.get("source", "Unknown Source")
        page = chunk.get("page", "?")
        text = chunk.get("text", "")
        context_parts.append(f"[{i}] Source: {source} (Page {page})\nContent: {text}")

    context_str = "\n\n".join(context_parts)

    system_instruction = (
        "You are an expert AI assistant for 'Talent Sphere Elevate', a smart document retrieval and QA platform. "
        "Your task is to answer the user's query truthfully using ONLY the provided document context below. "
        "If the answer cannot be found in the context, state that you do not know based on the provided documents. "
        "Do not make up facts.\n\n"
        "Cite your sources using bracketed numbers corresponding to the context passages (e.g. [1], [2]) where appropriate."
    )

    prompt = (
        f"{system_instruction}\n\n"
        f"--- CONTEXT PASSAGES ---\n{context_str}\n\n"
        f"--- USER QUERY ---\n{query}\n\n"
        "--- DETAILED RESPONSE ---"
    )

    try:
        url = f"{OLLAMA_HOST}/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        return f"Error connecting to Ollama: {e.reason}. Please make sure Ollama is running."
    except Exception as e:
        return f"An unexpected error occurred while generating answer: {e}"


def generate_chat_answer(prompt: str, model_name: str, system_instruction: str | None = None) -> str:
    """Generate a general model completion from a prompt (without RAG formatting)."""
    try:
        url = f"{OLLAMA_HOST}/api/generate"
        
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"
            
        payload = {
            "model": model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        return f"Error connecting to Ollama: {e.reason}. Please make sure Ollama is running."
    except Exception as e:
        return f"An unexpected error occurred: {e}"
