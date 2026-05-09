import clsx from 'clsx'
import type { CampaignStatus, LeadStatus } from '@/lib/types'

type StatusValue = CampaignStatus | LeadStatus | string

const statusConfig: Record<string, { label: string; classes: string }> = {
  // Campaign statuses
  active: { label: 'Active', classes: 'bg-green-100 text-green-800' },
  paused: { label: 'Paused', classes: 'bg-yellow-100 text-yellow-800' },
  draft: { label: 'Draft', classes: 'bg-gray-100 text-gray-700' },
  completed: { label: 'Completed', classes: 'bg-blue-100 text-blue-800' },

  // Lead statuses
  pending: { label: 'Pending', classes: 'bg-gray-100 text-gray-700' },
  called: { label: 'Called', classes: 'bg-blue-100 text-blue-800' },
  interested: { label: 'Interested', classes: 'bg-green-100 text-green-800' },
  not_interested: { label: 'Not Interested', classes: 'bg-red-100 text-red-800' },
  callback: { label: 'Callback', classes: 'bg-yellow-100 text-yellow-800' },
  wrong_number: { label: 'Wrong Number', classes: 'bg-orange-100 text-orange-800' },
  dnd: { label: 'DND', classes: 'bg-red-100 text-red-800' },
  failed: { label: 'Failed', classes: 'bg-red-100 text-red-800' },
}

interface StatusBadgeProps {
  status: StatusValue
  className?: string
}

export default function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status] || {
    label: status,
    classes: 'bg-gray-100 text-gray-700',
  }

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize',
        config.classes,
        className
      )}
    >
      {config.label}
    </span>
  )
}
