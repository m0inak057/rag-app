#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3.4 Manual Test - Collections API
Tests: Create collection, upload PDFs, verify grouping
"""

import requests
import json
import os
import time
import sys
from datetime import datetime

# Fix encoding on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://localhost:8000/api"
TEST_USER = f"test_user_{int(time.time())}"
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "TestPassword123!@#"

# Color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_section(title):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

def print_success(msg):
    print(f"{GREEN}[OK] {msg}{RESET}")

def print_error(msg):
    print(f"{RED}[ERROR] {msg}{RESET}")

def print_warning(msg):
    print(f"{YELLOW}[WARN] {msg}{RESET}")

def print_info(msg):
    print(f"  >> {msg}")

def print_json(data):
    print(json.dumps(data, indent=2))

print_section("Phase 3.4 - Collections API Manual Test")

# ===== STEP 1: Register User =====
print_section("Step 1: Register Test User")

register_data = {
    "username": TEST_USER,
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD,
    "password_confirm": TEST_PASSWORD
}

try:
    response = requests.post(f"{BASE_URL}/auth/register/", json=register_data)
    print_info(f"POST /api/auth/register/")
    print_info(f"Status: {response.status_code}")
    print_json(response.json())

    if response.status_code in [200, 201]:
        user_data = response.json()
        user_id = user_data.get('id') or user_data.get('user', {}).get('id')
        print_success(f"User registered: {TEST_USER} (ID: {user_id})")
    else:
        print_warning("Registration status was not 200/201, proceeding anyway...")
except Exception as e:
    print_error(f"Registration failed: {str(e)}")
    exit(1)

# ===== STEP 2: Login & Get JWT Token =====
print_section("Step 2: Login & Get JWT Token")

login_data = {
    "username": TEST_USER,
    "password": TEST_PASSWORD
}

try:
    response = requests.post(f"{BASE_URL}/auth/token/", json=login_data)
    print_info(f"POST /api/auth/token/")
    print_info(f"Status: {response.status_code}")

    if response.status_code == 200:
        tokens = response.json()
        access_token = tokens.get('access')

        if not access_token:
            print_error("No access token in response")
            print_json(tokens)
            exit(1)

        print_success(f"JWT token obtained: {access_token[:30]}...")
    else:
        print_error(f"Login failed with status {response.status_code}")
        print_json(response.json())
        exit(1)

except Exception as e:
    print_error(f"Login failed: {str(e)}")
    exit(1)

# ===== STEP 3: Create Collection =====
print_section("Step 3: Create Collection")

headers = {"Authorization": f"Bearer {access_token}"}

collection_data = {
    "name": f"ML Papers - {int(time.time())}",
    "description": "Test collection of machine learning research papers"
}

try:
    response = requests.post(f"{BASE_URL}/collections/", json=collection_data, headers=headers)
    print_info(f"POST /api/collections/")
    print_info(f"Status: {response.status_code}")
    print_json(response.json())

    if response.status_code in [200, 201]:
        collection = response.json()
        collection_id = collection.get('id')
        collection_name = collection.get('name')
        print_success(f"Collection created: {collection_name} (ID: {collection_id})")
    else:
        print_error(f"Collection creation failed: {response.status_code}")
        exit(1)

except Exception as e:
    print_error(f"Collection creation failed: {str(e)}")
    exit(1)

# ===== STEP 4: List Collections =====
print_section("Step 4: List Collections")

try:
    response = requests.get(f"{BASE_URL}/collections/", headers=headers)
    print_info(f"GET /api/collections/")
    print_info(f"Status: {response.status_code}")

    if response.status_code == 200:
        collections = response.json()

        # Handle both list and dict responses
        if isinstance(collections, dict):
            results = collections.get('results', [])
        else:
            results = collections

        print_info(f"Found {len(results)} collection(s)")

        # Check if our collection is in the list
        our_collection = None
        for coll in results:
            if coll.get('id') == collection_id:
                our_collection = coll
                break

        if our_collection:
            print_success(f"Our collection found in list")
            print_json(our_collection)
        else:
            print_warning(f"Our collection not found in list")
            print_info("All collections:")
            print_json(results)
    else:
        print_error(f"List collections failed: {response.status_code}")

except Exception as e:
    print_error(f"List collections failed: {str(e)}")

# ===== STEP 5: Upload PDFs =====
print_section("Step 5: Upload PDFs to Collection")

pdf_paths = [
    "d:/PADHAII/PROJECTS/RAG_APP/media/documents/test.pdf",
    "d:/PADHAII/PROJECTS/RAG_APP/media/documents/Moinak_Mondal_Resume.pdf"
]

uploaded_docs = []

for pdf_path in pdf_paths:
    if not os.path.exists(pdf_path):
        print_warning(f"PDF not found: {pdf_path}")
        continue

    try:
        print_info(f"Uploading: {os.path.basename(pdf_path)}")

        with open(pdf_path, 'rb') as f:
            files = {'file': f}
            data = {
                'title': os.path.splitext(os.path.basename(pdf_path))[0],
                'collection': collection_id
            }

            response = requests.post(
                f"{BASE_URL}/documents/upload/",
                files=files,
                data=data,
                headers=headers
            )

        print_info(f"Status: {response.status_code}")
        result = response.json()
        print_json(result)

        if response.status_code in [200, 201, 202]:
            doc_id = result.get('id')
            doc_title = result.get('title', os.path.basename(pdf_path))

            if doc_id:
                uploaded_docs.append(doc_id)
                print_success(f"Uploaded: {doc_title} (ID: {doc_id})")
            else:
                print_warning(f"Upload returned 2xx but no ID in response")
        else:
            print_error(f"Upload failed: {response.status_code}")

    except Exception as e:
        print_error(f"Upload failed: {str(e)}")

print_info(f"Total documents uploaded: {len(uploaded_docs)}")

# ===== STEP 6: Get Collection Details =====
print_section("Step 6: Get Collection Details & Verify Grouping")

try:
    response = requests.get(f"{BASE_URL}/collections/{collection_id}/", headers=headers)
    print_info(f"GET /api/collections/{collection_id}/")
    print_info(f"Status: {response.status_code}")

    if response.status_code == 200:
        collection_detail = response.json()
        print_json(collection_detail)

        # Verify collection details
        name = collection_detail.get('name')
        doc_count = collection_detail.get('document_count', 0)
        documents = collection_detail.get('documents', [])

        print_success(f"Collection: {name}")
        print_success(f"Document count: {doc_count}")

        if documents:
            print_success(f"Documents in collection: {len(documents)}")
            for doc in documents:
                doc_id = doc.get('id')
                doc_title = doc.get('title')
                doc_collection = doc.get('collection')
                print_info(f"  - {doc_title} (ID: {doc_id}, Collection: {doc_collection})")

                # Verify document belongs to collection
                if doc_collection == collection_id:
                    print_success(f"    ✓ Correctly scoped to collection {collection_id}")
                else:
                    print_error(f"    ✗ Document scoped to {doc_collection}, expected {collection_id}")
        else:
            print_warning(f"No documents in collection details (they may still be processing)")

    else:
        print_error(f"Get collection details failed: {response.status_code}")
        print_json(response.json())

except Exception as e:
    print_error(f"Get collection details failed: {str(e)}")

# ===== STEP 7: List Documents =====
print_section("Step 7: List User's Documents")

try:
    response = requests.get(f"{BASE_URL}/documents/", headers=headers)
    print_info(f"GET /api/documents/")
    print_info(f"Status: {response.status_code}")

    if response.status_code == 200:
        docs_data = response.json()

        # Handle both list and dict responses
        if isinstance(docs_data, dict):
            documents = docs_data.get('results', [])
        else:
            documents = docs_data

        print_success(f"Found {len(documents)} document(s)")

        # Filter documents belonging to our collection
        collection_docs = [doc for doc in documents if doc.get('collection') == collection_id]
        print_success(f"Documents in our collection: {len(collection_docs)}")

        for doc in collection_docs:
            print_info(f"  - {doc.get('title')} (ID: {doc.get('id')})")

        print_json(documents)
    else:
        print_error(f"List documents failed: {response.status_code}")

except Exception as e:
    print_error(f"List documents failed: {str(e)}")

# ===== FINAL SUMMARY =====
print_section("Test Summary")

print_success(f"Created collection: {collection_name} (ID: {collection_id})")
print_success(f"Uploaded documents: {len(uploaded_docs)}")
print_success(f"Test user: {TEST_USER}")
print("\nPhase 3.4 curl test completed!\n")
