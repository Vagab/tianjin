import { useHalt, useResume } from '../../api/hooks'
import { useStatus } from '../../api/hooks'

export function BotControls() {
  const { data: status } = useStatus()
  const halt = useHalt()
  const resume = useResume()

  return (
    <div className="flex gap-2">
      {status?.halted ? (
        <button
          onClick={() => resume.mutate()}
          disabled={resume.isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium
            bg-green/15 text-green border border-green/30
            hover:bg-green/25 transition-colors
            disabled:opacity-50"
        >
          {resume.isPending ? 'Resuming...' : 'Resume Trading'}
        </button>
      ) : (
        <button
          onClick={() => halt.mutate()}
          disabled={halt.isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium
            bg-red/15 text-red border border-red/30
            hover:bg-red/25 transition-colors
            disabled:opacity-50"
        >
          {halt.isPending ? 'Halting...' : 'Halt Trading'}
        </button>
      )}
    </div>
  )
}
