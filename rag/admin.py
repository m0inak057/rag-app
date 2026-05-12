from django.contrib import admin
from .models import Document, DocumentChunk, ChatConversation, ChatMessage, Collection

admin.site.register(Collection)
admin.site.register(Document)
admin.site.register(DocumentChunk)
admin.site.register(ChatConversation)
admin.site.register(ChatMessage)
