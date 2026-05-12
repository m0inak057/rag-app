import { useState, useEffect } from 'react'
import api from '../services/api'

export default function CollectionList({ onSelectCollection }) {
  const [collections, setCollections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  
  const [newCollectionName, setNewCollectionName] = useState('')
  const [newCollectionDesc, setNewCollectionDesc] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    fetchCollections()
  }, [])

  const fetchCollections = async () => {
    try {
      setLoading(true)
      const response = await api.get('/collections/')
      setCollections(response.data.results || response.data)
      setError('')
    } catch (err) {
      setError('Failed to load collections')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!newCollectionName.trim()) return
    
    setCreating(true)
    try {
      await api.post('/collections/', {
        name: newCollectionName,
        description: newCollectionDesc
      })
      setNewCollectionName('')
      setNewCollectionDesc('')
      fetchCollections()
    } catch (err) {
      setError('Failed to create collection')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this collection?')) return
    try {
      await api.delete(`/collections/${id}/`)
      fetchCollections()
    } catch (err) {
      setError('Failed to delete collection')
    }
  }

  if (loading) {
    return <div className="p-8 text-center text-gray-600">Loading collections...</div>
  }

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">My Collections</h2>
        <button
          onClick={fetchCollections}
          className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition"
        >
          🔄 Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg mb-6">
          {error}
        </div>
      )}

      {/* Create new collection form */}
      <form onSubmit={handleCreate} className="bg-gray-50 border border-gray-200 p-4 rounded-lg mb-8 flex gap-4 items-start">
        <div className="flex-1">
          <input 
            type="text" 
            placeholder="New Collection Name" 
            value={newCollectionName}
            onChange={(e) => setNewCollectionName(e.target.value)}
            className="w-full p-2 border border-gray-300 rounded mb-2"
          />
          <input 
            type="text" 
            placeholder="Description (optional)" 
            value={newCollectionDesc}
            onChange={(e) => setNewCollectionDesc(e.target.value)}
            className="w-full p-2 border border-gray-300 rounded"
          />
        </div>
        <button 
          type="submit" 
          disabled={creating || !newCollectionName.trim()}
          className="px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition disabled:bg-gray-400"
        >
          {creating ? 'Creating...' : '+ Create'}
        </button>
      </form>

      {/* Collections List */}
      {collections.length === 0 ? (
        <div className="text-center py-12 text-gray-600">No collections found.</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {collections.map((col) => (
            <div key={col.id} className="bg-white border text-left border-gray-200 rounded-lg shadow-sm p-5 hover:shadow-md transition flex flex-col justify-between">
              <div>
                <h3 className="font-bold text-lg text-gray-900 mb-1">{col.name}</h3>
                <p className="text-gray-600 text-sm mb-4 h-10 overflow-hidden line-clamp-2">{col.description || 'No description'}</p>
                <div className="text-sm bg-blue-50 text-blue-800 px-3 py-1 rounded inline-block mb-4">
                  {col.document_count} Documents
                </div>
              </div>
              
              <div className="flex justify-between items-center pt-4 border-t border-gray-100">
                <button 
                  onClick={() => onSelectCollection?.({ id: col.id, title: col.name })}
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm font-medium"
                >
                  💬 Chat
                </button>
                <button 
                  onClick={() => handleDelete(col.id)}
                  className="text-red-500 hover:text-red-700 text-sm font-medium"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
