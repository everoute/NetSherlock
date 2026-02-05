import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Eye, RotateCw, XCircle, FileText, Hand, Webhook, Bell } from 'lucide-react'
import { api } from '@/lib/api'
import type { DiagnosisResponse, DiagnosisStatus } from '@/types'
import { StatusBadge } from '@/components/StatusBadge'
import { formatRelativeTime, formatTaskName } from '@/lib/utils'

export function TasksPage() {
  const [tasks, setTasks] = useState<DiagnosisResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | DiagnosisStatus>('all')

  useEffect(() => {
    loadTasks()
    const interval = setInterval(loadTasks, 5000) // Poll every 5 seconds
    return () => clearInterval(interval)
  }, [])

  async function loadTasks() {
    try {
      const data = await api.listDiagnoses({ limit: 50 })
      setTasks(data)
    } catch (error) {
      console.error('Failed to load tasks:', error)
    } finally {
      setLoading(false)
    }
  }

  const filteredTasks = tasks.filter(
    (task) => filter === 'all' || task.status === filter,
  )

  const getTaskType = (task: DiagnosisResponse) => {
    const typeLabel = task.diagnosis_type
      ? task.diagnosis_type.charAt(0).toUpperCase() +
        task.diagnosis_type.slice(1).replace('_', ' ')
      : 'Unknown'

    const networkLabel = task.network_type
      ? ` (${task.network_type.toUpperCase()})`
      : ''

    return `${typeLabel}${networkLabel}`
  }

  const getTriggerIcon = (source?: string) => {
    switch (source) {
      case 'manual':
        return {
          Icon: Hand,
          color: 'text-blue-600',
          title: 'Manual Trigger',
        }
      case 'webhook':
        return {
          Icon: Webhook,
          color: 'text-green-600',
          title: 'Webhook Trigger',
        }
      case 'alert':
        return {
          Icon: Bell,
          color: 'text-orange-600',
          title: 'Alert Trigger',
        }
      default:
        return {
          Icon: Hand,
          color: 'text-gray-600',
          title: 'Unknown Trigger',
        }
    }
  }

  const getActions = (task: DiagnosisResponse) => {
    const actions = []

    if (task.status === 'running' || task.status === 'waiting') {
      actions.push(
        <Link
          key="logs"
          to={`/tasks/${task.diagnosis_id}`}
          className="text-blue-600 hover:text-blue-700 text-sm font-medium"
        >
          Logs
        </Link>,
      )
      actions.push(
        <button
          key="cancel"
          className="text-red-600 hover:text-red-700 text-sm font-medium"
        >
          Cancel
        </button>,
      )
    }

    if (task.status === 'completed') {
      actions.push(
        <Link
          key="report"
          to={`/reports/${task.diagnosis_id}`}
          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm font-medium"
        >
          <FileText className="h-4 w-4" />
          Report
        </Link>,
      )
    }

    if (task.status === 'error' || task.status === 'interrupted') {
      actions.push(
        <Link
          key="logs"
          to={`/tasks/${task.diagnosis_id}`}
          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm font-medium"
        >
          <Eye className="h-4 w-4" />
          Logs
        </Link>,
      )
      actions.push(
        <button
          key="retry"
          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm font-medium"
        >
          <RotateCw className="h-4 w-4" />
          Retry
        </button>,
      )
    }

    if (task.status === 'cancelled') {
      actions.push(
        <button
          key="retry"
          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm font-medium"
        >
          <RotateCw className="h-4 w-4" />
          Retry
        </button>,
      )
    }

    if (task.status === 'pending') {
      actions.push(
        <button
          key="cancel"
          className="inline-flex items-center gap-1 text-red-600 hover:text-red-700 text-sm font-medium"
        >
          <XCircle className="h-4 w-4" />
          Cancel
        </button>,
      )
    }

    return actions
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-gray-200 rounded" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Tasks</h2>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as any)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="error">Failed</option>
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Name/ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Started
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredTasks.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center">
                    <p className="text-gray-500">
                      No diagnosis tasks yet. Create your first task to get started.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredTasks.map((task) => (
                  <tr key={task.diagnosis_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {(() => {
                          const { Icon, color, title } = getTriggerIcon(task.trigger_source)
                          return (
                            <div title={title}>
                              <Icon className={`h-4 w-4 ${color} flex-shrink-0`} />
                            </div>
                          )
                        })()}
                        <Link
                          to={`/tasks/${task.diagnosis_id}`}
                          className="text-sm font-mono text-blue-600 hover:text-blue-700"
                          title={task.diagnosis_id}
                        >
                          {formatTaskName(task.diagnosis_id)}
                        </Link>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {getTaskType(task)}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={task.status} size="sm" />
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {formatRelativeTime(task.started_at || task.timestamp)}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        {getActions(task)}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {filteredTasks.length > 0 && (
          <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
            <p className="text-sm text-gray-500">
              Showing 1-{filteredTasks.length} of {filteredTasks.length} tasks
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
