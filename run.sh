#!/bin/bash

# RAG Project - Run All Services with Single Command
# Usage: bash run.sh

echo "========================================="
echo "Starting RAG Project (All Services)"
echo "========================================="
echo ""

# Start Docker Compose in background
echo "[1/3] Starting Docker Compose (PostgreSQL + Redis)..."
docker-compose up -d

# Wait for services to be ready
echo "[*] Waiting for services to be ready..."
sleep 5

# Activate virtual environment and start Celery Worker
echo "[2/3] Starting Celery Worker..."
source venv/Scripts/activate 2>/dev/null || . venv/Scripts/activate
celery -A config worker -l info &
CELERY_PID=$!

# Start Django development server
echo "[3/3] Starting Django Server..."
python manage.py runserver &
DJANGO_PID=$!

echo ""
echo "========================================="
echo "✅ All services started!"
echo "========================================="
echo ""
echo "📍 Services running:"
echo "   • PostgreSQL: localhost:5432"
echo "   • Redis: localhost:6379"
echo "   • Django App: http://localhost:8000"
echo "   • Admin Panel: http://localhost:8000/admin"
echo ""
echo "🛑 To stop all services, press Ctrl+C"
echo ""

# Trap Ctrl+C to stop all background processes
trap "echo 'Shutting down...'; kill $CELERY_PID $DJANGO_PID; docker-compose down; exit" SIGINT

# Wait for background processes
wait
