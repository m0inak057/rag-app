"""
Celery tasks for asynchronous document processing.
These tasks run in the background, keeping the API responsive.
"""

from celery import shared_task
from django.core.files.storage import default_storage
import fitz
from sentence_transformers import SentenceTransformer

from .models import Document, DocumentChunk

# Load the embedding model once
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')


@shared_task(bind=True)
def process_document_task(self, document_id: int) -> dict:
    """
    Celery task to process a PDF document asynchronously.
    
    Steps:
    1. Extract text and page numbers from PDF
    2. Generate embeddings for each chunk
    3. Store chunks, page numbers, and embeddings in the database
    4. Update document status and page count
    
    Args:
        document_id: The ID of the Document to process
    
    Returns:
        A dictionary with processing results
    """
    from .services import extract_chunks_with_pages # Moved import here
    from .models import Document, DocumentChunk
    import fitz # Moved import here
    
    try:
        # Get the document
        document = Document.objects.get(id=document_id)
        
        # Update status to "processing"
        document.status = 'processing'
        document.save()
        
        # Update task state
        self.update_state(state='PROCESSING', meta={'current': 'Extracting chunks with page numbers...'})
        
        # Step 1: Extract chunks with page numbers
        file_path = document.file.path
        chunks_with_pages = extract_chunks_with_pages(file_path)
        
        if not chunks_with_pages:
            raise ValueError("No text could be extracted from the PDF. It may be image-based or empty.")
        
        # Separate texts for embedding
        chunks_text = [item['text'] for item in chunks_with_pages]
        
        # Update task state
        self.update_state(state='PROCESSING', meta={'current': f'Generating embeddings for {len(chunks_text)} chunks...'})
        
        # Step 2: Generate embeddings
        embeddings = embedding_model.encode(chunks_text, show_progress_bar=False)
        
        # Step 3: Bulk create DocumentChunk objects
        chunk_objects = [
            DocumentChunk(
                document=document,
                text=item['text'],
                page_number=item['page_number'],
                embedding=embedding.tolist(),
            )
            for item, embedding in zip(chunks_with_pages, embeddings)
        ]
        
        DocumentChunk.objects.bulk_create(chunk_objects, batch_size=100)
        
        # Step 4: Update document status and page count
        document.status = 'ready'
        document.chunks_count = len(chunk_objects)
        
        # Get page count from the PDF
        try:
            with fitz.open(file_path) as doc:
                document.page_count = len(doc)
        except Exception:
            document.page_count = 0 # Or handle as an error
            
        document.error_message = None
        document.save()
        
        return {
            'status': 'success',
            'document_id': document_id,
            'chunks_created': len(chunk_objects),
            'page_count': document.page_count,
        }
    
    except Exception as e:
        # Update document status to failed
        try:
            document = Document.objects.get(id=document_id)
            document.status = 'failed'
            document.error_message = str(e)
            document.save()
        except Document.DoesNotExist:
            pass # Document may not have been saved yet
        
        # Return error info
        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(e),
        }


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file using PyMuPDF (fitz).
    
    Args:
        file_path: Path to the PDF file
    
    Returns:
        Extracted text as a string
    """
    text = ""
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text()
        doc.close()
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    
    return text


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list:
    """
    Split text into overlapping chunks.
    
    Args:
        text: The text to chunk
        chunk_size: Size of each chunk in characters
        overlap: Size of overlap between consecutive chunks
    
    Returns:
        List of text chunks
    """
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # Clean up the chunk
        if chunk.strip():
            chunks.append(chunk.strip())
        
        start += chunk_size - overlap
    
    return chunks


@shared_task(bind=True)
def regenerate_embeddings_task(self, document_id: int) -> dict:
    """
    Regenerate embeddings for all chunks of a document.
    Useful if you want to switch to a different embedding model.
    
    Args:
        document_id: The ID of the Document
    
    Returns:
        A dictionary with results
    """
    try:
        document = Document.objects.get(id=document_id)
        
        # Get all chunks for this document
        chunks = DocumentChunk.objects.filter(document_id=document_id)
        
        if not chunks.exists():
            raise ValueError("No chunks found for this document.")
        
        # Re-embed all chunks
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = embedding_model.encode(chunk_texts, show_progress_bar=False)
        
        # Update embeddings in bulk
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding.tolist()
        
        DocumentChunk.objects.bulk_update(chunks, ['embedding'], batch_size=100)
        
        return {
            'status': 'success',
            'document_id': document_id,
            'chunks_updated': len(embeddings),
        }
    
    except Exception as e:
        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(e),
        }
