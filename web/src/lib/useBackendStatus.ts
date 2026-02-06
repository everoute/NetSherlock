import { useEffect, useState } from 'react'
import { api } from './api'

export interface BackendStatus {
  status: 'healthy' | 'degraded' | 'offline'
  timestamp?: string
  queueSize?: number
  error?: string
}

/**
 * Hook to monitor backend API health status
 * Checks every 10 seconds
 */
export function useBackendStatus() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>({
    status: 'offline',
    error: 'Initializing...',
  })

  useEffect(() => {
    // Check immediately on mount
    checkHealth()

    // Then check every 10 seconds
    const interval = setInterval(checkHealth, 10000)

    return () => clearInterval(interval)
  }, [])

  const checkHealth = async () => {
    try {
      const response = await api.getHealth()

      setBackendStatus({
        status: response.status === 'healthy' ? 'healthy' : 'degraded',
        timestamp: response.timestamp,
        queueSize: response.queue_size,
      })
    } catch (error) {
      setBackendStatus({
        status: 'offline',
        error: error instanceof Error ? error.message : 'Connection failed',
      })
    }
  }

  return backendStatus
}
