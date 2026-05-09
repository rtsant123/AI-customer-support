'use client'

import Layout from '@/components/Layout'
import { useAuth } from '@/lib/auth'

export default function AdminPage() {
  const { user, loading: authLoading, logout } = useAuth()

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!user?.is_admin) {
    return (
      <Layout user={user} onLogout={logout}>
        <div className="text-center py-20">
          <div className="w-16 h-16 bg-red-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg
              className="w-8 h-8 text-red-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">Access Denied</h2>
          <p className="text-gray-500">You do not have permission to view this page.</p>
        </div>
      </Layout>
    )
  }

  return (
    <Layout user={user} onLogout={logout}>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
        <p className="text-gray-500 mt-1">Platform administration &amp; analytics</p>
      </div>

      {/* Coming soon banner */}
      <div className="card text-center py-16">
        <div className="w-20 h-20 bg-indigo-50 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <svg
            className="w-10 h-10 text-indigo-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
            />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-gray-900 mb-3">Admin Dashboard</h2>
        <p className="text-gray-500 max-w-md mx-auto mb-8">
          The full admin panel is coming soon. It will include client management, revenue
          analytics, call statistics, and platform controls.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-lg mx-auto text-left">
          {[
            { icon: '👥', label: 'All Clients', desc: 'View all registered clients and their usage' },
            { icon: '📊', label: 'Revenue Analytics', desc: 'Total revenue, call minutes, billing' },
            { icon: '📡', label: 'Active Campaigns', desc: 'Monitor all running campaigns' },
          ].map((feature) => (
            <div
              key={feature.label}
              className="p-4 bg-gray-50 rounded-lg border border-gray-200 opacity-60"
            >
              <div className="text-2xl mb-2">{feature.icon}</div>
              <p className="text-sm font-semibold text-gray-700">{feature.label}</p>
              <p className="text-xs text-gray-500 mt-1">{feature.desc}</p>
            </div>
          ))}
        </div>

        <div className="mt-8 inline-flex items-center gap-2 px-4 py-2 bg-indigo-50 text-indigo-700 rounded-full text-sm font-medium">
          <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
          Coming Soon
        </div>
      </div>
    </Layout>
  )
}
