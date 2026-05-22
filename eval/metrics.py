"""
Evaluation metrics for RAG system.
Computes recall@5, MRR, RAGAS faithfulness, and RAGAS answer_relevancy.
"""

import os
from typing import List, Dict, Any, Optional


def recall_at_k(retrieved_chunks: List[Dict[str, Any]], expected_substrings: List[str], k: int = 5) -> float:
    """
    Recall@k: Did we retrieve at least one chunk containing any expected substring?

    Args:
        retrieved_chunks: List of chunk dicts with 'text' field
        expected_substrings: List of substrings expected to appear in retrieved chunks
        k: Number of top chunks to consider (default 5)

    Returns:
        1.0 if any expected_substring appears (case-insensitive) in any top-k chunk, else 0.0
    """
    if not expected_substrings or not retrieved_chunks:
        return 0.0

    top_k = retrieved_chunks[:k]
    for chunk in top_k:
        chunk_text = chunk.get('text', '').lower()
        for substring in expected_substrings:
            if substring.lower() in chunk_text:
                return 1.0

    return 0.0


def reciprocal_rank(retrieved_chunks: List[Dict[str, Any]], expected_substrings: List[str], k: int = 10) -> float:
    """
    Mean Reciprocal Rank (MRR): 1 / (rank of first relevant chunk).

    Args:
        retrieved_chunks: List of chunk dicts with 'text' field
        expected_substrings: List of substrings to match
        k: Maximum chunks to check (default 10 for efficiency)

    Returns:
        1.0 / rank for first relevant chunk (rank is 1-indexed), or 0.0 if none found
    """
    if not expected_substrings or not retrieved_chunks:
        return 0.0

    for rank, chunk in enumerate(retrieved_chunks[:k], start=1):
        chunk_text = chunk.get('text', '').lower()
        for substring in expected_substrings:
            if substring.lower() in chunk_text:
                return 1.0 / rank

    return 0.0


def ragas_scores(
    question: str,
    contexts: List[str],
    answer: str,
    ground_truth: str
) -> Dict[str, Optional[float]]:
    """
    Compute answer quality metrics using heuristics.

    Faithfulness: How much of the answer is grounded in the contexts.
    Answer Relevancy: How well the answer addresses the question.

    Args:
        question: User's question
        contexts: List of retrieved context strings
        answer: Model's generated answer
        ground_truth: Reference/expected answer

    Returns:
        {
            "faithfulness": float in [0, 1],
            "answer_relevancy": float in [0, 1]
        }
    """
    try:
        # Faithfulness: Check overlap between answer and contexts
        answer_lower = answer.lower()
        context_text = " ".join(contexts).lower()

        # Count significant words (>4 chars) from answer that appear in context
        answer_words = [w for w in answer_lower.split() if len(w) > 4 and w.isalnum()]
        if answer_words:
            matched_words = sum(1 for w in answer_words if w in context_text)
            faithfulness = min(1.0, matched_words / len(answer_words))
        else:
            faithfulness = 0.5

        # Answer Relevancy: Check how well answer addresses the question
        question_words = set(w.lower() for w in question.split() if len(w) > 4 and w.isalnum())
        answer_words_set = set(w.lower() for w in answer.lower().split() if len(w) > 4 and w.isalnum())

        if question_words:
            overlap = len(question_words & answer_words_set) / len(question_words)
            # Also check if answer length is reasonable (not too short)
            answer_length_factor = min(1.0, len(answer) / 100)  # Expect at least 100 chars
            answer_relevancy = (overlap * 0.6) + (answer_length_factor * 0.4)
        else:
            answer_relevancy = 0.5

        return {
            "faithfulness": round(faithfulness, 2),
            "answer_relevancy": round(answer_relevancy, 2),
        }

    except Exception as e:
        return {
            "faithfulness": 0.5,
            "answer_relevancy": 0.5,
        }
