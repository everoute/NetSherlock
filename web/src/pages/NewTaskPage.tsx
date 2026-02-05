import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { ArrowLeft, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '@/lib/api'
import type { DiagnosticRequest } from '@/types'

export function NewTaskPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [formData, setFormData] = useState<DiagnosticRequest>({
    network_type: 'vm',
    diagnosis_type: 'latency',
    mode: 'autonomous',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const response = await api.createDiagnosis(formData)
      navigate(`/tasks/${response.diagnosis_id}`)
    } catch (err: any) {
      setError(err.message || 'Failed to create diagnosis task')
    } finally {
      setLoading(false)
    }
  }

  const updateField = <K extends keyof DiagnosticRequest>(
    field: K,
    value: DiagnosticRequest[K],
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <Link
        to="/tasks"
        className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 mb-4"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Tasks
      </Link>

      <h1 className="text-2xl font-bold text-gray-900 mb-2">
        Create New Diagnosis Task
      </h1>
      <div className="h-px bg-gray-200 mb-6" />

      <form onSubmit={handleSubmit} className="space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-700 text-sm">{error}</p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Network Type <span className="text-red-500">*</span>
          </label>
          <div className="flex gap-3">
            {(['vm', 'system'] as const).map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => updateField('network_type', type)}
                className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                  formData.network_type === type
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {type === 'vm' ? 'VM' : 'System'}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Diagnosis Type <span className="text-red-500">*</span>
          </label>
          <select
            value={formData.diagnosis_type}
            onChange={(e) =>
              updateField('diagnosis_type', e.target.value as any)
            }
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="latency">Latency</option>
            <option value="packet_drop">Packet Drop</option>
            <option value="connectivity">Connectivity</option>
          </select>
        </div>

        <div className="border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Source</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Host IP {formData.network_type === 'vm' && <span className="text-red-500">*</span>}
              </label>
              <input
                type="text"
                value={formData.src_host || ''}
                onChange={(e) => updateField('src_host', e.target.value)}
                placeholder="192.168.1.100"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {formData.network_type === 'vm' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  VM UUID
                </label>
                <input
                  type="text"
                  value={formData.src_vm || ''}
                  onChange={(e) => updateField('src_vm', e.target.value)}
                  placeholder="a1b2c3d4-e5f6-g7h8-i9j0-k1l2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
          </div>
          {formData.network_type === 'vm' && (
            <div className="mt-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                OR VM Name (alternative)
              </label>
              <input
                type="text"
                value={formData.src_vm_name || ''}
                onChange={(e) => updateField('src_vm_name', e.target.value)}
                placeholder="production-web-01"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}
        </div>

        <div className="border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">
            Destination (optional)
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Host IP
              </label>
              <input
                type="text"
                value={formData.dst_host || ''}
                onChange={(e) => updateField('dst_host', e.target.value)}
                placeholder="192.168.1.200"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {formData.network_type === 'vm' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  VM UUID
                </label>
                <input
                  type="text"
                  value={formData.dst_vm || ''}
                  onChange={(e) => updateField('dst_vm', e.target.value)}
                  placeholder="a1b2c3d4-e5f6-g7h8-i9j0-k1l2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
          </div>
          {formData.network_type === 'vm' && (
            <div className="mt-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                OR VM Name (alternative)
              </label>
              <input
                type="text"
                value={formData.dst_vm_name || ''}
                onChange={(e) => updateField('dst_vm_name', e.target.value)}
                placeholder="production-db-01"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Execution Mode
          </label>
          <div className="flex gap-3">
            {(['autonomous', 'interactive'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => updateField('mode', mode)}
                className={`px-6 py-2 rounded-lg font-medium capitalize transition-colors ${
                  formData.mode === mode
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        <div className="border border-gray-200 rounded-lg">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full px-4 py-3 flex items-center justify-between text-sm font-semibold text-gray-900 hover:bg-gray-50"
          >
            <span>Advanced Options</span>
            {showAdvanced ? (
              <ChevronUp className="h-5 w-5" />
            ) : (
              <ChevronDown className="h-5 w-5" />
            )}
          </button>
          {showAdvanced && (
            <div className="p-4 border-t border-gray-200">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Description
                </label>
                <textarea
                  value={formData.description || ''}
                  onChange={(e) => updateField('description', e.target.value)}
                  rows={3}
                  placeholder="VM-to-VM latency issue reported by monitoring"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-3 justify-end">
          <Link
            to="/tasks"
            className="px-6 py-2 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50"
          >
            Cancel
          </Link>
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Creating...' : 'Create Task'}
          </button>
        </div>
      </form>
    </div>
  )
}
