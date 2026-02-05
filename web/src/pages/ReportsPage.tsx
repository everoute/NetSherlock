import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Search } from 'lucide-react'
import { api } from '@/lib/api'
import type { DiagnosisResponse } from '@/types'
import { RootCauseBadge } from '@/components/RootCauseBadge'
import { ConfidenceBar } from '@/components/ConfidenceBar'

export function ReportsPage() {
  const [reports, setReports] = useState<DiagnosisResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    loadReports()
  }, [])

  async function loadReports() {
    try {
      const data = await api.listDiagnoses({ limit: 100 })
      const completed = data.filter((d) => d.status === 'completed' && d.root_cause)
      setReports(completed)
    } catch (error) {
      console.error('Failed to load reports:', error)
    } finally {
      setLoading(false)
    }
  }

  const filteredReports = reports.filter(
    (report) =>
      report.diagnosis_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      report.summary?.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 bg-gray-200 rounded" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Reports</h2>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search reports..."
              className="pl-10 pr-4 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Summary
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Root Cause
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Confidence
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredReports.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center">
                    <p className="text-gray-500">
                      No reports available. Complete a diagnosis to see reports here.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredReports.map((report) => (
                  <tr key={report.diagnosis_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <Link
                        to={`/reports/${report.diagnosis_id}`}
                        className="text-sm font-mono text-blue-600 hover:text-blue-700"
                      >
                        {report.diagnosis_id.slice(0, 16)}...
                      </Link>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-sm text-gray-900 line-clamp-2">
                        {report.summary || 'No summary available'}
                      </p>
                    </td>
                    <td className="px-6 py-4">
                      {report.root_cause && (
                        <RootCauseBadge category={report.root_cause.category} size="sm" />
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {report.root_cause && (
                        <ConfidenceBar confidence={report.root_cause.confidence} />
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <Link
                        to={`/reports/${report.diagnosis_id}`}
                        className="text-blue-600 hover:text-blue-700 text-sm font-medium"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
