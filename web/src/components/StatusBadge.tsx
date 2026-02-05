import {
  Clock,
  Loader,
  Pause,
  CheckCircle,
  XCircle,
  AlertCircle,
} from 'lucide-react'
import type { DiagnosisStatus } from '@/types'
import { cn, getStatusColor, getStatusLabel } from '@/lib/utils'

const STATUS_ICONS: Record<DiagnosisStatus, React.ComponentType<{ className?: string }>> = {
  pending: Clock,
  running: Loader,
  waiting: Pause,
  completed: CheckCircle,
  cancelled: XCircle,
  error: AlertCircle,
  interrupted: AlertCircle,
}

interface StatusBadgeProps {
  status: DiagnosisStatus
  size?: 'sm' | 'md' | 'lg'
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const Icon = STATUS_ICONS[status]
  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
    lg: 'px-3 py-1.5 text-base',
  }
  const iconSizes = {
    sm: 'h-3 w-3',
    md: 'h-4 w-4',
    lg: 'h-5 w-5',
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        getStatusColor(status),
        sizeClasses[size],
      )}
    >
      <Icon
        className={cn(
          iconSizes[size],
          status === 'running' && 'animate-spin',
        )}
      />
      {getStatusLabel(status)}
    </span>
  )
}
