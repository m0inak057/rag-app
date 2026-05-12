from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField

class Collection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collections')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.user.username})"

class Document(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    )
    
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='documents')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(null=True, blank=True)
    chunks_count = models.IntegerField(default=0)
    page_count = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.title} ({self.user.username}) - {self.status}"

class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    text = models.TextField()
    # Sentence-transformers 'all-MiniLM-L6-v2' outputs 384-dimensional vectors.
    # OpenAI 'text-embedding-3-small' outputs 1536-dimensional vectors.
    # We will set dimensions to 384 for sentence-transformers as planned.
    embedding = VectorField(dimensions=384) 
    page_number = models.IntegerField(null=True)

    def __str__(self):
        return f"Chunk for {self.document.title} (Page {self.page_number})"

class ChatConversation(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='conversations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='conversations', null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat on {self.document.title} by {self.user.username}"

class ChatMessage(models.Model):
    ROLE_CHOICES = (
        ('user', 'User'),
        ('ai', 'AI Assistant'),
    )
    conversation = models.ForeignKey(ChatConversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    reasoning_trace = models.JSONField(null=True, blank=True)  # Stores the agent's thinking steps
    sources = models.JSONField(null=True, blank=True)  # Stores the chunks used to generate the answer

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role} message in {self.conversation.id}"
