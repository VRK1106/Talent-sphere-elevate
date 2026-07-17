import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set env key if needed
os.environ["SECRET_KEY"] = "test-key"

print("Importing embeddings, vectorstore, llm...")
try:
    from src.embeddings import embed_query
    from src.vectorstore import search
    from src.llm import generate_rag_answer_stream
    print("Imports successful!")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

query = "Heat treatment of steel"
print(f"Embedding query: '{query}'...")
try:
    query_vec = embed_query(query)
    print("Embedding successful!")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Searching vector store...")
try:
    sources = search(query_vec, top_k=4, threshold=0.1)
    print(f"Search successful! Found {len(sources) if sources else 0} sources.")
    if sources:
        for idx, s in enumerate(sources):
            print(f"Source {idx}: {s.get('source')} Page {s.get('page')} Score {s.get('score')}")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Testing generate_rag_answer_stream...")
try:
    model = "meta-llama/llama-4-scout-17b-16e-instruct"
    chunk_stream = generate_rag_answer_stream(query, sources, model)
    print("Stream generated. Reading chunks...")
    for chunk in chunk_stream:
        print(chunk, end="", flush=True)
    print("\nStream reading completed successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
