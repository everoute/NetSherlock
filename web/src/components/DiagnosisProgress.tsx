import { Check } from 'lucide-react'
import { cn, DIAGNOSIS_PHASES, getPhaseStep } from '@/lib/utils'

interface DiagnosisProgressProps {
  phase?: string
}

export function DiagnosisProgress({ phase }: DiagnosisProgressProps) {
  const currentStep = getPhaseStep(phase)

  return (
    <div className="flex items-center w-full">
      {DIAGNOSIS_PHASES.map((p, index) => {
        const isCompleted = currentStep > index
        const isActive = currentStep === index
        const isUpcoming = currentStep < index

        return (
          <div key={p.key} className="flex items-center flex-1 last:flex-none">
            {/* Step circle + label */}
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  'w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium border-2 transition-all',
                  isCompleted && 'bg-green-500 border-green-500 text-white',
                  isActive && 'bg-blue-500 border-blue-500 text-white animate-pulse',
                  isUpcoming && 'bg-white border-gray-300 text-gray-400',
                )}
              >
                {isCompleted ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <span>{index + 1}</span>
                )}
              </div>
              <span
                className={cn(
                  'mt-1.5 text-xs font-medium whitespace-nowrap',
                  isCompleted && 'text-green-700',
                  isActive && 'text-blue-700',
                  isUpcoming && 'text-gray-400',
                )}
              >
                {p.label}
              </span>
            </div>

            {/* Connector line (not after last step) */}
            {index < DIAGNOSIS_PHASES.length - 1 && (
              <div
                className={cn(
                  'flex-1 h-0.5 mx-2 mt-[-1.25rem] transition-all',
                  currentStep > index ? 'bg-green-500' : 'bg-gray-200',
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
