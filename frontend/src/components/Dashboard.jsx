import { useState } from 'react'
import DocumentUpload from './DocumentUpload'
import DocumentList from './DocumentList'
import CollectionList from './CollectionList'
import Chat from './Chat'

export default function Dashboard({ user, onLogout }) {
  const [activeTab, setActiveTab] = useState('chat')
  const [refreshDocuments, setRefreshDocuments] = useState(0)
  const [selectedDocument, setSelectedDocument] = useState(null) // { id, title }
  const [selectedCollection, setSelectedCollection] = useState(null) // { id, title }

  const handleDocumentUploaded = () => {
    setRefreshDocuments((prev) => prev + 1)
    setActiveTab('documents')
  }

  const handleDocumentSelect = (doc) => {
    setSelectedDocument(doc)
    setSelectedCollection(null)
    setActiveTab('chat')
  }

  const handleCollectionSelect = (col) => {
    setSelectedCollection(col)
    setSelectedDocument(null)
    setActiveTab('chat')
  }

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">RAG System</h1>
            <p className="text-gray-600 text-sm">
              Logged in as: <span className="font-medium">{user}</span>
              {selectedDocument && (
                <span className="ml-3 text-blue-600">
                  📄 Doc: {selectedDocument.title}
                </span>
              )}
              {selectedCollection && (
                <span className="ml-3 text-purple-600">
                  📁 Collection: {selectedCollection.title}
                </span>
              )}
            </p>
          </div>
          <button
            onClick={onLogout}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition"
          >
            Logout
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Navigation Tabs */}
        <div className="flex gap-4 mb-8">
          <button
            onClick={() => setActiveTab('chat')}
            className={`px-6 py-2 rounded-lg font-medium transition ${
              activeTab === 'chat'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            💬 Chat
          </button>
          <button
            onClick={() => setActiveTab('upload')}
            className={`px-6 py-2 rounded-lg font-medium transition ${
              activeTab === 'upload'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            📤 Upload Document
          </button>
          <button
            onClick={() => setActiveTab('documents')}
            className={`px-6 py-2 rounded-lg font-medium transition ${
              activeTab === 'documents'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            📚 My Documents
          </button>
          <button
            onClick={() => setActiveTab('collections')}
            className={`px-6 py-2 rounded-lg font-medium transition ${
              activeTab === 'collections'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            📁 My Collections
          </button>
        </div>

        {/* Content Area */}
        <div className="bg-white rounded-lg shadow">
          {activeTab === 'chat' && (
            <Chat
              documentId={selectedDocument?.id ?? null}
              documentTitle={selectedDocument?.title ?? null}
              collectionId={selectedCollection?.id ?? null}
              collectionTitle={selectedCollection?.title ?? null}
            />
          )}
          {activeTab === 'upload' && (
            <DocumentUpload onSuccess={handleDocumentUploaded} />
          )}
          {activeTab === 'documents' && (
            <DocumentList
              key={refreshDocuments}
              onSelectDocument={handleDocumentSelect}
            />
          )}
          {activeTab === 'collections' && (
            <CollectionList
              onSelectCollection={handleCollectionSelect}
            />
          )}
        </div>
      </div>
    </div>
  )
}
