export type Language = 'hindi' | 'english' | 'bangla' | 'tamil'

export type LeadStatus =
  | 'pending'
  | 'called'
  | 'interested'
  | 'not_interested'
  | 'callback'
  | 'wrong_number'
  | 'dnd'
  | 'failed'

export type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed'

export type AgentGender = 'male' | 'female'

export type AgentTone = 'friendly' | 'professional' | 'urgent'

export type CampaignGoal =
  | 'qualify_lead'
  | 'book_appointment'
  | 'reminder'
  | 'survey'

export interface AuthResponse {
  access_token: string
  token_type: string
}

export interface UserProfile {
  id: string
  email: string
  company_name: string
  is_admin: boolean
  created_at: string
}

export interface Campaign {
  id: string
  name: string
  language: Language
  status: CampaignStatus
  agent_name: string
  agent_gender: AgentGender
  agent_tone: AgentTone
  company_name: string
  transfer_condition: string
  product_name: string
  product_price: string
  key_benefits: string[]
  goal: CampaignGoal
  schedule_start_time: string
  schedule_end_time: string
  schedule_days: string[]
  total_numbers: number
  called_count: number
  interested_count: number
  created_at: string
  updated_at: string
}

export interface CampaignCreate {
  name: string
  language: Language
  agent_name: string
  agent_gender: AgentGender
  agent_tone: AgentTone
  company_name: string
  transfer_condition: string
  product_name: string
  product_price: string
  key_benefits: string[]
  goal: CampaignGoal
  schedule_start_time: string
  schedule_end_time: string
  schedule_days: string[]
}

export interface CampaignStats {
  total: number
  pending: number
  called: number
  interested: number
  not_interested: number
  callback: number
  wrong_number: number
  dnd: number
  failed: number
}

export interface PhoneNumber {
  id: string
  campaign_id: string
  phone_number: string
  lead_status: LeadStatus
  attempts: number
  last_attempt_at: string | null
  created_at: string
}

export interface CallRecord {
  id: string
  campaign_id: string
  campaign_name: string
  phone_number: string
  lead_status: LeadStatus
  duration_seconds: number
  cost_paise: number
  recording_url: string | null
  ai_summary: string | null
  started_at: string
  ended_at: string | null
}

export interface WalletBalance {
  balance_paise: number
  balance_inr: number
}

export interface Transaction {
  id: string
  type: 'topup' | 'deduction'
  amount_paise: number
  description: string
  created_at: string
}

export interface RazorpayOrder {
  order_id: string
  amount: number
  currency: string
  key_id: string
}

export interface AdminClient {
  id: string
  email: string
  company_name: string
  balance_paise: number
  total_calls: number
  created_at: string
}

export interface AdminStats {
  total_revenue_paise: number
  total_call_minutes: number
  active_campaigns: number
  total_clients: number
}
