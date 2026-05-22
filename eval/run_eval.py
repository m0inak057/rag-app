#!/usr/bin/env python
"""
Evaluation harness: run questions through the RAG system and compute metrics.

Usage:
  python eval/run_eval.py

Before running:
  1. Run eval/seed_corpus.py to load PDFs
  2. Update EVAL_COLLECTION_ID below with the collection ID from step 1
  3. Populate eval/test_set.json with real questions and expected answers
"""

import os
import sys
import json
import time
import django
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from rag.models import Collection
from rag.graph import create_rag_graph, AgentState
from rag.tools import set_embedding_model
from sentence_transformers import SentenceTransformer
from eval.metrics import recall_at_k, reciprocal_rank, ragas_scores


# ============================================================================
# USER CONFIG - EDIT THESE
# ============================================================================

EVAL_COLLECTION_ID = 7  # REQUIRED: Set to collection ID from seed_corpus.py output
TEST_SET_PATH = 'eval/test_set.json'
RESULTS_DIR = 'eval/results/'
TOP_K = 10  # Increased from 5 to give more context for better grading and less hallucination

# ============================================================================


def validate_config():
    """Check that required config is set."""
    if EVAL_COLLECTION_ID is None:
        print("[ERROR] EVAL_COLLECTION_ID not set in run_eval.py")
        print("Please run eval/seed_corpus.py first and update EVAL_COLLECTION_ID")
        sys.exit(1)

    if not Path(TEST_SET_PATH).exists():
        print(f"[ERROR] {TEST_SET_PATH} not found")
        sys.exit(1)

    if not Path(RESULTS_DIR).exists():
        Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)


def load_test_set():
    """Load test set from JSON."""
    with open(TEST_SET_PATH, 'r') as f:
        return json.load(f)


