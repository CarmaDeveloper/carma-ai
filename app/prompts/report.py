"""Prompts for report generation."""

RAG_PROMPT_TEMPLATE = (
    "Context:\n{context}\n\n"
    "Based on the above context, please analyze the "
    "following Q&A pairs and generate a comprehensive report:\n\n{qas}"
)
