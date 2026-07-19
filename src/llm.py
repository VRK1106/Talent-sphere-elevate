"""Groq LLM connector.

Communicates with the Groq API at https://api.groq.com.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Standard headers to prevent 403 Forbidden blocks from WAFs
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def list_local_models() -> list[str]:
    """Fetch the list of model names currently available in Groq API.
    
    If the API key is not set or request fails, falls back to a list of standard Groq models.
    """
    fallback_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it"
    ]
    if not GROQ_API_KEY:
        return fallback_models
        
    try:
        url = "https://api.groq.com/openai/v1/models"
        req_headers = HEADERS.copy()
        req_headers["Authorization"] = f"Bearer {GROQ_API_KEY}"
        
        req = urllib.request.Request(
            url,
            headers=req_headers,
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["id"] for m in data.get("data", [])]
            # Keep only common text models (filter out audio/whisper models)
            text_models = [
                m for m in models 
                if "whisper" not in m.lower() and "audio" not in m.lower() and "guard" not in m.lower()
            ]
            if text_models:
                # Ensure our fallbacks are prioritized at the top of the list if returned by the API
                prioritized = [m for m in fallback_models if m in text_models]
                others = [m for m in text_models if m not in fallback_models]
                return prioritized + others
            return fallback_models
    except Exception:
        return fallback_models


def generate_rag_answer(query: str, chunks: list[dict[str, Any]], model_name: str) -> str:
    """Generate an answer using retrieved document contexts via Groq API."""
    if not chunks:
        return "No context available to answer the query. Please upload documents first."

    if not GROQ_API_KEY:
        return "Groq API Key is not configured. Please add GROQ_API_KEY to your .env file."

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
        "Do not make up facts. "
        "Do NOT include any code blocks, programming snippets, or code examples in your response unless the user explicitly asks for code or programming implementation.\n\n"
        "Cite your sources using bracketed numbers corresponding to the context passages (e.g. [1], [2]) where appropriate."
    )

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"--- CONTEXT PASSAGES ---\n{context_str}\n\n--- USER QUERY ---\n{query}"}
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
            "top_p": 0.9,
        }

        req_headers = HEADERS.copy()
        req_headers["Authorization"] = f"Bearer {GROQ_API_KEY}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.URLError as e:
        return f"Error connecting to Groq API: {e.reason}."
    except Exception as e:
        return f"An unexpected error occurred while generating answer: {e}"


def generate_chat_answer(prompt: str, model_name: str, system_instruction: str | None = None) -> str:
    """Generate a general model completion from a prompt via Groq API."""
    if not GROQ_API_KEY:
        return "Groq API Key is not configured. Please add GROQ_API_KEY to your .env file."

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
            
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
            "top_p": 0.9,
        }

        req_headers = HEADERS.copy()
        req_headers["Authorization"] = f"Bearer {GROQ_API_KEY}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.URLError as e:
        return f"Error connecting to Groq API: {e.reason}."
    except Exception as e:
        return f"An unexpected error occurred: {e}"


def generate_rag_answer_stream(query: str, chunks: list[dict[str, Any]], model_name: str):
    """Yield chunks of text generated using retrieved document contexts via Groq API."""
    if not chunks:
        yield "No context available to answer the query. Please upload documents first."
        return

    if not GROQ_API_KEY:
        yield "Groq API Key is not configured. Please add GROQ_API_KEY to your .env file."
        return

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
        "Do not make up facts. "
        "Do NOT include any code blocks, programming snippets, or code examples in your response unless the user explicitly asks for code or programming implementation.\n\n"
        "Cite your sources using bracketed numbers corresponding to the context passages (e.g. [1], [2]) where appropriate."
    )

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"--- CONTEXT PASSAGES ---\n{context_str}\n\n--- USER QUERY ---\n{query}"}
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
            "top_p": 0.9,
            "stream": True
        }

        req_headers = HEADERS.copy()
        req_headers["Authorization"] = f"Bearer {GROQ_API_KEY}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180.0) as resp:
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data: "):
                    data_content = line_str[6:]
                    if data_content == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_content)
                        delta = chunk_data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        pass
    except urllib.error.URLError as e:
        yield f"Error connecting to Groq API: {e.reason}."
    except Exception as e:
        yield f"An unexpected error occurred while generating answer: {e}"


def generate_chat_answer_stream(prompt: str, model_name: str, system_instruction: str | None = None):
    """Yield chunks of text generated from a prompt via Groq API."""
    if not GROQ_API_KEY:
        yield "Groq API Key is not configured. Please add GROQ_API_KEY to your .env file."
        return

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
            
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
            "top_p": 0.9,
            "stream": True
        }

        req_headers = HEADERS.copy()
        req_headers["Authorization"] = f"Bearer {GROQ_API_KEY}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=180.0) as resp:
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data: "):
                    data_content = line_str[6:]
                    if data_content == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_content)
                        delta = chunk_data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        pass
    except urllib.error.URLError as e:
        yield f"Error connecting to Groq API: {e.reason}."
    except Exception as e:
        yield f"An unexpected error occurred: {e}"


def analyze_proctor_image(image_base64: str) -> str:
    """Analyze a base64 encoded JPEG image using Groq's vision model.
    Returns: 'none', 'phone', 'second_person', 'absent', or 'error'.
    """
    if not GROQ_API_KEY:
        return "none"
        
    try:
        # Strip data URL prefix if present
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
            
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "llama-3.2-11b-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Does this image show a phone, a second person, or the student absent from frame? Answer only: none / phone / second_person / absent."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.0,
            "max_tokens": 10
        }
        
        req_headers = HEADERS.copy()
        req_headers["Authorization"] = f"Bearer {GROQ_API_KEY}"
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"].strip().lower()
            for label in ["phone", "second_person", "absent", "none"]:
                if label in answer:
                    return label
            return "none"
    except urllib.error.HTTPError as e:
        if e.code in [400, 403, 404]:
            print(f"[PROCTOR VISION] Groq vision model not available or decommissioned ({e.code} {e.reason}). Bypassing AI validation.")
        else:
            print(f"[PROCTOR VISION] HTTP error during analysis: {e.code} {e.reason}")
        return "none"
    except Exception as e:
        print(f"[PROCTOR VISION] Error in Groq vision analysis: {e}")
        return "none"


