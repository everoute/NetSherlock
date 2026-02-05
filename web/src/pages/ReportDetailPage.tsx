import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, Download, Copy } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '@/lib/api'
import type { DiagnosisResponse } from '@/types'
import { RootCauseBadge } from '@/components/RootCauseBadge'
import { copyToClipboard } from '@/lib/utils'

export function ReportDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [report, setReport] = useState<DiagnosisResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    loadReport()
  }, [id])

  async function loadReport() {
    if (!id) return
    try {
      const data = await api.getDiagnosis(id)
      setReport(data)
    } catch (error) {
      console.error('Failed to load report:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCopyCommand = (command: string) => {
    copyToClipboard(command)
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-1/3" />
          <div className="h-64 bg-gray-200 rounded" />
        </div>
      </div>
    )
  }

  if (!report || !report.root_cause) {
    return (
      <div className="p-6">
        <div className="text-center">
          <p className="text-gray-500">Report not found or not yet completed</p>
          <Link to="/reports" className="text-blue-600 hover:text-blue-700 mt-2 inline-block">
            Back to Reports
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <Link
          to="/reports"
          className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Reports
        </Link>
        <button className="inline-flex items-center gap-2 px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50">
          <Download className="h-4 w-4" />
          Download PDF
        </button>
      </div>

      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">
          Diagnosis Report: {report.diagnosis_id}
        </h1>
        <p className="text-sm text-gray-500">
          Generated: {report.completed_at ? new Date(report.completed_at).toLocaleString() : 'N/A'}
        </p>
      </div>

      <div className="h-px bg-gray-200 mb-6" />

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Summary</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-600">Confidence:</span>{' '}
            <span className="font-semibold text-gray-900">
              {Math.round(report.root_cause.confidence * 100)}%
            </span>
          </div>
          <div>
            <span className="text-gray-600">Root Cause:</span>{' '}
            <RootCauseBadge category={report.root_cause.category} />
          </div>
        </div>
        {report.summary && (
          <p className="mt-4 text-gray-700">{report.summary}</p>
        )}
      </div>

      {report.root_cause && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Root Cause</h2>
          <div className="space-y-3">
            <div>
              <span className="text-sm text-gray-600">Category:</span>{' '}
              <RootCauseBadge category={report.root_cause.category} />
            </div>
            <div>
              <span className="text-sm text-gray-600">Component:</span>{' '}
              <span className="text-sm font-medium text-gray-900">
                {report.root_cause.component}
              </span>
            </div>
            <div>
              <span className="text-sm text-gray-600">Confidence:</span>{' '}
              <span className="text-sm font-medium text-gray-900">
                {Math.round(report.root_cause.confidence * 100)}%
              </span>
            </div>
            {report.root_cause.evidence.length > 0 && (
              <div>
                <p className="text-sm text-gray-600 mb-2">Evidence:</p>
                <ul className="list-disc list-inside space-y-1">
                  {report.root_cause.evidence.map((evidence, i) => (
                    <li key={i} className="text-sm text-gray-700">
                      {evidence}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {report.recommendations && report.recommendations.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Recommendations
          </h2>
          <div className="space-y-4">
            {report.recommendations.map((rec, i) => (
              <div key={i} className="border-l-4 border-blue-500 pl-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900">
                      <span className="inline-block px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs mr-2">
                        PRIORITY {rec.priority}
                      </span>
                      {rec.action}
                    </p>
                    {rec.command && (
                      <div className="mt-2 bg-gray-50 rounded p-2 flex items-center justify-between">
                        <code className="text-sm text-gray-800 font-mono">
                          {rec.command}
                        </code>
                        <button
                          onClick={() => handleCopyCommand(rec.command!)}
                          className="ml-2 text-gray-400 hover:text-gray-600"
                          title="Copy command"
                        >
                          <Copy className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                    {rec.rationale && (
                      <p className="mt-2 text-sm text-gray-600">
                        Rationale: {rec.rationale}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {report.markdown_report && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Full Report
          </h2>
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {report.markdown_report}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}
