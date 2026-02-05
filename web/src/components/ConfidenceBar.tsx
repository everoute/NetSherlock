interface ConfidenceBarProps {
  confidence: number // 0-1
}

export function ConfidenceBar({ confidence }: ConfidenceBarProps) {
  const percentage = Math.round(confidence * 100)

  const getColor = () => {
    if (percentage >= 80) return 'bg-green-500'
    if (percentage >= 60) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full ${getColor()} transition-all duration-300`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-sm text-gray-600 font-medium w-10">
        {percentage}%
      </span>
    </div>
  )
}
