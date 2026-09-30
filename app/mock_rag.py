from __future__ import annotations

import time

from .incidents import STATE
from .pii import summarize_text
from .tracing import get_langfuse_client, observe

CORPUS = {
    "refund": ["Refunds are available within 7 days with proof of purchase."],
    "monitoring": ["Metrics detect incidents, logs identify affected requests, traces localize the root cause."],
    "policy": ["Do not expose PII in logs. Use sanitized summaries only."],
}


@observe(name="retrieval", as_type="retriever", capture_input=False, capture_output=False)
def retrieve(message: str) -> list[str]:
    client = get_langfuse_client()
    safe_query = summarize_text(message)
    if hasattr(client, "update_current_span"):
        client.update_current_span(
            input=safe_query,
            metadata={"query_preview": safe_query},
        )
    if STATE["tool_fail"]:
        raise RuntimeError("Vector store timeout")
    if STATE["rag_slow"]:
        time.sleep(2.5)
    lowered = message.lower()
    for key, docs in CORPUS.items():
        if key in lowered:
            if hasattr(client, "update_current_span"):
                client.update_current_span(
                    output=docs,
                    metadata={"query_preview": safe_query, "doc_count": len(docs)},
                )
            return docs
    fallback = ["No domain document matched. Use general fallback answer."]
    if hasattr(client, "update_current_span"):
        client.update_current_span(
            output=fallback,
            metadata={"query_preview": safe_query, "doc_count": len(fallback)},
        )
    return fallback