def run_eval():
    """Main evaluation runner."""

    print("=" * 80)
    print("RAG EVALUATION HARNESS")
    print("=" * 80)

    # Validate config
    print("\n[1] Validating configuration...")
    validate_config()
    print(f"    Collection ID: {EVAL_COLLECTION_ID}")
    print(f"    Test set: {TEST_SET_PATH}")
    print(f"    Results dir: {RESULTS_DIR}")

    # Load embedding model
    print("\n[2] Loading embedding model...")
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    set_embedding_model(embedding_model)
    print("    Model loaded: all-MiniLM-L6-v2")

    # Load RAG graph
    print("\n[3] Creating RAG graph...")
    rag_graph = create_rag_graph()
    print("    Graph created")

    # Load test set
    print("\n[4] Loading test set...")
    test_items = load_test_set()
    print(f"    Loaded {len(test_items)} questions")

    # Get collection (for validation)
    try:
        collection = Collection.objects.get(id=EVAL_COLLECTION_ID)
        print(f"    Collection: {collection.name} (user: {collection.user.username})")
    except Collection.DoesNotExist:
        print(f"[ERROR] Collection {EVAL_COLLECTION_ID} not found")
        sys.exit(1)

    # Run evaluation
    print(f"\n[5] Running evaluation ({len(test_items)} questions)...\n")

    results = []
    ragas_failures = 0

    for idx, item in enumerate(test_items, start=1):
        question = item['question']
        expected_chunks = item.get('expected_chunks_contain', [])
        ground_truth = item.get('ground_truth_answer', '')
        question_id = item.get('id', f'q{idx}')

        try:
            # Build agent state
            state: AgentState = {
                "question": question,
                "document_id": None,
                "collection_id": EVAL_COLLECTION_ID,
                "conversation_history": [],
                "retrieved_documents": [],
                "graded_documents": [],
                "generation": "",
                "reasoning_trace": [],
                "current_step": "",
                "loop_count": 0,
                "use_web_search": False,
                "rewrite_count": 0,
                "cited_sources": [],
            }

            # Invoke graph
            result = rag_graph.invoke(state)

            # Extract metrics
            retrieved = result.get('retrieved_documents', [])
            answer = result.get('generation', '')

            recall = recall_at_k(retrieved, expected_chunks, k=TOP_K)
            mrr = reciprocal_rank(retrieved, expected_chunks)

            # Compute RAGAS scores
            contexts = [c.get('text', '') for c in retrieved[:TOP_K]]
            ragas_result = ragas_scores(question, contexts, answer, ground_truth)

            faith = ragas_result.get('faithfulness')
            relevancy = ragas_result.get('answer_relevancy')

            if ragas_result.get('error'):
                ragas_failures += 1

            # Append result
            results.append({
                'id': question_id,
                'question': question,
                'answer': answer,
                'retrieved_count': len(retrieved),
                'recall': recall,
                'mrr': mrr,
                'faithfulness': faith,
                'answer_relevancy': relevancy,
                'ragas_error': ragas_result.get('error'),
            })

            # Print progress
            faith_str = f"{faith:.2f}" if faith is not None else "FAIL"
            rel_str = f"{relevancy:.2f}" if relevancy is not None else "FAIL"
            print(f"  Q{idx}/{len(test_items):2d} recall={recall:.2f} mrr={mrr:.2f} "
                  f"faith={faith_str} rel={rel_str}")

        except Exception as e:
            print(f"  Q{idx}/{len(test_items):2d} ERROR: {str(e)}")
            results.append({
                'id': question_id,
                'question': question,
                'error': str(e),
                'recall': 0,
                'mrr': 0,
                'faithfulness': None,
                'answer_relevancy': None,
            })

    # Compute aggregates
    print("\n[6] Computing aggregates...")

    recalls = [r['recall'] for r in results if 'recall' in r and r['recall'] is not None]
    mrrs = [r['mrr'] for r in results if 'mrr' in r and r['mrr'] is not None]
    faiths = [r['faithfulness'] for r in results if r.get('faithfulness') is not None]
    rels = [r['answer_relevancy'] for r in results if r.get('answer_relevancy') is not None]

    avg_recall = sum(recalls) / len(recalls) if recalls else 0.0
    avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0.0
    avg_faith = sum(faiths) / len(faiths) if faiths else None
    avg_rel = sum(rels) / len(rels) if rels else None

    # Write results
    print("\n[7] Writing results...")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_path = Path(RESULTS_DIR) / f'{timestamp}_full.json'
    md_path = Path(RESULTS_DIR) / f'{timestamp}_full.md'

    # Write JSON
    with open(json_path, 'w') as f:
        json.dump(
            {
                'timestamp': timestamp,
                'collection_id': EVAL_COLLECTION_ID,
                'num_questions': len(test_items),
                'metrics': {
                    'recall': avg_recall,
                    'mrr': avg_mrr,
                    'faithfulness': avg_faith,
                    'answer_relevancy': avg_rel,
                },
                'ragas_failures': ragas_failures,
                'results': results,
            },
            f,
            indent=2
        )
    print(f"    JSON: {json_path}")

    # Write Markdown
    with open(md_path, 'w') as f:
        f.write(f"# Evaluation Results\n\n")
        f.write(f"**Timestamp:** {timestamp}\n")
        f.write(f"**Collection ID:** {EVAL_COLLECTION_ID}\n")
        f.write(f"**Total Questions:** {len(test_items)}\n")
        f.write(f"**RAGAS Failures:** {ragas_failures}\n\n")

        f.write("## Summary Metrics\n\n")
        f.write("| Metric | Score |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Recall@{TOP_K} | {avg_recall:.4f} |\n")
        f.write(f"| MRR | {avg_mrr:.4f} |\n")

        if avg_faith is not None:
            f.write(f"| Faithfulness | {avg_faith:.4f} |\n")
        else:
            f.write(f"| Faithfulness | N/A |\n")

        if avg_rel is not None:
            f.write(f"| Answer Relevancy | {avg_rel:.4f} |\n")
        else:
            f.write(f"| Answer Relevancy | N/A |\n")

        f.write("\n## Per-Question Results\n\n")
        f.write("| ID | Recall | MRR | Faith | Rel | Notes |\n")
        f.write("|----|----|----|----|----|---------|\n")

        for r in results:
            recall = r.get('recall', 0)
            mrr = r.get('mrr', 0)
            faith = f"{r.get('faithfulness', 0):.2f}" if r.get('faithfulness') is not None else 'N/A'
            rel = f"{r.get('answer_relevancy', 0):.2f}" if r.get('answer_relevancy') is not None else 'N/A'
            error_msg = r.get('ragas_error') or r.get('error') or ''
            notes = str(error_msg)[:30] if error_msg else ''
            f.write(f"| {r['id']} | {recall:.2f} | {mrr:.2f} | {faith} | {rel} | {notes} |\n")

    print(f"    Markdown: {md_path}")

    # Print summary
    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)
    print(f"\nRecall@{TOP_K}:       {avg_recall:.4f}")
    print(f"MRR:              {avg_mrr:.4f}")
    if avg_faith is not None:
        print(f"Faithfulness:     {avg_faith:.4f}")
    if avg_rel is not None:
        print(f"Answer Relevancy: {avg_rel:.4f}")
    print(f"\nResults written to: {md_path}")
    print()


if __name__ == '__main__':
    try:
        run_eval()
    except KeyboardInterrupt:
        print("\n[CANCELLED] by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
