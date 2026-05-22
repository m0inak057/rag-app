#!/usr/bin/env python
"""
Seed the eval corpus: load PDFs from eval/corpus/ into the database.

Usage:
  python eval/seed_corpus.py

This script:
1. Creates/gets an "eval_user" (or first superuser if it doesn't exist)
2. Creates/gets an "Eval Corpus" collection owned by that user
3. Loads all PDFs from eval/corpus/ into the DB
4. Triggers async processing via Celery
5. Polls until all documents are ready
6. Prints the collection ID for use in run_eval.py
"""

import os
import sys
import time
import django
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from rag.models import Collection, Document
from rag.tasks import process_document_task
from sentence_transformers import SentenceTransformer
from rag.tools import set_embedding_model


def seed_corpus():
    """Main function to seed the eval corpus."""

    print("=" * 70)
    print("EVAL CORPUS SEEDING")
    print("=" * 70)

    # 1. Get or create eval user
    print("\n[1] Initializing eval user...")
    eval_user, created = User.objects.get_or_create(
        username='eval_user',
        defaults={
            'email': 'eval@internal.local',
            'is_staff': False,
        }
    )
    if created:
        print(f"    Created new user: eval_user")
    else:
        print(f"    Using existing user: eval_user")

    # 2. Get or create Eval Corpus collection
    print("\n[2] Initializing collection...")
    collection, created = Collection.objects.get_or_create(
        user=eval_user,
        name='Eval Corpus',
        defaults={'description': 'Collection for evaluation and benchmarking'}
    )
    if created:
        print(f"    Created new collection: Eval Corpus (ID: {collection.id})")
    else:
        print(f"    Using existing collection: Eval Corpus (ID: {collection.id})")

    # 3. Set embedding model
    print("\n[3] Loading embedding model...")
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    set_embedding_model(embedding_model)
    print("    Embedding model loaded (all-MiniLM-L6-v2)")

    # 4. Load PDFs from eval/corpus/
    print("\n[4] Scanning eval/corpus/ for PDFs...")
    corpus_dir = Path(__file__).parent / 'corpus'
    if not corpus_dir.exists():
        print(f"    ERROR: {corpus_dir} does not exist")
        sys.exit(1)

    pdf_files = list(corpus_dir.glob('*.pdf'))
    if not pdf_files:
        print(f"    No PDF files found in {corpus_dir}")
        print(f"    Please add PDFs to {corpus_dir} and try again")
        sys.exit(1)

    print(f"    Found {len(pdf_files)} PDF(s)")

    # 5. Create documents and queue processing
    print("\n[5] Creating documents and queuing processing...")
    created_docs = []

    for pdf_file in pdf_files:
        doc_title = pdf_file.stem  # filename without .pdf

        # Check if document already exists
        existing = Document.objects.filter(
            collection=collection,
            title=doc_title
        ).exists()

        if existing:
            print(f"    [SKIP] {doc_title} (already in collection)")
            continue

        # Create document with file opened
        from django.core.files import File
        with open(pdf_file, 'rb') as f:
            doc = Document.objects.create(
                user=eval_user,
                collection=collection,
                title=doc_title,
                file=File(f, name=pdf_file.name),
                status='processing'
            )
        print(f"    [CREATE] {doc_title} (ID: {doc.id})")

        # Queue processing task
        try:
            task = process_document_task.delay(doc.id)
            print(f"             Task ID: {task.id}")
            created_docs.append((doc, task))
        except Exception as e:
            print(f"             ERROR: Failed to queue task: {str(e)}")
            doc.delete()
            continue

    if not created_docs:
        print("    No new documents were created")
        print(f"\n[OK] Eval corpus ready. Collection ID: {collection.id}")
        return collection.id

    # 6. Poll for processing completion
    print(f"\n[6] Waiting for {len(created_docs)} document(s) to process...")
    max_wait = 600  # 10 minutes
    poll_interval = 5  # 5 seconds
    elapsed = 0

    while elapsed < max_wait:
        # Check status of all documents
        statuses = {}
        for doc, _ in created_docs:
            doc.refresh_from_db()
            statuses[doc.title] = doc.status

        ready_count = sum(1 for s in statuses.values() if s == 'ready')
        total = len(created_docs)

        # Print progress
        print(f"    [{elapsed}s] {ready_count}/{total} ready", end='')

        # Check for failures
        failed = [t for t, s in statuses.items() if s == 'failed']
        if failed:
            print(f" (FAILED: {', '.join(failed)})")
            print("\n[ERROR] Some documents failed to process")
            sys.exit(1)

        if ready_count == total:
            print(" - COMPLETE")
            break

        print()
        time.sleep(poll_interval)
        elapsed += poll_interval

    if elapsed >= max_wait:
        print(f"\n[ERROR] Timeout waiting for documents to process")
        sys.exit(1)

    # 7. Success
    print("\n" + "=" * 70)
    print(f"[SUCCESS] Eval corpus seeded!")
    print(f"Collection ID: {collection.id}")
    print(f"Documents: {len(created_docs)}")
    print("=" * 70)
    print(f"\nNext: Update EVAL_COLLECTION_ID in eval/run_eval.py to {collection.id}")
    print()

    return collection.id


if __name__ == '__main__':
    try:
        seed_corpus()
    except KeyboardInterrupt:
        print("\n[CANCELLED] by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
