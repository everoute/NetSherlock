import type { RootCauseCategory, DiagnosisStatus } from '@/types'

/**
 * Merge classnames together, filtering out falsy values
 */
export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes
    .filter((c) => typeof c === 'string' && c.length > 0)
    .join(' ')
}

/**
 * Get color classes for a root cause category
 */
export function getRootCauseColor(category: RootCauseCategory): string {
  const colors: Record<RootCauseCategory, string> = {
    vm_internal: 'bg-purple-100 text-purple-700 border-purple-300',
    host_internal: 'bg-red-100 text-red-700 border-red-300',
    vhost_processing: 'bg-orange-100 text-orange-700 border-orange-300',
    physical_network: 'bg-blue-100 text-blue-700 border-blue-300',
    configuration: 'bg-yellow-100 text-yellow-700 border-yellow-300',
    resource_contention: 'bg-pink-100 text-pink-700 border-pink-300',
    unknown: 'bg-gray-100 text-gray-700 border-gray-300',
  }
  return colors[category] || colors.unknown
}

/**
 * Get display label for a root cause category
 */
export function getRootCauseLabel(category: RootCauseCategory): string {
  const labels: Record<RootCauseCategory, string> = {
    vm_internal: 'VM Internal',
    host_internal: 'Host Internal',
    vhost_processing: 'Vhost Processing',
    physical_network: 'Physical Network',
    configuration: 'Configuration',
    resource_contention: 'Resource Contention',
    unknown: 'Unknown',
  }
  return labels[category] || 'Unknown'
}

/**
 * Get color classes for a diagnosis status
 */
export function getStatusColor(status: DiagnosisStatus): string {
  const colors: Record<DiagnosisStatus, string> = {
    pending: 'bg-gray-100 text-gray-700',
    running: 'bg-blue-100 text-blue-700',
    waiting: 'bg-yellow-100 text-yellow-700',
    completed: 'bg-green-100 text-green-700',
    cancelled: 'bg-gray-100 text-gray-600',
    error: 'bg-red-100 text-red-700',
    interrupted: 'bg-orange-100 text-orange-700',
  }
  return colors[status] || colors.pending
}

/**
 * Get display label for a diagnosis status
 */
export function getStatusLabel(status: DiagnosisStatus): string {
  const labels: Record<DiagnosisStatus, string> = {
    pending: 'Pending',
    running: 'Running',
    waiting: 'Waiting',
    completed: 'Completed',
    cancelled: 'Cancelled',
    error: 'Error',
    interrupted: 'Interrupted',
  }
  return labels[status] || 'Unknown'
}

/**
 * Format a date as relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)} days ago`
  return date.toLocaleDateString()
}

/**
 * Format duration between two dates or milliseconds as a duration string
 */
export function formatDuration(
  startOrMs: string | number | undefined,
  end?: string | undefined,
): string {
  if (!startOrMs) return 'N/A'

  let ms: number

  if (typeof startOrMs === 'number') {
    ms = startOrMs
  } else if (end) {
    const startDate = new Date(startOrMs)
    const endDate = new Date(end)
    ms = endDate.getTime() - startDate.getTime()
  } else {
    return 'N/A'
  }

  if (ms < 0) return 'N/A'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}

/**
 * Copy text to clipboard
 */
export function copyToClipboard(text: string): void {
  navigator.clipboard.writeText(text).catch((err) => {
    console.error('Failed to copy to clipboard:', err)
  })
}

/**
 * Format diagnosis ID to readable task name
 * Examples:
 *   diag-20260204-175008-vm-latency → measurement-20260204-175008
 *   diag-20260205-120000-new-latency → measurement-20260205-120000
 */
export function formatTaskName(diagnosisId: string): string {
  // Extract the date and time parts from diagnosis_id
  // Format: diag-YYYYMMDD-HHMMSS-description
  const parts = diagnosisId.split('-')

  if (parts.length >= 3 && parts[0] === 'diag') {
    // Get date (YYYYMMDD) and time (HHMMSS)
    const date = parts[1] // e.g., 20260204
    const time = parts[2] // e.g., 175008

    // Return in format: measurement-YYYYMMDD-HHMMSS
    return `measurement-${date}-${time}`
  }

  // Fallback to original ID if format doesn't match
  return diagnosisId
}
