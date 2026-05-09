'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Layout from '@/components/Layout'
import StatusBadge from '@/components/StatusBadge'
import Table, { Column } from '@/components/Table'
import { useAuth, formatDateTime, formatDuration, formatPaise } from '@/lib/auth'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import type { Campaign, CampaignStats, PhoneNumber, CallRecord } from '@/lib/types'
import clsx from 'clsx'

type Tab = 'numbers' | 'calls'

export default function CampaignDetailPage() {
  const { user, loading: authLoading, logout } = useAuth()
  const { showToast } = useToast()
  const params = useParams()
  const id = params.id as string

  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [stats, setStats] = useState<CampaignStats | null>(null)
  const [numbers, setNumbers] = useState<PhoneNumber[]>([])
  const [calls, setCalls] = useState<CallRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('numbers')

  useEffect(() => {
    if (!user || !id) return
    loadData()
  }, [user, id])

  useEffect(() => {
    if (!user || !id) return
    if (activeTab === 'numbers') {
      api.campaigns.getNumbers(id).then(setNumbers).catch(() => setNumbers([]))
    } else {
      api.calls.list({ campaign_id: id }).then(setCalls).catch(() => setCalls([]))
    }
  }, [activeTab, user, id])

  async function loadData() {
    setLoading(true)
    try {
      const [c, s] = await Promise.all([
        api.campaigns.get(id),
        api.campaigns.getStats(id).catch(() => null),
      ])
      setCampaign(c)
      setStats(s)
      // Load initial tab data
      const nums = await api.campaigns.getNumbers(id).catch(() => [] as PhoneNumber[])
      setNumbers(nums)
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to load campaign', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleLaunch() {
    setActionLoading(true)
    try {
      await api.campaigns.launch(id)
      showToast('Campaign launched!', 'success')
      loadData()
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to launch', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  async function handlePause() {
    setActionLoading(true)
    try {
      await api.campaigns.pause(id)
      showToast('Campaign paused', 'success')
      loadData()
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to pause', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  async function handleResume() {
    setActionLoading(true)
    try {
      await api.campaigns.resume(id)
      showToast('Campaign resumed!', 'success')
      loadData()
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to resume', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  const progressPct =
    stats && stats.total > 0 ? Math.round((stats.called / stats.total) * 100) : 0

  const numberColumns: Column<PhoneNumber & Record<string, unknown>>[] = [
    { key: 'phone_number', header: 'Phone Number' },
    {
      key: 'lead_status',
      header: 'Status',
      render: (val) => <StatusBadge status={val as string} />,
    },
    { key: 'attempts', header: 'Attempts' },
    {
      key: 'last_attempt_at',
      header: 'Last Attempt',
      render: (val) => (
        <span className="text-gray-500">
          {val ? formatDateTime(val as string) : 'Never'}
        </span>
      ),
    },
  ]

  const callColumns: Column<CallRecord & Record<string, unknown>>[] = [
    { key: 'phone_number', header: 'Phone' },
    {
      key: 'lead_status',
      header: 'Status',
      render: (val) => <StatusBadge status={val as string} />,
    },
    {
      key: 'duration_seconds',
      header: 'Duration',
      render: (val) => <span>{formatDuration(val as number)}</span>,
    },
    {
      key: 'cost_paise',
      header: 'Cost',
      render: (val) => <span className="text-gray-700">{formatPaise(val as number)}</span>,
    },
    {
      key: 'started_at',
      header: 'Date',
      render: (val) => <span className="text-gray-500">{formatDateTime(val as string)}</span>,
    },
    {
      key: 'recording_url',
      header: 'Recording',
      render: (val) =>
        val ? (
          <a
            href={val as string}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:text-indigo-700 text-xs font-medium"
            onClick={(e) => e.stopPropagation()}
          >
            Play
          </a>
        ) : (
          <span className="text-gray-400 text-xs">-</span>
        ),
    },
  ]

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!campaign) {
    return (
      <Layout user={user} onLogout={logout}>
        <div className="text-center py-20">
          <p className="text-gray-500">Campaign not found</p>
        </div>
      </Layout>
    )
  }

  return (
    <Layout user={user} onLogout={logout}>
      {/* Header */}
      <div className="flex items-start justify-between mb-6 flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">{campaign.name}</h1>
            <StatusBadge status={campaign.status} />
          </div>
          <p className="text-gray-500 mt-1 capitalize">
            {campaign.language} &bull; {campaign.agent_name} &bull;{' '}
            {campaign.goal.replace('_', ' ')}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {campaign.status === 'draft' && (
            <button
              onClick={handleLaunch}
              disabled={actionLoading}
              className="btn-primary flex items-center gap-2"
            >
              {actionLoading ? (
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
              Launch Campaign
            </button>
          )}
          {campaign.status === 'active' && (
            <button
              onClick={handlePause}
              disabled={actionLoading}
              className="bg-yellow-500 hover:bg-yellow-600 text-white font-medium py-2 px-4 rounded-lg flex items-center gap-2 disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Pause
            </button>
          )}
          {campaign.status === 'paused' && (
            <button
              onClick={handleResume}
              disabled={actionLoading}
              className="btn-primary flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Resume
            </button>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        {[
          { label: 'Total', value: stats?.total ?? campaign.total_numbers, color: 'text-gray-900' },
          { label: 'Pending', value: stats?.pending ?? 0, color: 'text-gray-600' },
          { label: 'Called', value: stats?.called ?? campaign.called_count, color: 'text-blue-600' },
          { label: 'Interested', value: stats?.interested ?? campaign.interested_count, color: 'text-green-600' },
          { label: 'Callback', value: stats?.callback ?? 0, color: 'text-yellow-600' },
          { label: 'Failed', value: stats?.failed ?? 0, color: 'text-red-600' },
        ].map((stat) => (
          <div key={stat.label} className="card py-4 px-4 text-center">
            <p className={clsx('text-xl font-bold', stat.color)}>{stat.value}</p>
            <p className="text-xs text-gray-500 mt-1">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="card mb-6">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-medium text-gray-700">Calling Progress</p>
          <p className="text-sm font-semibold text-indigo-600">{progressPct}%</p>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div
            className="bg-indigo-600 h-3 rounded-full transition-all duration-500"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <p className="text-xs text-gray-500 mt-2">
          {stats?.called ?? 0} of {stats?.total ?? campaign.total_numbers} numbers called
        </p>
      </div>

      {/* Tabs */}
      <div className="card p-0 overflow-hidden">
        <div className="flex border-b border-gray-200">
          {(['numbers', 'calls'] as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={clsx(
                'px-6 py-3 text-sm font-medium capitalize transition-colors border-b-2 -mb-px',
                activeTab === tab
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              )}
            >
              {tab === 'numbers' ? 'Phone Numbers' : 'Call History'}
            </button>
          ))}
        </div>

        <div className="p-0">
          {activeTab === 'numbers' ? (
            <Table
              columns={numberColumns as Column<Record<string, unknown>>[]}
              data={numbers as unknown as Record<string, unknown>[]}
              loading={false}
              emptyMessage="No phone numbers uploaded yet"
              keyExtractor={(row) => row.id as string}
            />
          ) : (
            <Table
              columns={callColumns as Column<Record<string, unknown>>[]}
              data={calls as unknown as Record<string, unknown>[]}
              loading={false}
              emptyMessage="No calls recorded yet"
              keyExtractor={(row) => row.id as string}
            />
          )}
        </div>
      </div>
    </Layout>
  )
}
