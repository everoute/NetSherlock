import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, Copy, FileText } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '@/lib/api'
import type { DiagnosisResponse } from '@/types'
import { StatusBadge } from '@/components/StatusBadge'
import { formatRelativeTime, formatDuration, copyToClipboard } from '@/lib/utils'

export function TaskDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [task, setTask] = useState<DiagnosisResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [copySuccess, setCopySuccess] = useState(false)
  const [selectedLogIndex, setSelectedLogIndex] = useState(0)

  useEffect(() => {
    if (!id) return
    loadTask()
    const interval = setInterval(loadTask, 2000) // Poll every 2 seconds
    return () => clearInterval(interval)
  }, [id])

  async function loadTask() {
    if (!id) return
    try {
      const data = await api.getDiagnosis(id)
      setTask(data)
    } catch (error) {
      console.error('Failed to load task:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = async () => {
    if (task?.diagnosis_id) {
      await copyToClipboard(task.diagnosis_id)
      setCopySuccess(true)
      setTimeout(() => setCopySuccess(false), 2000)
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-1/3" />
          <div className="h-32 bg-gray-200 rounded" />
          <div className="h-64 bg-gray-200 rounded" />
        </div>
      </div>
    )
  }

  if (!task) {
    return (
      <div className="p-6">
        <div className="text-center">
          <p className="text-gray-500">Task not found</p>
          <Link to="/tasks" className="text-blue-600 hover:text-blue-700 mt-2 inline-block">
            Back to Tasks
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <Link
        to="/tasks"
        className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 mb-4"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Tasks
      </Link>

      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900">
            Task: {task.diagnosis_id}
          </h1>
          <button
            onClick={handleCopy}
            className="text-gray-400 hover:text-gray-600"
            title="Copy ID"
          >
            <Copy className="h-4 w-4" />
          </button>
          {copySuccess && (
            <span className="text-sm text-green-600">Copied!</span>
          )}
        </div>
        <StatusBadge status={task.status} size="lg" />
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Started:</span>{' '}
            <span className="text-gray-900">
              {task.started_at
                ? new Date(task.started_at).toLocaleString()
                : 'N/A'}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Duration:</span>{' '}
            <span className="text-gray-900">
              {formatDuration(task.started_at, task.completed_at)}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Mode:</span>{' '}
            <span className="text-gray-900 capitalize">{task.mode || 'N/A'}</span>
          </div>
        </div>
      </div>

      {(task.diagnosis_type || task.network_type || task.src_host) && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Request Parameters</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            {task.diagnosis_type && (
              <div>
                <span className="text-gray-500">Diagnosis Type:</span>{' '}
                <span className="text-gray-900">{task.diagnosis_type.replace('_', ' ')}</span>
              </div>
            )}
            {task.network_type && (
              <div>
                <span className="text-gray-500">Network Type:</span>{' '}
                <span className="text-gray-900">{task.network_type === 'vm' ? 'VM Network' : 'System Network'}</span>
              </div>
            )}
            {task.src_host && (
              <div>
                <span className="text-gray-500">Source:</span>{' '}
                <span className="text-gray-900 font-mono">
                  {task.src_host}{task.src_vm ? ` (${task.src_vm})` : ''}
                </span>
              </div>
            )}
            {(task.dst_host || task.dst_vm) && (
              <div>
                <span className="text-gray-500">Destination:</span>{' '}
                <span className="text-gray-900 font-mono">
                  {task.dst_host || ''}{task.dst_vm ? ` (${task.dst_vm})` : ''}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {task.summary && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Summary</h2>
          <p className="text-gray-700">{task.summary}</p>
        </div>
      )}

      {task.error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-red-900 mb-3">Error</h2>
          <p className="text-red-700 font-mono text-sm">{task.error}</p>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Execution Details</h2>
        </div>
        <div className="p-6">
          {/* Timeline Summary */}
          <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm mb-6">
            <div className="space-y-2">
              <div className="text-gray-600">
                [<span className="text-blue-600">{task.timestamp ? formatRelativeTime(task.timestamp) : 'N/A'}</span>]
                Diagnosis task created
              </div>
              <div className="text-gray-600">
                [<span className="text-blue-600">{task.started_at ? formatRelativeTime(task.started_at) : 'N/A'}</span>]
                Status: {task.status}
              </div>
              {task.mode && (
                <div className="text-gray-600">
                  [<span className="text-blue-600">{task.started_at ? formatRelativeTime(task.started_at) : 'N/A'}</span>]
                  Mode: {task.mode}
                </div>
              )}
              {task.completed_at && (
                <div className="text-gray-600">
                  [<span className="text-blue-600">{formatRelativeTime(task.completed_at)}</span>]
                  Task {task.status}
                </div>
              )}
            </div>
          </div>

          {/* Log Files Section */}
          {task.logs && task.logs.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Log Files</h3>

              {/* Log File Tabs */}
              <div className="flex gap-2 mb-4 border-b border-gray-200">
                {task.logs.map((log, index) => (
                  <button
                    key={index}
                    onClick={() => setSelectedLogIndex(index)}
                    className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                      selectedLogIndex === index
                        ? 'border-blue-600 text-blue-600'
                        : 'border-transparent text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    {log.name}
                  </button>
                ))}
              </div>

              {/* Log Content */}
              <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                <pre className="font-mono text-xs text-gray-100 whitespace-pre-wrap break-words">
                  {task.logs[selectedLogIndex]?.content}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>

      {task.markdown_report && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 mt-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Full Report
          </h2>
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {task.markdown_report}
            </ReactMarkdown>
          </div>
        </div>
      )}

      {task.status === 'completed' && (
        <div className="mt-6">
          <Link
            to={`/reports/${task.diagnosis_id}`}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            <FileText className="h-4 w-4" />
            View Report
          </Link>
        </div>
      )}
    </div>
  )
}
