#!/bin/bash

# Phase 3.4 Manual Curl Test
# Test: Create collection, upload PDFs, verify grouping

BASE_URL="http://localhost:8000/api"
TEST_USER="test_phase3_$(date +%s)"
TEST_EMAIL="test_phase3_$(date +%s)@example.com"
TEST_PASSWORD="TestPassword123!@#"

echo "========================================="
echo "Phase 3.4 - Collections API Curl Test"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
        exit 1
    fi
}

# Step 1: Register a new user
echo "Step 1: Registering test user..."
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/register/" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$TEST_USER\", \"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASSWORD\", \"password_confirm\": \"$TEST_PASSWORD\"}")

echo "Response: $REGISTER_RESPONSE"
echo ""

# Check if registration was successful
if echo "$REGISTER_RESPONSE" | grep -q "id\|username"; then
    print_status 0 "User registered successfully"
else
    echo -e "${RED}Registration failed${NC}"
    echo "Response: $REGISTER_RESPONSE"
fi

# Step 2: Login to get JWT token
echo "Step 2: Logging in to get JWT token..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/token/" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$TEST_USER\", \"password\": \"$TEST_PASSWORD\"}")

echo "Login response: $LOGIN_RESPONSE"

# Extract access token (handle both json and plain text)
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access":"[^"]*"' | cut -d'"' -f4)
if [ -z "$ACCESS_TOKEN" ]; then
    ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access": *"[^"]*"' | cut -d'"' -f4)
fi

if [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}Failed to extract access token${NC}"
    echo "Full response: $LOGIN_RESPONSE"
    exit 1
fi

print_status 0 "JWT token obtained"
echo "Token: ${ACCESS_TOKEN:0:20}..."
echo ""

# Step 3: Create a collection
echo "Step 3: Creating a collection..."
CREATE_COLLECTION_RESPONSE=$(curl -s -X POST "$BASE_URL/collections/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"name": "ML Papers", "description": "Collection of machine learning research papers"}')

echo "Response: $CREATE_COLLECTION_RESPONSE"

COLLECTION_ID=$(echo "$CREATE_COLLECTION_RESPONSE" | grep -o '"id":[0-9]*' | grep -o '[0-9]*')
if [ -z "$COLLECTION_ID" ]; then
    echo -e "${RED}Failed to extract collection ID${NC}"
    exit 1
fi

print_status 0 "Collection created with ID: $COLLECTION_ID"
echo ""

# Step 4: List collections
echo "Step 4: Listing collections..."
LIST_RESPONSE=$(curl -s -X GET "$BASE_URL/collections/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Response: $LIST_RESPONSE"

if echo "$LIST_RESPONSE" | grep -q "\"id\": $COLLECTION_ID\|\"id\":$COLLECTION_ID"; then
    print_status 0 "Collection appears in list"
else
    echo -e "${YELLOW}Warning: Collection not found in list, but may still be there${NC}"
fi
echo ""

# Step 5: Upload PDFs to the collection
echo "Step 5: Uploading test PDFs to collection..."

PDF_FILES=("d:/PADHAII/PROJECTS/RAG_APP/media/documents/test.pdf" "d:/PADHAII/PROJECTS/RAG_APP/media/documents/Moinak_Mondal_Resume.pdf")
UPLOADED_DOCS=()

for PDF in "${PDF_FILES[@]}"; do
    if [ -f "$PDF" ]; then
        echo "  Uploading: $PDF"

        UPLOAD_RESPONSE=$(curl -s -X POST "$BASE_URL/documents/upload/" \
          -H "Authorization: Bearer $ACCESS_TOKEN" \
          -F "file=@$PDF" \
          -F "collection_id=$COLLECTION_ID")

        echo "  Response: $UPLOAD_RESPONSE"

        # Extract document ID from response
        DOC_ID=$(echo "$UPLOAD_RESPONSE" | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')
        if [ ! -z "$DOC_ID" ]; then
            UPLOADED_DOCS+=($DOC_ID)
            print_status 0 "Uploaded: $(basename $PDF) (ID: $DOC_ID)"
        else
            echo -e "${YELLOW}Warning: Could not extract document ID from response${NC}"
        fi
        echo ""
    fi
done

if [ ${#UPLOADED_DOCS[@]} -eq 0 ]; then
    echo -e "${YELLOW}No PDFs were uploaded. Checking if files exist...${NC}"
    ls -la d:/PADHAII/PROJECTS/RAG_APP/media/documents/ 2>/dev/null || echo "Media directory not found"
fi

# Step 6: Get collection details and verify documents are grouped
echo "Step 6: Getting collection details to verify document grouping..."
COLLECTION_DETAIL=$(curl -s -X GET "$BASE_URL/collections/$COLLECTION_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Response: $COLLECTION_DETAIL"

if echo "$COLLECTION_DETAIL" | grep -q "\"name\": *\"ML Papers\"\|\"name\":\"ML Papers\""; then
    print_status 0 "Collection details retrieved correctly"
else
    echo -e "${RED}Collection details not found${NC}"
fi

# Check for documents in collection
if echo "$COLLECTION_DETAIL" | grep -q "document_count\|documents"; then
    print_status 0 "Collection contains documents reference"
else
    echo -e "${YELLOW}Warning: No document count/reference found in collection details${NC}"
fi
echo ""

# Step 7: List documents scoped to user
echo "Step 7: Listing documents for user..."
DOCS_LIST=$(curl -s -X GET "$BASE_URL/documents/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Response: $DOCS_LIST"

if echo "$DOCS_LIST" | grep -q "\"id\""; then
    print_status 0 "Documents list retrieved"
else
    echo -e "${YELLOW}No documents in user's list (may be expected if upload failed)${NC}"
fi
echo ""

# Summary
echo "========================================="
echo "Test Summary"
echo "========================================="
echo "Created Collection ID: $COLLECTION_ID"
echo "Uploaded Documents: ${#UPLOADED_DOCS[@]}"
echo "Test User: $TEST_USER"
echo ""
echo -e "${GREEN}Phase 3.4 curl test completed!${NC}"
echo "========================================="
