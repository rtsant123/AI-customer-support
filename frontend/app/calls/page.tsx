'use client'

import { useEffect, useState } from 'react'
import Layout from '@/components/Layout'
import StatusBadge from '@/components/StatusBadge'
import { useAuth, formatDateTime, formatDuration, formatPaise } from '@/lib/auth'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import type { Campaign, CallRecord, LeadStatus } from '@/lib/types'
import clsx from 'clsx'

const LEAD_STATUSES: { value: LeadStatus | ''; label: string }[] = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'called', label: 'Called' },
  { value: 'interested', label: 'Interested' },
  { value: 'not_interested', label: 'Not Interested' },
  { value: 'callback', label: 'Callback' },
  { value: 'wrong_number', label: 'Wrong Number' },
  { value: 'dnd', label: 'DND' },
  { value: 'failed', label: 'Failed' },
]

const PAGE_SIZE = 20

export default function CallsPage() {
  const { user, loading: authLoading, logout } = useAuth()
  const { showToast } = useToast()

  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [calls, setCalls] = useState<CallRecord[]>([])
  const [loading, setLoading] = useState(true)

  const [filterCampaign, setFilterCampaign] = useState('')
  const [filterStatus, setFilterStatus] = useState<LeadStatus | ''>('')
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    api.campaigns.list().then(setCampaigns).catch(() => {})
  }, [user])

  useEffect(() => {
    if (!user) return
    loadCalls()
  }, [user, filterCampaign, filterStatus, page])

  async function loadCalls() {
    setLoading(true)
    try {
      const data = await api.calls.list({
        campaign_id: filterCampaign || undefined,
        lead_status: filterStatus || undefined,
        page,
      })
      setCalls(data)
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to load calls', 'error')
    } finally {
      setLoading(false)
    }
  }

  function handleFilterChange() {
    setPage(1)
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <Layout user={user} onLogout={logout}>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Call History</h1>
        <p className="text-gray-500 mt-1">All calls made by your campaigns</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <select
          value={filterCampaign}
          onChange={(e) => {
            setFilterCampaign(e.target.value)
            handleFilterChange()
          }}
          className="input-field w-auto min-w-[180px]"
        >
          <option value="">All Campaigns</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>

        <select
          value={filterStatus}
          onChange={(e) => {
            setFilterStatus(e.target.value as LeadStatus | '')
            handleFilterChange()
          }}
          className="input-field w-auto min-w-[160px]"
        >
          {LEAD_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>

        {(filterCampaign || filterStatus) && (
          <button
            onClick={() => {
              setFilterCampaign('')
              setFilterStatus('')
              setPage(1)
            }}
            className="btn-secondary text-sm"
          >
            Clear Filters
          </button>
        )}
      </div>

      {/* Calls table */}
      <div className="card p-0 overflow-hidden mb-4">
        {loading ? (
          <div className="divide-y divide-gray-100">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="px-6 py-4 flex items-center gap-4">
                <div className="skeleton h-4 rounded w-28" />
                <div className="skeleton h-4 rounded w-36 flex-1" />
                <div className="skeleton h-5 rounded w-20" />
                <div className="skeleton h-4 rounded w-16" />
              </div>
            ))}
          </div>
        ) : calls.length === 0 ? (
          <div className="px-6 py-16 text-center text-gray-500">
            <svg
              className="w-12 h-12 text-gray-300 mx-auto mb-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"
              />
            </svg>
            <p>No calls found</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {/* Table header */}
            <div className="grid grid-cols-12 px-6 py-3 bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              <div className="col-span-2">Phone</div>
              <div className="col-span-3">Campaign</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-1">Duration</div>
              <div className="col-span-1">Cost</div>
              <div className="col-span-2">Date</div>
              <div className="col-span-1"></div>
            </div>

            {calls.map((call) => (
              <div key={call.id}>
                <div
                  className={clsx(
                    'grid grid-cols-12 px-6 py-4 items-center hover:bg-gray-50 cursor-pointer transition-colors',
                    expandedId === call.id && 'bg-indigo-50'
                  )}
                  onClick={() =>
                    setExpandedId(expandedId === call.id ? null : call.id)
                  }
                >
                  <div className="col-span-2 text-sm font-medium text-gray-900 font-mono">
                    {call.phone_number}
                  </div>
                  <div className="col-span-3 text-sm text-gray-600 truncate pr-2">
                    {call.campaign_name}
                  </div>
                  <div className="col-span-2">
                    <StatusBadge status={call.lead_status} />
                  </div>
                  <div className="col-span-1 text-sm text-gray-600">
                    {formatDuration(call.duration_seconds)}
                  </div>
                  <div className="col-span-1 text-sm text-gray-700">
                    {formatPaise(call.cost_paise)}
                  </div>
                  <div className="col-span-2 text-sm text-gray-500">
                    {formatDateTime(call.started_at)}
                  </div>
                  <div className="col-span-1 text-right">
                    <svg
                      className={clsx(
                        'w-4 h-4 text-gray-400 ml-auto transition-transform',
                        expandedId === call.id && 'rotate-180'
                      )}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 9l-7 7-7-7"
                      />
                    </svg>
                  </div>
                </div>

                {/* Expanded row */}
                {expandedId === call.id && (
                  <div className="px-6 py-4 bg-indigo-50 border-t border-indigo-100">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {call.ai_summary && (
                        <div>
                          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                            AI Summary
                          </p>
                          <p className="text-sm text-gray-700 leading-relaxed">
                            {call.ai_summary}
                          </p>
                        </div>
                      )}
                      {call.recording_url && (
                        <div>
                          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                            Recording
                          </p>
                          <a
                            href={call.recording_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-700 font-medium"
                          >
                            <svg
                              className="w-4 h-4"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                            >
                              <path
                                fillRule="evenodd"
                                d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z"
                                clipRule="evenodd"
                              />
                            </svg>
                            Play Recording
                          </a>
                        </div>
                      )}
                      {!call.ai_summary && !call.recording_url && (
                        <p className="text-sm text-gray-500 col-span-2">
                          No summary or recording available for this call.
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          Page {page} &bull; {calls.length} results
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="btn-secondary text-sm disabled:opacity-40"
          >
            Previous
          </button>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={calls.length < PAGE_SIZE}
            className="btn-secondary text-sm disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </Layout>
  )
}
