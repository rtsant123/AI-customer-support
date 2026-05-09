import type {
  AuthResponse,
  UserProfile,
  Campaign,
  CampaignCreate,
  CampaignStats,
  PhoneNumber,
  CallRecord,
  WalletBalance,
  Transaction,
  RazorpayOrder,
  LeadStatus,
} from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const TOKEN_KEY = 'ac_token'
const COOKIE_NAME = 'ac_token'

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

function setToken(token: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(TOKEN_KEY, token)
  // Also set cookie for middleware
  const expires = new Date()
  expires.setDate(expires.getDate() + 7)
  document.cookie = `${COOKIE_NAME}=${token}; path=/; expires=${expires.toUTCString()}; SameSite=Lax`
}

function clearToken(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem(TOKEN_KEY)
  document.cookie = `${COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    clearToken()
    if (typeof window !== 'undefined') {
      window.location.href = '/login'
    }
    throw new Error('Unauthorized')
  }

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`
    try {
      const errorData = await response.json()
      errorMessage = errorData.detail || errorData.message || errorMessage
    } catch {
      // ignore parse errors
    }
    throw new Error(errorMessage)
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export { getToken, setToken, clearToken }

export const api = {
  auth: {
    async signup(
      email: string,
      password: string,
      company_name: string
    ): Promise<AuthResponse> {
      return apiFetch<AuthResponse>('/auth/signup', {
        method: 'POST',
        body: JSON.stringify({ email, password, company_name }),
      })
    },

    async login(email: string, password: string): Promise<AuthResponse> {
      return apiFetch<AuthResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
    },

    async me(): Promise<UserProfile> {
      return apiFetch<UserProfile>('/auth/me')
    },
  },

  campaigns: {
    async list(): Promise<Campaign[]> {
      return apiFetch<Campaign[]>('/campaigns')
    },

    async create(data: CampaignCreate): Promise<Campaign> {
      return apiFetch<Campaign>('/campaigns', {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },

    async get(id: string): Promise<Campaign> {
      return apiFetch<Campaign>(`/campaigns/${id}`)
    },

    async update(id: string, data: Partial<CampaignCreate>): Promise<Campaign> {
      return apiFetch<Campaign>(`/campaigns/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
    },

    async delete(id: string): Promise<void> {
      return apiFetch<void>(`/campaigns/${id}`, {
        method: 'DELETE',
      })
    },

    async launch(id: string): Promise<void> {
      return apiFetch<void>(`/campaigns/${id}/launch`, {
        method: 'POST',
      })
    },

    async pause(id: string): Promise<void> {
      return apiFetch<void>(`/campaigns/${id}/pause`, {
        method: 'POST',
      })
    },

    async resume(id: string): Promise<void> {
      return apiFetch<void>(`/campaigns/${id}/resume`, {
        method: 'POST',
      })
    },

    async uploadNumbers(
      id: string,
      numbers: string[]
    ): Promise<{ added: number; filtered: number }> {
      return apiFetch<{ added: number; filtered: number }>(
        `/campaigns/${id}/numbers`,
        {
          method: 'POST',
          body: JSON.stringify({ numbers }),
        }
      )
    },

    async getNumbers(id: string): Promise<PhoneNumber[]> {
      return apiFetch<PhoneNumber[]>(`/campaigns/${id}/numbers`)
    },

    async getStats(id: string): Promise<CampaignStats> {
      return apiFetch<CampaignStats>(`/campaigns/${id}/stats`)
    },
  },

  calls: {
    async list(params?: {
      campaign_id?: string
      lead_status?: LeadStatus
      page?: number
    }): Promise<CallRecord[]> {
      const query = new URLSearchParams()
      if (params?.campaign_id) query.set('campaign_id', params.campaign_id)
      if (params?.lead_status) query.set('lead_status', params.lead_status)
      if (params?.page) query.set('page', String(params.page))
      const qs = query.toString()
      return apiFetch<CallRecord[]>(`/calls${qs ? `?${qs}` : ''}`)
    },

    async get(id: string): Promise<CallRecord> {
      return apiFetch<CallRecord>(`/calls/${id}`)
    },
  },

  wallet: {
    async balance(): Promise<WalletBalance> {
      return apiFetch<WalletBalance>('/wallet/balance')
    },

    async transactions(page?: number): Promise<Transaction[]> {
      const query = page ? `?page=${page}` : ''
      return apiFetch<Transaction[]>(`/wallet/transactions${query}`)
    },

    async createTopupOrder(amount_paise: number): Promise<RazorpayOrder> {
      return apiFetch<RazorpayOrder>('/wallet/topup', {
        method: 'POST',
        body: JSON.stringify({ amount_paise }),
      })
    },

    async verifyTopup(
      order_id: string,
      payment_id: string,
      signature: string
    ): Promise<void> {
      return apiFetch<void>('/wallet/topup/verify', {
        method: 'POST',
        body: JSON.stringify({ order_id, payment_id, signature }),
      })
    },
  },
}
