'use client'

import { useEffect, useState } from 'react'
import Script from 'next/script'
import Layout from '@/components/Layout'
import { useAuth, formatPaise, formatDateTime } from '@/lib/auth'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import type { WalletBalance, Transaction } from '@/lib/types'

declare global {
  interface Window {
    Razorpay: new (options: RazorpayOptions) => RazorpayInstance
  }
}

interface RazorpayOptions {
  key: string
  amount: number
  currency: string
  name: string
  description: string
  order_id: string
  handler: (response: RazorpayPaymentResponse) => void
  prefill: {
    email?: string
  }
  theme: {
    color: string
  }
  modal?: {
    ondismiss?: () => void
  }
}

interface RazorpayInstance {
  open: () => void
}

interface RazorpayPaymentResponse {
  razorpay_order_id: string
  razorpay_payment_id: string
  razorpay_signature: string
}

const TOPUP_AMOUNTS = [
  { label: '₹500', paise: 50000 },
  { label: '₹2,000', paise: 200000 },
  { label: '₹5,000', paise: 500000 },
  { label: '₹10,000', paise: 1000000 },
]

export default function WalletPage() {
  const { user, loading: authLoading, logout } = useAuth()
  const { showToast } = useToast()

  const [wallet, setWallet] = useState<WalletBalance | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [txPage, setTxPage] = useState(1)
  const [topupLoading, setTopupLoading] = useState(false)
  const [customAmount, setCustomAmount] = useState('')
  const [razorpayReady, setRazorpayReady] = useState(false)

  useEffect(() => {
    if (!user) return
    loadData()
  }, [user])

  useEffect(() => {
    if (!user) return
    api.wallet.transactions(txPage).then(setTransactions).catch(() => {})
  }, [txPage, user])

  async function loadData() {
    setLoading(true)
    try {
      const [w, tx] = await Promise.all([
        api.wallet.balance(),
        api.wallet.transactions(1),
      ])
      setWallet(w)
      setTransactions(tx)
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to load wallet', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleTopup(amountPaise: number) {
    if (!razorpayReady) {
      showToast('Payment system loading, please wait...', 'error')
      return
    }
    if (amountPaise < 10000) {
      showToast('Minimum top-up is ₹100', 'error')
      return
    }

    setTopupLoading(true)
    try {
      const order = await api.wallet.createTopupOrder(amountPaise)

      const options: RazorpayOptions = {
        key: order.key_id || process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID || '',
        amount: order.amount,
        currency: order.currency || 'INR',
        name: 'AI Caller',
        description: 'Wallet Top-up',
        order_id: order.order_id,
        prefill: {
          email: user?.email,
        },
        theme: {
          color: '#4f46e5',
        },
        handler: async (response: RazorpayPaymentResponse) => {
          try {
            await api.wallet.verifyTopup(
              response.razorpay_order_id,
              response.razorpay_payment_id,
              response.razorpay_signature
            )
            showToast('Payment successful! Wallet updated.', 'success')
            loadData()
          } catch (err: unknown) {
            showToast(
              err instanceof Error ? err.message : 'Payment verification failed',
              'error'
            )
          }
        },
        modal: {
          ondismiss: () => {
            setTopupLoading(false)
          },
        },
      }

      const rzp = new window.Razorpay(options)
      rzp.open()
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to create payment order', 'error')
      setTopupLoading(false)
    }
  }

  function handleCustomTopup() {
    const amount = parseFloat(customAmount)
    if (isNaN(amount) || amount <= 0) {
      showToast('Enter a valid amount', 'error')
      return
    }
    const paise = Math.round(amount * 100)
    handleTopup(paise)
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <>
      <Script
        src="https://checkout.razorpay.com/v1/checkout.js"
        onLoad={() => setRazorpayReady(true)}
        strategy="afterInteractive"
      />

      <Layout user={user} onLogout={logout}>
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Wallet</h1>
          <p className="text-gray-500 mt-1">Manage your calling credits</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column - balance + topup */}
          <div className="lg:col-span-1 space-y-4">
            {/* Balance card */}
            <div className="card text-center">
              <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <svg
                  className="w-8 h-8 text-indigo-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"
                  />
                </svg>
              </div>
              <p className="text-sm font-medium text-gray-500 mb-1">Available Balance</p>
              {loading ? (
                <div className="skeleton h-10 rounded w-32 mx-auto" />
              ) : (
                <p className="text-4xl font-bold text-gray-900">
                  {formatPaise(wallet?.balance_paise ?? 0)}
                </p>
              )}
              <p className="text-xs text-gray-400 mt-2">₹12 per minute call rate</p>

              {!loading && (wallet?.balance_paise ?? 0) < 20000 && (
                <div className="mt-4 p-3 bg-yellow-50 rounded-lg text-left">
                  <p className="text-xs text-yellow-800">
                    <span className="font-semibold">Low balance!</span> Top up to continue
                    campaigns.
                  </p>
                </div>
              )}
            </div>

            {/* Quick topup buttons */}
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Quick Top-up</h3>
              <div className="grid grid-cols-2 gap-2 mb-3">
                {TOPUP_AMOUNTS.map((amt) => (
                  <button
                    key={amt.paise}
                    onClick={() => handleTopup(amt.paise)}
                    disabled={topupLoading}
                    className="btn-secondary text-sm py-2 hover:border-indigo-400 hover:text-indigo-600 transition-colors disabled:opacity-50"
                  >
                    {amt.label}
                  </button>
                ))}
              </div>

              <div className="border-t border-gray-100 pt-3">
                <label className="label text-xs">Custom Amount (₹)</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    min="100"
                    step="1"
                    value={customAmount}
                    onChange={(e) => setCustomAmount(e.target.value)}
                    placeholder="Enter amount"
                    className="input-field text-sm flex-1"
                  />
                  <button
                    onClick={handleCustomTopup}
                    disabled={topupLoading || !customAmount}
                    className="btn-primary text-sm px-3 disabled:opacity-50"
                  >
                    {topupLoading ? '...' : 'Pay'}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Right column - transaction history */}
          <div className="lg:col-span-2">
            <div className="card p-0 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200">
                <h3 className="text-base font-semibold text-gray-900">Transaction History</h3>
              </div>

              {loading ? (
                <div className="divide-y divide-gray-100">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="px-6 py-4 flex items-center gap-4">
                      <div className="skeleton h-4 rounded w-24" />
                      <div className="skeleton h-4 rounded flex-1" />
                      <div className="skeleton h-4 rounded w-20" />
                    </div>
                  ))}
                </div>
              ) : transactions.length === 0 ? (
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
                      d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z"
                    />
                  </svg>
                  <p>No transactions yet</p>
                </div>
              ) : (
                <>
                  {/* Header */}
                  <div className="grid grid-cols-12 px-6 py-3 bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    <div className="col-span-3">Date</div>
                    <div className="col-span-2">Type</div>
                    <div className="col-span-4">Description</div>
                    <div className="col-span-3 text-right">Amount</div>
                  </div>

                  <div className="divide-y divide-gray-100">
                    {transactions.map((tx) => (
                      <div key={tx.id} className="grid grid-cols-12 px-6 py-4 items-center">
                        <div className="col-span-3 text-sm text-gray-500">
                          {formatDateTime(tx.created_at)}
                        </div>
                        <div className="col-span-2">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                              tx.type === 'topup'
                                ? 'bg-green-100 text-green-700'
                                : 'bg-red-100 text-red-700'
                            }`}
                          >
                            {tx.type === 'topup' ? 'Top-up' : 'Deduction'}
                          </span>
                        </div>
                        <div className="col-span-4 text-sm text-gray-600 truncate pr-2">
                          {tx.description}
                        </div>
                        <div
                          className={`col-span-3 text-sm font-semibold text-right ${
                            tx.type === 'topup' ? 'text-green-600' : 'text-red-600'
                          }`}
                        >
                          {tx.type === 'topup' ? '+' : '-'}
                          {formatPaise(tx.amount_paise)}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Pagination */}
                  <div className="px-6 py-3 border-t border-gray-100 flex items-center justify-between">
                    <p className="text-xs text-gray-500">Page {txPage}</p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setTxPage((p) => Math.max(1, p - 1))}
                        disabled={txPage === 1}
                        className="btn-secondary text-xs py-1 px-2 disabled:opacity-40"
                      >
                        Prev
                      </button>
                      <button
                        onClick={() => setTxPage((p) => p + 1)}
                        disabled={transactions.length < 20}
                        className="btn-secondary text-xs py-1 px-2 disabled:opacity-40"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </Layout>
    </>
  )
}
