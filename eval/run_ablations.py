#!/usr/bin/env python
"""
Ablation Study Runner - Test different RAG configurations.

Evaluates 4 configurations to understand which components contribute to performance:
- Config A: Full (hybrid search + grading + rewriting) — BASELINE
- Config B: No rewriting (hybrid search + grading)
- Config C: Hybrid only (hybrid search only, no grading or rewriting)
- Config D: Vector-only (no hybrid, no grading, no rewriting)

Usage:
  python eval/run_ablations.py
"""

import os
import sys
import json
import django
from pathlib import Path
from datetime import datetime

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rag.models import Collection
from rag.graph import create_rag_graph, AgentState
from rag.tools import set_embedding_model
from sentence_transformers import SentenceTransformer
from eval.metrics import recall_at_k, reciprocal_rank, ragas_scores


# Configuration
EVAL_COLLECTION_ID = 7
TEST_SET_PATH = 'eval/test_set.json'
RESULTS_DIR = 'eval/results/'
TOP_K = 10

# Ablation configurations to test
CONFIGS = {
    'A_Full': {
        'use_hybrid_search': True,
        'use_grading': True,
        'use_rewriting': True,
        'description': 'Hybrid search + grading + query rewriting'
    },
    'B_NoRewrite': {
        'use_hybrid_search': True,
        'use_grading': True,
        'use_rewriting': False,
        'description': 'Hybrid search + grading (no rewriting)'
    },
    'C_HybridOnly': {
        'use_hybrid_search': True,
        'use_grading': False,
        'use_rewriting': False,
        'description': 'Hybrid search only (no grading or rewriting)'
    },
    'D_VectorOnly': {
        'use_hybrid_search': False,
        'use_grading': False,
        'use_rewriting': False,
        'description': 'Vector search only (baseline retrieval)'
    }
}


def load_test_set():
    """Load test set from JSON."""
    with open(TEST_SET_PATH, 'r') as f:
        return json.load(f)


