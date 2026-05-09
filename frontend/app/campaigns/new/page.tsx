'use client'

import { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Papa from 'papaparse'
import Layout from '@/components/Layout'
import { useAuth } from '@/lib/auth'
import { api } from '@/lib/api'
import { useToast } from '@/components/Toast'
import type { Language, AgentGender, AgentTone, CampaignGoal, CampaignCreate } from '@/lib/types'
import clsx from 'clsx'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const STEPS = [
  { num: 1, label: 'Basic Info' },
  { num: 2, label: 'Agent Setup' },
  { num: 3, label: 'Product/Script' },
  { num: 4, label: 'Upload Numbers' },
]

interface FormData {
  // Step 1
  name: string
  language: Language
  schedule_start_time: string
  schedule_end_time: string
  schedule_days: string[]
  // Step 2
  agent_name: string
  agent_gender: AgentGender
  agent_tone: AgentTone
  company_name: string
  transfer_condition: string
  // Step 3
  product_name: string
  product_price: string
  key_benefits: [string, string, string]
  goal: CampaignGoal
}

export default function NewCampaignPage() {
  const { user, loading: authLoading, logout } = useAuth()
  const { showToast } = useToast()
  const router = useRouter()

  const [step, setStep] = useState(1)
  const [saving, setSaving] = useState(false)
  const [campaignId, setCampaignId] = useState<string | null>(null)

  const [form, setForm] = useState<FormData>({
    name: '',
    language: 'hindi',
    schedule_start_time: '09:00',
    schedule_end_time: '18:00',
    schedule_days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
    agent_name: '',
    agent_gender: 'female',
    agent_tone: 'friendly',
    company_name: '',
    transfer_condition: 'if customer asks for pricing or to speak to a human',
    product_name: '',
    product_price: '',
    key_benefits: ['', '', ''],
    goal: 'qualify_lead',
  })

  // Step 4 - numbers
  const [numbers, setNumbers] = useState<string[]>([])
  const [pastedNumbers, setPastedNumbers] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [uploading, setUploading] = useState(false)

  function update<K extends keyof FormData>(key: K, value: FormData[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function toggleDay(day: string) {
    setForm((prev) => ({
      ...prev,
      schedule_days: prev.schedule_days.includes(day)
        ? prev.schedule_days.filter((d) => d !== day)
        : [...prev.schedule_days, day],
    }))
  }

  function updateBenefit(index: number, value: string) {
    const updated = [...form.key_benefits] as [string, string, string]
    updated[index] = value
    setForm((prev) => ({ ...prev, key_benefits: updated }))
  }

  function validateStep(s: number): string | null {
    if (s === 1) {
      if (!form.name.trim()) return 'Campaign name is required'
      if (form.schedule_days.length === 0) return 'Select at least one calling day'
    }
    if (s === 2) {
      if (!form.agent_name.trim()) return 'Agent name is required'
      if (!form.company_name.trim()) return 'Company name is required'
    }
    if (s === 3) {
      if (!form.product_name.trim()) return 'Product name is required'
    }
    return null
  }

  async function saveAsDraft() {
    const err = validateStep(step)
    if (err) {
      showToast(err, 'error')
      return
    }

    setSaving(true)
    try {
      const payload: CampaignCreate = {
        name: form.name,
        language: form.language,
        schedule_start_time: form.schedule_start_time,
        schedule_end_time: form.schedule_end_time,
        schedule_days: form.schedule_days,
        agent_name: form.agent_name || 'AI Agent',
        agent_gender: form.agent_gender,
        agent_tone: form.agent_tone,
        company_name: form.company_name || user?.company_name || '',
        transfer_condition: form.transfer_condition,
        product_name: form.product_name || 'Our Product',
        product_price: form.product_price,
        key_benefits: form.key_benefits.filter(Boolean),
        goal: form.goal,
      }

      if (campaignId) {
        await api.campaigns.update(campaignId, payload)
        showToast('Draft saved!', 'success')
      } else {
        const campaign = await api.campaigns.create(payload)
        setCampaignId(campaign.id)
        showToast('Draft saved!', 'success')
      }
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to save draft', 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleNext() {
    const err = validateStep(step)
    if (err) {
      showToast(err, 'error')
      return
    }
    if (step === 3) {
      // Auto-fill company name from user if empty
      if (!form.company_name && user?.company_name) {
        update('company_name', user.company_name)
      }
    }
    setStep((s) => s + 1)
  }

  function handleBack() {
    setStep((s) => s - 1)
  }

  function parseCSV(file: File) {
    Papa.parse(file, {
      complete: (result) => {
        const parsed: string[] = []
        for (const row of result.data as string[][]) {
          const val = row[0]?.toString().trim().replace(/\D/g, '')
          if (val && val.length >= 10) {
            parsed.push(val)
          }
        }
        setNumbers((prev) => {
          const combined = [...new Set([...prev, ...parsed])]
          showToast(`Parsed ${parsed.length} numbers from CSV`, 'success')
          return combined
        })
      },
      error: () => {
        showToast('Failed to parse CSV file', 'error')
      },
    })
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) parseCSV(file)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) parseCSV(file)
  }

  function handlePasteNumbers() {
    const lines = pastedNumbers
      .split(/[\n,;]+/)
      .map((l) => l.trim().replace(/\D/g, ''))
      .filter((l) => l.length >= 10)
    if (lines.length === 0) {
      showToast('No valid numbers found', 'error')
      return
    }
    setNumbers((prev) => {
      const combined = [...new Set([...prev, ...lines])]
      showToast(`Added ${lines.length} numbers`, 'success')
      return combined
    })
    setPastedNumbers('')
  }

  async function handleSubmit() {
    if (numbers.length === 0) {
      showToast('Please add at least one phone number', 'error')
      return
    }

    setUploading(true)
    try {
      // Create or update campaign first
      const payload: CampaignCreate = {
        name: form.name,
        language: form.language,
        schedule_start_time: form.schedule_start_time,
        schedule_end_time: form.schedule_end_time,
        schedule_days: form.schedule_days,
        agent_name: form.agent_name,
        agent_gender: form.agent_gender,
        agent_tone: form.agent_tone,
        company_name: form.company_name || user?.company_name || '',
        transfer_condition: form.transfer_condition,
        product_name: form.product_name,
        product_price: form.product_price,
        key_benefits: form.key_benefits.filter(Boolean),
        goal: form.goal,
      }

      let id = campaignId
      if (id) {
        await api.campaigns.update(id, payload)
      } else {
        const campaign = await api.campaigns.create(payload)
        id = campaign.id
        setCampaignId(id)
      }

      // Upload numbers
      const result = await api.campaigns.uploadNumbers(id!, numbers)
      showToast(
        `Campaign created! ${result.added} numbers added, ${result.filtered} filtered.`,
        'success'
      )
      router.push(`/campaigns/${id}`)
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to create campaign', 'error')
    } finally {
      setUploading(false)
    }
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
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Create Campaign</h1>
          <p className="text-gray-500 mt-1">Set up your AI calling campaign in 4 steps</p>
        </div>

        {/* Progress indicator */}
        <div className="flex items-center mb-8">
          {STEPS.map((s, idx) => (
            <div key={s.num} className="flex items-center flex-1">
              <div className="flex flex-col items-center">
                <div
                  className={clsx(
                    'w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-colors',
                    step > s.num
                      ? 'bg-indigo-600 text-white'
                      : step === s.num
                      ? 'bg-indigo-600 text-white ring-4 ring-indigo-100'
                      : 'bg-gray-200 text-gray-500'
                  )}
                >
                  {step > s.num ? (
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  ) : (
                    s.num
                  )}
                </div>
                <span
                  className={clsx(
                    'text-xs mt-1 font-medium hidden sm:block',
                    step >= s.num ? 'text-indigo-600' : 'text-gray-400'
                  )}
                >
                  {s.label}
                </span>
              </div>
              {idx < STEPS.length - 1 && (
                <div
                  className={clsx(
                    'flex-1 h-0.5 mx-2 transition-colors',
                    step > s.num ? 'bg-indigo-600' : 'bg-gray-200'
                  )}
                />
              )}
            </div>
          ))}
        </div>

        {/* Form card */}
        <div className="card">
          {/* Step 1 - Basic Info */}
          {step === 1 && (
            <div className="space-y-5">
              <h2 className="text-lg font-semibold text-gray-900">Basic Information</h2>

              <div>
                <label className="label">Campaign Name *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => update('name', e.target.value)}
                  className="input-field"
                  placeholder="e.g. Q1 Lead Generation Campaign"
                />
              </div>

              <div>
                <label className="label">Language *</label>
                <select
                  value={form.language}
                  onChange={(e) => update('language', e.target.value as Language)}
                  className="input-field"
                >
                  <option value="hindi">Hindi</option>
                  <option value="english">English</option>
                  <option value="bangla">Bangla</option>
                  <option value="tamil">Tamil</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Calling Start Time</label>
                  <input
                    type="time"
                    value={form.schedule_start_time}
                    onChange={(e) => update('schedule_start_time', e.target.value)}
                    className="input-field"
                  />
                </div>
                <div>
                  <label className="label">Calling End Time</label>
                  <input
                    type="time"
                    value={form.schedule_end_time}
                    onChange={(e) => update('schedule_end_time', e.target.value)}
                    className="input-field"
                  />
                </div>
              </div>

              <div>
                <label className="label">Calling Days *</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {DAYS.map((day) => (
                    <button
                      key={day}
                      type="button"
                      onClick={() => toggleDay(day)}
                      className={clsx(
                        'px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors',
                        form.schedule_days.includes(day)
                          ? 'bg-indigo-600 text-white border-indigo-600'
                          : 'bg-white text-gray-600 border-gray-300 hover:border-indigo-400'
                      )}
                    >
                      {day}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 2 - Agent Setup */}
          {step === 2 && (
            <div className="space-y-5">
              <h2 className="text-lg font-semibold text-gray-900">Agent Setup</h2>

              <div>
                <label className="label">Agent Name *</label>
                <input
                  type="text"
                  value={form.agent_name}
                  onChange={(e) => update('agent_name', e.target.value)}
                  className="input-field"
                  placeholder="e.g. Priya, Rahul"
                />
              </div>

              <div>
                <label className="label">Agent Gender</label>
                <div className="flex gap-3 mt-1">
                  {(['female', 'male'] as AgentGender[]).map((g) => (
                    <label
                      key={g}
                      className={clsx(
                        'flex items-center gap-2 px-4 py-2.5 rounded-lg border cursor-pointer transition-colors capitalize',
                        form.agent_gender === g
                          ? 'border-indigo-600 bg-indigo-50 text-indigo-700'
                          : 'border-gray-300 hover:border-indigo-300'
                      )}
                    >
                      <input
                        type="radio"
                        name="gender"
                        value={g}
                        checked={form.agent_gender === g}
                        onChange={() => update('agent_gender', g)}
                        className="sr-only"
                      />
                      {g === 'female' ? '👩' : '👨'} {g.charAt(0).toUpperCase() + g.slice(1)}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="label">Agent Tone</label>
                <div className="flex gap-3 mt-1 flex-wrap">
                  {(['friendly', 'professional', 'urgent'] as AgentTone[]).map((t) => (
                    <label
                      key={t}
                      className={clsx(
                        'flex items-center gap-2 px-4 py-2.5 rounded-lg border cursor-pointer transition-colors',
                        form.agent_tone === t
                          ? 'border-indigo-600 bg-indigo-50 text-indigo-700'
                          : 'border-gray-300 hover:border-indigo-300'
                      )}
                    >
                      <input
                        type="radio"
                        name="tone"
                        value={t}
                        checked={form.agent_tone === t}
                        onChange={() => update('agent_tone', t)}
                        className="sr-only"
                      />
                      {t.charAt(0).toUpperCase() + t.slice(1)}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="label">Company Name *</label>
                <input
                  type="text"
                  value={form.company_name || user?.company_name || ''}
                  onChange={(e) => update('company_name', e.target.value)}
                  className="input-field"
                  placeholder="Your company name"
                />
              </div>

              <div>
                <label className="label">Transfer Condition</label>
                <input
                  type="text"
                  value={form.transfer_condition}
                  onChange={(e) => update('transfer_condition', e.target.value)}
                  className="input-field"
                  placeholder="e.g. if customer asks for pricing or to speak to a human"
                />
                <p className="text-xs text-gray-500 mt-1">
                  When should the AI transfer the call to a human?
                </p>
              </div>
            </div>
          )}

          {/* Step 3 - Product/Script */}
          {step === 3 && (
            <div className="space-y-5">
              <h2 className="text-lg font-semibold text-gray-900">Product & Script</h2>

              <div>
                <label className="label">Product / Service Name *</label>
                <input
                  type="text"
                  value={form.product_name}
                  onChange={(e) => update('product_name', e.target.value)}
                  className="input-field"
                  placeholder="e.g. Solar Panel Installation"
                />
              </div>

              <div>
                <label className="label">Price</label>
                <input
                  type="text"
                  value={form.product_price}
                  onChange={(e) => update('product_price', e.target.value)}
                  className="input-field"
                  placeholder="e.g. ₹25,000 onwards"
                />
              </div>

              <div>
                <label className="label">Key Benefits</label>
                <div className="space-y-2">
                  {form.key_benefits.map((benefit, i) => (
                    <input
                      key={i}
                      type="text"
                      value={benefit}
                      onChange={(e) => updateBenefit(i, e.target.value)}
                      className="input-field"
                      placeholder={`Benefit ${i + 1} (e.g. Save 60% on electricity bills)`}
                    />
                  ))}
                </div>
              </div>

              <div>
                <label className="label">Campaign Goal</label>
                <select
                  value={form.goal}
                  onChange={(e) => update('goal', e.target.value as CampaignGoal)}
                  className="input-field"
                >
                  <option value="qualify_lead">Qualify Lead</option>
                  <option value="book_appointment">Book Appointment</option>
                  <option value="reminder">Reminder</option>
                  <option value="survey">Survey</option>
                </select>
              </div>
            </div>
          )}

          {/* Step 4 - Upload Numbers */}
          {step === 4 && (
            <div className="space-y-5">
              <h2 className="text-lg font-semibold text-gray-900">Upload Phone Numbers</h2>

              {/* CSV drop zone */}
              <div>
                <label className="label">Upload CSV File</label>
                <div
                  onDragOver={(e) => {
                    e.preventDefault()
                    setDragOver(true)
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={clsx(
                    'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
                    dragOver
                      ? 'border-indigo-500 bg-indigo-50'
                      : 'border-gray-300 hover:border-indigo-400 hover:bg-gray-50'
                  )}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.txt"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  <svg
                    className="w-10 h-10 text-gray-400 mx-auto mb-3"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                    />
                  </svg>
                  <p className="text-gray-600 font-medium">Drop CSV file here or click to browse</p>
                  <p className="text-gray-400 text-sm mt-1">
                    First column should contain phone numbers
                  </p>
                </div>
              </div>

              {/* Or paste */}
              <div>
                <label className="label">Or Paste Numbers</label>
                <textarea
                  value={pastedNumbers}
                  onChange={(e) => setPastedNumbers(e.target.value)}
                  className="input-field resize-none"
                  rows={4}
                  placeholder="Paste numbers separated by commas, newlines, or semicolons&#10;e.g. 9876543210, 9123456789&#10;or one per line"
                />
                <button
                  type="button"
                  onClick={handlePasteNumbers}
                  disabled={!pastedNumbers.trim()}
                  className="btn-secondary text-sm mt-2 disabled:opacity-50"
                >
                  Add Numbers
                </button>
              </div>

              {/* Preview */}
              {numbers.length > 0 && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm font-semibold text-gray-900">
                      {numbers.length} numbers ready to upload
                    </p>
                    <button
                      onClick={() => setNumbers([])}
                      className="text-xs text-red-600 hover:text-red-700"
                    >
                      Clear all
                    </button>
                  </div>
                  <div className="space-y-1">
                    {numbers.slice(0, 5).map((num, i) => (
                      <p key={i} className="text-sm text-gray-600 font-mono">
                        {num}
                      </p>
                    ))}
                    {numbers.length > 5 && (
                      <p className="text-sm text-gray-400">
                        ... and {numbers.length - 5} more
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Navigation buttons */}
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-gray-100">
            <div className="flex items-center gap-3">
              {step > 1 && (
                <button type="button" onClick={handleBack} className="btn-secondary">
                  Back
                </button>
              )}
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={saveAsDraft}
                disabled={saving}
                className="btn-secondary text-sm"
              >
                {saving ? 'Saving...' : 'Save Draft'}
              </button>

              {step < 4 ? (
                <button type="button" onClick={handleNext} className="btn-primary">
                  Next Step
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={uploading || numbers.length === 0}
                  className="btn-primary flex items-center gap-2"
                >
                  {uploading ? (
                    <>
                      <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        />
                      </svg>
                      Creating...
                    </>
                  ) : (
                    'Create Campaign'
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  )
}
