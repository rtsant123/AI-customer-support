'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { api, clearToken, getToken } from './api'
import type { UserProfile } from './types'

interface UseAuthReturn {
  user: UserProfile | null
  loading: boolean
  logout: () => void
}

export function useAuth(): UseAuthReturn {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      router.replace('/login')
      return
    }

    api.auth
      .me()
      .then((profile) => {
        setUser(profile)
      })
      .catch(() => {
        clearToken()
        router.replace('/login')
      })
      .finally(() => {
        setLoading(false)
      })
  }, [router])

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
    router.replace('/login')
  }, [router])

  return { user, loading, logout }
}

export function formatPaise(paise: number): string {
  return `₹${(paise / 100).toFixed(2)}`
}

export function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0) return '0s'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m === 0) return `${s}s`
  return `${m}m ${s}s`
}

export function formatDateTime(isoString: string): string {
  if (!isoString) return '-'
  const date = new Date(isoString)
  return date.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(isoString: string): string {
  if (!isoString) return '-'
  const date = new Date(isoString)
  return date.toLocaleDateString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}
