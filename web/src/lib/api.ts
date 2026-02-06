import type { DiagnosticRequest, DiagnosisResponse, HealthResponse } from '@/types'
import { getMockDiagnosis, getMockDiagnosesList } from './mockData'

/**
 * Determine API base URL based on environment
 * - Development: use empty string to leverage Vite proxy
 * - Production: use VITE_API_URL environment variable
 */
const getApiBaseUrl = (): string => {
  // Use full URL in production or when proxy is explicitly disabled
  if (import.meta.env.PROD) {
    return import.meta.env.VITE_API_URL || 'http://localhost:8000'
  }
  // In development, use relative paths (Vite proxy handles routing)
  return ''
}

const API_BASE_URL = getApiBaseUrl()
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

// Log API configuration for debugging
if (typeof window !== 'undefined') {
  console.debug('[API Config]', {
    baseUrl: API_BASE_URL || '(using Vite proxy)',
    useMockData: USE_MOCK_DATA,
    environment: import.meta.env.MODE,
  })
}

interface ListOptions {
  limit?: number
  offset?: number
  status?: string
}

/**
 * API client for diagnosis operations
 */
export const api = {
  /**
   * Check if the API is healthy
   */
  async getHealth(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE_URL}/health`)
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.statusText}`)
    }
    return response.json()
  },

  /**
   * Create a new diagnosis request
   */
  async createDiagnosis(request: DiagnosticRequest): Promise<DiagnosisResponse> {
    const response = await fetch(`${API_BASE_URL}/diagnose`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })
    if (!response.ok) {
      throw new Error(`Failed to create diagnosis: ${response.statusText}`)
    }
    return response.json()
  },

  /**
   * Get a specific diagnosis by ID
   */
  async getDiagnosis(id: string): Promise<DiagnosisResponse> {
    if (USE_MOCK_DATA) {
      const diagnosis = getMockDiagnosis(id)
      if (!diagnosis) {
        throw new Error(`Diagnosis not found: ${id}`)
      }
      // Simulate network delay
      await new Promise((resolve) => setTimeout(resolve, 300))
      return diagnosis
    }

    const response = await fetch(`${API_BASE_URL}/diagnose/${id}`)
    if (!response.ok) {
      throw new Error(`Failed to get diagnosis: ${response.statusText}`)
    }
    return response.json()
  },

  /**
   * List all diagnoses with optional filtering
   */
  async listDiagnoses(options?: ListOptions): Promise<DiagnosisResponse[]> {
    if (USE_MOCK_DATA) {
      // Simulate network delay
      await new Promise((resolve) => setTimeout(resolve, 500))
      return getMockDiagnosesList(options)
    }

    const params = new URLSearchParams()
    if (options?.limit) params.append('limit', options.limit.toString())
    if (options?.offset) params.append('offset', options.offset.toString())
    if (options?.status) params.append('status', options.status)

    const url = `${API_BASE_URL}/diagnoses?${params.toString()}`
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`Failed to list diagnoses: ${response.statusText}`)
    }
    return response.json()
  },

  /**
   * Cancel a pending diagnosis
   */
  async cancelDiagnosis(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/diagnose/${id}/cancel`, {
      method: 'POST',
    })
    if (!response.ok) {
      throw new Error(`Failed to cancel diagnosis: ${response.statusText}`)
    }
  },
}
