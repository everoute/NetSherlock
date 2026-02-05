import type { RootCauseCategory } from '@/types'
import { cn, getRootCauseColor, getRootCauseLabel } from '@/lib/utils'

interface RootCauseBadgeProps {
  category: RootCauseCategory
  size?: 'sm' | 'md'
}

export function RootCauseBadge({ category, size = 'md' }: RootCauseBadgeProps) {
  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
  }

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium',
        getRootCauseColor(category),
        sizeClasses[size],
      )}
    >
      {getRootCauseLabel(category)}
    </span>
  )
}