def run_ablation_study():
    """Run full ablation study across all configurations."""

    print("=" * 90)
    print("RAG SYSTEM ABLATION STUDY")
    print("=" * 90)

    # Validate config
    print("\n[1] Validating configuration...")
    if EVAL_COLLECTION_ID is None:
        print("[ERROR] EVAL_COLLECTION_ID not set")
        sys.exit(1)

    try:
        collection = Collection.objects.get(id=EVAL_COLLECTION_ID)
        print(f"    Collection: {collection.name} ({collection.documents.count()} docs)")
    except Collection.DoesNotExist:
        print(f"[ERROR] Collection {EVAL_COLLECTION_ID} not found")
        sys.exit(1)

    # Load embedding model
    print("\n[2] Loading embedding model...")
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    set_embedding_model(embedding_model)
    print("    Model loaded")

    # Load test set
    print("\n[3] Loading test set...")
    test_items = load_test_set()
    print(f"    Loaded {len(test_items)} questions")

    # Run each configuration
    ablation_results = {}

    for config_name, config_params in CONFIGS.items():
        print(f"\n{'=' * 90}")
        print(f"[CONFIG] {config_name}: {config_params['description']}")
        print(f"{'=' * 90}\n")

        # Create graph with this configuration
        description = config_params.pop('description')
        rag_graph = create_rag_graph(config=config_params)

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

                results.append({
                    'id': question_id,
                    'recall': recall,
                    'mrr': mrr,
                    'faithfulness': faith,
                    'answer_relevancy': relevancy,
                })

                # Print progress
                faith_str = f"{faith:.2f}" if faith is not None else "N/A"
                rel_str = f"{relevancy:.2f}" if relevancy is not None else "N/A"
                print(f"  Q{idx:2d}/40 recall={recall:.2f} mrr={mrr:.2f} "
                      f"faith={faith_str} rel={rel_str}")

            except Exception as e:
                print(f"  Q{idx:2d}/40 ERROR: {str(e)[:50]}")
                results.append({
                    'id': question_id,
                    'recall': 0,
                    'mrr': 0,
                    'faithfulness': None,
                    'answer_relevancy': None,
                })

        # Compute aggregates
        recalls = [r['recall'] for r in results if r['recall'] is not None]
        mrrs = [r['mrr'] for r in results if r['mrr'] is not None]
        faiths = [r['faithfulness'] for r in results if r.get('faithfulness') is not None]
        rels = [r['answer_relevancy'] for r in results if r.get('answer_relevancy') is not None]

        avg_recall = sum(recalls) / len(recalls) if recalls else 0.0
        avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0.0
        avg_faith = sum(faiths) / len(faiths) if faiths else None
        avg_rel = sum(rels) / len(rels) if rels else None

        ablation_results[config_name] = {
            'description': description,
            'recall': avg_recall,
            'mrr': avg_mrr,
            'faithfulness': avg_faith,
            'answer_relevancy': avg_rel,
            'ragas_failures': ragas_failures,
        }

        print(f"\n[SUMMARY] {config_name}")
        print(f"  Recall@{TOP_K}: {avg_recall:.4f}")
        print(f"  MRR: {avg_mrr:.4f}")
        if avg_faith is not None:
            print(f"  Faithfulness: {avg_faith:.4f}")
        if avg_rel is not None:
            print(f"  Answer Relevancy: {avg_rel:.4f}")

    # Generate comparison table
    print("\n" + "=" * 90)
    print("ABLATION STUDY RESULTS - COMPARISON TABLE")
    print("=" * 90)

    print("\n| Config | Description | Recall@10 | MRR | Faithfulness | Answer Relevancy |")
    print("|--------|-------------|-----------|-----|--------------|------------------|")

    for config_name in CONFIGS.keys():
        r = ablation_results[config_name]
        recall = f"{r['recall']:.4f}"
        mrr = f"{r['mrr']:.4f}"
        faith = f"{r['faithfulness']:.4f}" if r['faithfulness'] is not None else "N/A"
        rel = f"{r['answer_relevancy']:.4f}" if r['answer_relevancy'] is not None else "N/A"
        print(f"| {config_name:6s} | {r['description']:25s} | {recall:9s} | {mrr:5s} | {faith:12s} | {rel:16s} |")

    # Compute deltas from baseline (Config A)
    print("\n" + "=" * 90)
    print("DELTA FROM BASELINE (Config A)")
    print("=" * 90)

    baseline = ablation_results['A_Full']

    print("\n| Config | Recall Δ | MRR Δ | Faithfulness Δ | Relevancy Δ |")
    print("|--------|----------|-------|----------------|-------------|")

    for config_name in ['B_NoRewrite', 'C_HybridOnly', 'D_VectorOnly']:
        r = ablation_results[config_name]

        recall_delta = r['recall'] - baseline['recall']
        mrr_delta = r['mrr'] - baseline['mrr']
        faith_delta = (r['faithfulness'] - baseline['faithfulness']) if (r['faithfulness'] is not None and baseline['faithfulness'] is not None) else None
        rel_delta = (r['answer_relevancy'] - baseline['answer_relevancy']) if (r['answer_relevancy'] is not None and baseline['answer_relevancy'] is not None) else None

        recall_str = f"{recall_delta:+.4f}"
        mrr_str = f"{mrr_delta:+.4f}"
        faith_str = f"{faith_delta:+.4f}" if faith_delta is not None else "N/A"
        rel_str = f"{rel_delta:+.4f}" if rel_delta is not None else "N/A"

        print(f"| {config_name:6s} | {recall_str:8s} | {mrr_str:5s} | {faith_str:14s} | {rel_str:11s} |")

    # Write results to file
    print("\n[WRITING] Results to file...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_path = Path(RESULTS_DIR) / f'{timestamp}_ablation.json'

    with open(results_path, 'w') as f:
        json.dump(ablation_results, f, indent=2)

    print(f"    Saved: {results_path}")
    print("\n" + "=" * 90)
    print("ABLATION STUDY COMPLETE")
    print("=" * 90 + "\n")


if __name__ == '__main__':
    try:
        run_ablation_study()
    except KeyboardInterrupt:
        print("\n[CANCELLED] by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
