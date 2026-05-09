'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import Layout from '@/components/Layout'
import StatCard from '@/components/StatCard'
import StatusBadge from '@/components/StatusBadge'
import { useAuth, formatPaise, formatDateTime, formatDuration } from '@/lib/auth'
import { api } from '@/lib/api'
import type { Campaign, CallRecord, WalletBalance } from '@/lib/types'

export default function DashboardPage() {
  const { user, loading: authLoading, logout } = useAuth()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [calls, setCalls] = useState<CallRecord[]>([])
  const [wallet, setWallet] = useState<WalletBalance | null>(null)
  const [dataLoading, setDataLoading] = useState(true)

  useEffect(() => {
    if (!user) return

    Promise.all([
      api.campaigns.list().catch(() => [] as Campaign[]),
      api.calls.list({ page: 1 }).catch(() => [] as CallRecord[]),
      api.wallet.balance().catch(() => null),
    ]).then(([c, cl, w]) => {
      setCampaigns(c)
      setCalls(cl.slice(0, 10))
      setWallet(w)
      setDataLoading(false)
    })
  }, [user])

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-500 text-sm">Loading...</p>
        </div>
      </div>
    )
  }

  const totalCampaigns = campaigns.length
  const activeCampaigns = campaigns.filter((c) => c.status === 'active').length

  const today = new Date().toISOString().split('T')[0]
  const callsToday = calls.filter((c) => c.started_at?.startsWith(today)).length

  const balancePaise = wallet?.balance_paise ?? 0
  const lowBalance = balancePaise < 20000 // less than ₹200

  const recentCampaigns = campaigns.slice(0, 5)

  return (
    <Layout user={user} onLogout={logout}>
      {/* Low balance warning */}
      {!dataLoading && lowBalance && (
        <div className="mb-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg flex items-center gap-3">
          <svg
            className="w-5 h-5 text-yellow-600 flex-shrink-0"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          <p className="text-sm text-yellow-800">
            <span className="font-medium">Low wallet balance!</span> Your balance is{' '}
            {formatPaise(balancePaise)}. Please{' '}
            <Link href="/wallet" className="underline font-medium">
              top up your wallet
            </Link>{' '}
            to continue calling.
          </p>
        </div>
      )}

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Welcome back, {user?.company_name}</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          title="Total Campaigns"
          value={dataLoading ? '...' : totalCampaigns}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"
              />
            </svg>
          }
        />
        <StatCard
          title="Active Campaigns"
          value={dataLoading ? '...' : activeCampaigns}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          }
        />
        <StatCard
          title="Calls Today"
          value={dataLoading ? '...' : callsToday}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"
              />
            </svg>
          }
        />
        <StatCard
          title="Wallet Balance"
          value={dataLoading ? '...' : formatPaise(balancePaise)}
          subtitle="₹12/min calling rate"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"
              />
            </svg>
          }
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent campaigns */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-900">Recent Campaigns</h2>
            <Link
              href="/campaigns"
              className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
            >
              View all
            </Link>
          </div>

          {dataLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="skeleton h-4 rounded flex-1" />
                  <div className="skeleton h-5 rounded w-16" />
                </div>
              ))}
            </div>
          ) : recentCampaigns.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-500 text-sm mb-3">No campaigns yet</p>
              <Link href="/campaigns/new" className="btn-primary text-sm">
                Create Campaign
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {recentCampaigns.map((c) => (
                <Link
                  key={c.id}
                  href={`/campaigns/${c.id}`}
                  className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-900">{c.name}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {c.called_count} / {c.total_numbers} called
                    </p>
                  </div>
                  <StatusBadge status={c.status} />
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Recent calls */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-900">Recent Calls</h2>
            <Link
              href="/calls"
              className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
            >
              View all
            </Link>
          </div>

          {dataLoading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="skeleton h-4 rounded flex-1" />
                  <div className="skeleton h-5 rounded w-16" />
                </div>
              ))}
            </div>
          ) : calls.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-500 text-sm">No calls recorded yet</p>
            </div>
          ) : (
            <div className="space-y-2">
              {calls.slice(0, 8).map((call) => (
                <div
                  key={call.id}
                  className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-900">{call.phone_number}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {formatDuration(call.duration_seconds)} &bull; {formatDateTime(call.started_at)}
                    </p>
                  </div>
                  <StatusBadge status={call.lead_status} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}
