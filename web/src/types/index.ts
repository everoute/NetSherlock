// Diagnosis status types
export type DiagnosisStatus =
  | 'pending'
  | 'running'
  | 'waiting'
  | 'completed'
  | 'cancelled'
  | 'error'
  | 'interrupted'

// Root cause categories
export type RootCauseCategory =
  | 'vm_internal'
  | 'host_internal'
  | 'vhost_processing'
  | 'physical_network'
  | 'configuration'
  | 'resource_contention'
  | 'unknown'

// Request types
export interface DiagnosticRequest {
  network_type: 'vm' | 'system'
  diagnosis_type: 'latency' | 'packet_drop' | 'connectivity'
  src_host?: string
  src_vm?: string
  src_vm_name?: string
  dst_host?: string
  dst_vm?: string
  dst_vm_name?: string
  description?: string
  mode?: 'autonomous' | 'interactive'
  options?: Record<string, unknown>
}

// Response types
export interface RootCause {
  category: RootCauseCategory
  component: string
  confidence: number // 0-1
  evidence: string[]
}

export interface Recommendation {
  priority: number
  action: string
  command?: string
  rationale?: string
}

export interface LogFile {
  name: string
  content: string
}

export interface DiagnosisResponse {
  diagnosis_id: string
  status: DiagnosisStatus
  phase?: string
  timestamp: string
  started_at?: string
  completed_at?: string
  trigger?: 'manual' | 'webhook' | 'alert'
  trigger_source?: 'manual' | 'webhook' | 'alert'
  mode?: 'autonomous' | 'interactive'
  diagnosis_type?: 'latency' | 'packet_drop' | 'connectivity'
  network_type?: 'vm' | 'system'
  src_host?: string
  src_vm?: string
  dst_host?: string
  dst_vm?: string
  summary?: string
  root_cause?: RootCause
  recommendations?: Recommendation[]
  markdown_report?: string
  logs?: LogFile[]
  error?: string
}

export interface HealthResponse {
  status: string
  timestamp: string
  queue_size: number
  engine?: string
}
