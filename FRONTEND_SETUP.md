# RAG Frontend Setup Guide

## Prerequisites
- Node.js 18+ and npm/yarn installed
- Backend running at `http://localhost:8000`
- Django admin user created (or use `admin`/`admin`)

## Quick Start

### 1. Install Dependencies
```bash
cd frontend
npm install
```

### 2. Start Development Server
```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`

### 3. Access the Application
- Open http://localhost:3000 in your browser
- Login with your Django credentials (default: `admin` / `admin`)
- Start uploading documents and chatting!

## Build for Production
```bash
npm run build
```

Output will be in `dist/` directory.

## Project Structure
```
frontend/
├── src/
│   ├── components/
│   │   ├── Login.jsx           # Authentication form
│   │   ├── Dashboard.jsx       # Main app layout with tab navigation
│   │   ├── DocumentUpload.jsx  # PDF upload with drag-and-drop
│   │   ├── DocumentList.jsx    # View uploaded documents
│   │   └── Chat.jsx            # Chat interface with streaming
│   ├── services/
│   │   └── api.js              # Axios instance with auth
│   ├── App.jsx                 # Main app component
│   ├── App.css                 # Global styles
│   ├── main.jsx                # Entry point
│   └── index.css               # Tailwind imports
├── vite.config.js              # Vite configuration with /api proxy
├── tailwind.config.js          # Tailwind theming
├── postcss.config.js           # PostCSS pipeline
└── index.html                  # HTML template
```

## Key Features

### Authentication
- Token-based auth via Django REST Framework
- Credentials stored in localStorage
- Auto-logout on 401 response

### Document Upload
- Drag-and-drop PDF upload
- Progress tracking
- Real-time status updates
- Automatic document list refresh

### Chat Interface
- Streaming responses with SSE (Server-Sent Events)
- Real-time reasoning step visualization
- Source citations from retrieved documents
- Loading indicators and error handling

### API Proxy
- Vite automatically proxies `/api/*` requests to `http://localhost:8000`
- No CORS issues - transparent routing

## Troubleshooting

### Port 3000 Already in Use
```bash
npm run dev -- --port 3001
```

### Backend Not Responding
- Verify Django is running: `python manage.py runserver`
- Check `http://localhost:8000` in browser
- Ensure `CORS_ALLOWED_ORIGINS` includes `http://localhost:3000` in Django settings

### Login Fails
- Verify user exists in Django admin: `http://localhost:8000/admin`
- Check browser console for API error details
- Ensure token endpoint is accessible: `http://localhost:8000/api/api-token-auth/`

### Chat Not Working
- Start Celery worker: `celery -A config worker -l info` (from backend)
- Check Redis is running: port 6379
- Verify documents are uploaded: check `/api/documents/` endpoint

## Development Tips

### Hot Module Replacement
Changes to components auto-refresh in browser - no manual reload needed

### CSS Changes
Tailwind CSS generates styles on-demand. Classes auto-complete in most editors.

### API Debugging
Open browser DevTools → Network tab → See all API calls to backend
