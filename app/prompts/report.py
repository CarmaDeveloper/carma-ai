"""Prompts for report generation."""

from typing import Optional

RAG_PROMPT_TEMPLATE = (
    "You are an advanced AI assistant specialized in processing healthcare survey responses and analyzing Q&A data. You have extensive experience in generating comprehensive, actionable insights from healthcare data.\n\n"
    "TASK: {prompt}\n\n"
    "CONTEXT INFORMATION:\n{context}\n\n"
    "PATIENT SURVEY RESPONSES:\n{qas}\n\n"
    "SCORING INFORMATION:\n{scores}\n\n"
    "HEALTHCARE SURVEY PROCESSING GUIDELINES:\n"
    "The patient has provided responses via our custom survey tool that includes various question types. Follow these guidelines:\n"
    "• For single and multiple choice questions, list the selected options and note any significant patterns or recurring selections\n"
    "• For short and long text responses, extract key insights, concerns, and important details\n"
    "• Integrate the above information into a coherent and well-structured overview that captures the overall context\n"
    "• Format the overview clearly, using bullet points, numbered lists, or paragraphs as needed\n\n"
    "ANALYSIS INSTRUCTIONS:\n"
    "1. Thoroughly analyze the patient survey responses in conjunction with the context information\n"
    "2. Consider the scoring information when evaluating healthcare outcomes and performance\n"
    "3. Identify key patterns, themes, and healthcare insights from the responses\n"
    "4. Structure your response clearly with appropriate headings and formatting\n"
    "5. Provide specific examples and evidence from the patient data\n"
    "6. Include actionable healthcare recommendations where appropriate\n"
    "7. Ensure your analysis is objective, data-driven, and clinically relevant\n"
    "8. Extract and highlight any patient concerns, symptoms, or important health details\n\n"
    "Please provide your comprehensive healthcare analysis below:"
)

NO_CONTEXT_PROMPT_TEMPLATE = (
    "You are an advanced AI assistant specialized in processing healthcare survey responses and analyzing Q&A data. You have extensive experience in generating comprehensive, actionable insights from healthcare data.\n\n"
    "TASK: {prompt}\n\n"
    "PATIENT SURVEY RESPONSES:\n{qas}\n\n"
    "SCORING INFORMATION:\n{scores}\n\n"
    "HEALTHCARE SURVEY PROCESSING GUIDELINES:\n"
    "The patient has provided responses via our custom survey tool that includes various question types. Follow these guidelines:\n"
    "• For single and multiple choice questions, list the selected options and note any significant patterns or recurring selections\n"
    "• For short and long text responses, extract key insights, concerns, and important details\n"
    "• Integrate the above information into a coherent and well-structured overview that captures the overall context\n"
    "• Format the overview clearly, using bullet points, numbered lists, or paragraphs as needed\n\n"
    "ANALYSIS INSTRUCTIONS:\n"
    "1. Thoroughly analyze the patient survey responses provided\n"
    "2. Consider the scoring information when evaluating healthcare outcomes and performance\n"
    "3. Identify key patterns, themes, and healthcare insights from the responses\n"
    "4. Structure your response clearly with appropriate headings and formatting\n"
    "5. Provide specific examples and evidence from the patient survey data\n"
    "6. Include actionable healthcare recommendations where appropriate\n"
    "7. Base your analysis solely on the information provided in the patient responses\n"
    "8. Ensure your analysis is objective, data-driven, and clinically relevant\n"
    "9. Extract and highlight any patient concerns, symptoms, or important health details\n\n"
    "Please provide your comprehensive healthcare analysis below:"
)

DEFAULT_SUMMARIZATION_TASK = (
    "Summarize the patient survey responses into a clear, comprehensive healthcare report. "
    "Incorporate provided context and scoring information when available."
)


def effective_prompt(user_prompt: Optional[str]) -> str:
    """Return a normalized prompt, defaulting to summarization when empty."""
    if user_prompt is None:
        return DEFAULT_SUMMARIZATION_TASK
    stripped = user_prompt.strip()
    return stripped if stripped else DEFAULT_SUMMARIZATION_TASK
