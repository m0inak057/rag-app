import { useState, useEffect } from 'react'
import api from '../services/api'

/**
 * DocumentList component.
 *
 * Props:
 *   onSelectDocument  (fn)  — called with { id, title } when user clicks "Chat"
 */
export default function DocumentList({ onSelectDocument }) {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchDocuments()
  }, [])

  const fetchDocuments = async () => {
    try {
      setLoading(true)
      const response = await api.get('/documents/')
      setDocuments(response.data.results || response.data)
      setError('')
    } catch (err) {
      setError('Failed to load documents')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const getStatusBadge = (doc) => {
    const statusMap = {
      ready:      { label: '✓ Ready',      classes: 'bg-green-100 text-green-800' },
      processing: { label: '⏳ Processing', classes: 'bg-yellow-100 text-yellow-800' },
      pending:    { label: '🕐 Pending',    classes: 'bg-gray-100 text-gray-600' },
      failed:     { label: '✗ Failed',      classes: 'bg-red-100 text-red-800' },
    }
    const s = statusMap[doc.status] || { label: doc.status, classes: 'bg-gray-100 text-gray-600' }
    return (
      <span className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${s.classes}`}>
        {s.label}
      </span>
    )
  }

  if (loading) {
    return (
      <div className="p-8 text-center">
        <p className="text-gray-600">Loading documents...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700">{error}</p>
          <button
            onClick={fetchDocuments}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">My Documents</h2>
        <button
          onClick={fetchDocuments}
          className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition"
        >
          🔄 Refresh
        </button>
      </div>

      {documents.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 text-lg mb-4">No documents uploaded yet</p>
          <p className="text-gray-500">Upload a PDF document to get started</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left px-4 py-3 font-semibold text-gray-900">Title</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-900">Chunks</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-900">Status</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-900">Uploaded</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-900">Action</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-900 font-medium">{doc.title}</td>
                  <td className="px-4 py-3 text-gray-600">{doc.chunks_count ?? 0}</td>
                  <td className="px-4 py-3">{getStatusBadge(doc)}</td>
                  <td className="px-4 py-3 text-gray-600 text-sm">
                    {new Date(doc.uploaded_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    {doc.status === 'ready' ? (
                      <button
                        onClick={() => onSelectDocument?.({ id: doc.id, title: doc.title })}
                        className="px-3 py-1 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition"
                      >
                        💬 Chat
                      </button>
                    ) : (
                      <span className="text-gray-400 text-sm">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
