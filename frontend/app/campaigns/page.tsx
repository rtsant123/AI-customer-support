'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import Layout from '@/components/Layout'
import StatusBadge from '@/components/StatusBadge'
import Table, { Column } from '@/components/Table'
import { useAuth, formatDateTime } from '@/lib/auth'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import type { Campaign } from '@/lib/types'

export default function CampaignsPage() {
  const { user, loading: authLoading, logout } = useAuth()
  const { showToast } = useToast()
  const router = useRouter()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    loadCampaigns()
  }, [user])

  async function loadCampaigns() {
    setLoading(true)
    try {
      const data = await api.campaigns.list()
      setCampaigns(data)
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to load campaigns', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleLaunch(id: string) {
    setActionLoading(id)
    try {
      await api.campaigns.launch(id)
      showToast('Campaign launched!', 'success')
      loadCampaigns()
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to launch campaign', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handlePause(id: string) {
    setActionLoading(id)
    try {
      await api.campaigns.pause(id)
      showToast('Campaign paused', 'success')
      loadCampaigns()
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to pause campaign', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleResume(id: string) {
    setActionLoading(id)
    try {
      await api.campaigns.resume(id)
      showToast('Campaign resumed!', 'success')
      loadCampaigns()
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to resume campaign', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete campaign "${name}"? This cannot be undone.`)) return
    setActionLoading(id)
    try {
      await api.campaigns.delete(id)
      showToast('Campaign deleted', 'success')
      loadCampaigns()
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to delete campaign', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  const columns: Column<Campaign & Record<string, unknown>>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (_, row) => (
        <div>
          <p className="font-medium text-gray-900">{row.name as string}</p>
          <p className="text-xs text-gray-500 capitalize">{(row.language as string)}</p>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (val) => <StatusBadge status={val as string} />,
    },
    {
      key: 'total_numbers',
      header: 'Numbers',
      render: (val) => <span>{val as number}</span>,
    },
    {
      key: 'called_count',
      header: 'Called',
      render: (val) => <span>{val as number}</span>,
    },
    {
      key: 'interested_count',
      header: 'Interested',
      render: (val) => <span className="text-green-700 font-medium">{val as number}</span>,
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (val) => <span className="text-gray-500">{formatDateTime(val as string)}</span>,
    },
    {
      key: 'id',
      header: 'Actions',
      render: (val, row) => {
        const id = val as string
        const isLoading = actionLoading === id
        return (
          <div className="flex items-center gap-2">
            <Link
              href={`/campaigns/${id}`}
              className="text-indigo-600 hover:text-indigo-700 text-xs font-medium"
            >
              View
            </Link>

            {row.status === 'draft' && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleLaunch(id)
                }}
                disabled={isLoading}
                className="text-green-600 hover:text-green-700 text-xs font-medium disabled:opacity-50"
              >
                {isLoading ? '...' : 'Launch'}
              </button>
            )}

            {row.status === 'active' && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handlePause(id)
                }}
                disabled={isLoading}
                className="text-yellow-600 hover:text-yellow-700 text-xs font-medium disabled:opacity-50"
              >
                {isLoading ? '...' : 'Pause'}
              </button>
            )}

            {row.status === 'paused' && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleResume(id)
                }}
                disabled={isLoading}
                className="text-green-600 hover:text-green-700 text-xs font-medium disabled:opacity-50"
              >
                {isLoading ? '...' : 'Resume'}
              </button>
            )}

            <button
              onClick={(e) => {
                e.stopPropagation()
                handleDelete(id, row.name as string)
              }}
              disabled={isLoading || row.status === 'active'}
              className="text-red-600 hover:text-red-700 text-xs font-medium disabled:opacity-30 disabled:cursor-not-allowed"
              title={row.status === 'active' ? 'Pause before deleting' : 'Delete'}
            >
              Delete
            </button>
          </div>
        )
      },
    },
  ]

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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Campaigns</h1>
          <p className="text-gray-500 mt-1">{campaigns.length} total campaigns</p>
        </div>
        <Link href="/campaigns/new" className="btn-primary flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
          New Campaign
        </Link>
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <Table
          columns={columns as Column<Record<string, unknown>>[]}
          data={campaigns as unknown as Record<string, unknown>[]}
          loading={loading}
          emptyMessage="No campaigns yet. Create your first campaign to get started."
          onRowClick={(row) => router.push(`/campaigns/${row.id as string}`)}
          keyExtractor={(row) => row.id as string}
        />
      </div>
    </Layout>
  )
}
