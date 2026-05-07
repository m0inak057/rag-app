from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Document, ChatConversation, ChatMessage


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Handles new user registration with password confirmation.
    """
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm']

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
        )
        user.set_password(validated_data['password'])
        user.save()
        return user





class DocumentSerializer(serializers.ModelSerializer):
    """
    Used for document upload and listing.
    """
    class Meta:
        model = Document
        fields = ['id', 'title', 'file', 'uploaded_at', 'status', 'chunks_count']
        read_only_fields = ['uploaded_at', 'status', 'chunks_count']

    def validate_file(self, value):
        if not value.name.endswith('.pdf'):
            raise serializers.ValidationError("Only PDF files are allowed.")
        if value.size > 20 * 1024 * 1024:
            raise serializers.ValidationError("File size must not exceed 20 MB.")
        return value


class ChatQuerySerializer(serializers.Serializer):
    """
    Validates the incoming chat request.
    
    Required: question, document_id
    Optional: conversation_id (if continuing an existing chat)
    """
    question = serializers.CharField(
        max_length=2000,
        help_text="The question to ask about the document"
    )
    document_id = serializers.IntegerField(
        help_text="ID of the document to query against"
    )
    conversation_id = serializers.IntegerField(
        required=False,
        default=None,
        help_text="ID of existing conversation (omit to start a new one)"
    )


class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Serializes individual chat messages (for returning conversation history).
    """
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'created_at']


class ChatConversationSerializer(serializers.ModelSerializer):
    """
    Serializes a conversation with all its messages.
    """
    messages = ChatMessageSerializer(many=True, read_only=True)
    document_title = serializers.CharField(source='document.title', read_only=True)

    class Meta:
        model = ChatConversation
        fields = ['id', 'document_title', 'created_at', 'messages']
