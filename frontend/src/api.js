const BASE = '/api/v1'

export function getToken() { return localStorage.getItem('py_token') || '' }
export function setToken(t) { t ? localStorage.setItem('py_token', t) : localStorage.removeItem('py_token') }

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  const t = getToken()
  if (t) headers['Authorization'] = `Bearer ${t}`
  let payload
  if (form) {
    payload = form
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(BASE + path, { method, headers, body: payload })
  if (res.status === 401 && !path.startsWith('/auth/login')) {
    setToken('')
    window.dispatchEvent(new Event('py:unauthorized'))
  }
  let data = null
  try { data = await res.json() } catch { data = null }
  if (!res.ok) {
    const err = new Error((data && data.detail) || `خطای ${res.status}`)
    err.status = res.status
    throw err
  }
  return data
}

export async function uploadFile(path, file) {
  const fd = new FormData()
  fd.append('file', file)
  return api(path, { method: 'POST', form: fd })
}

export const fmtDate = (iso) => {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleDateString('fa-IR', { year: 'numeric', month: 'long', day: 'numeric' }) }
  catch { return iso }
}
export const fmtDateTime = (iso) => {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString('fa-IR', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
  catch { return iso }
}

export const REQ_STATUS = {
  draft: 'پیش‌نویس', published: 'منتشرشده در استخر', offers_received: 'دریافت پیشنهاد',
  negotiating: 'در حال مذاکره', initial_agreement: 'توافق اولیه',
  pending_university_approval: 'در انتظار تأیید دانشگاه', connected_to_project: 'متصل به پروژه',
  cancelled: 'لغوشده', expired: 'منقضی‌شده', closed_no_agreement: 'بسته‌شده بدون توافق',
}
export const REQ_FLOW = ['draft', 'published', 'offers_received', 'negotiating', 'initial_agreement',
  'pending_university_approval', 'connected_to_project']
export const OFFER_STATUS = {
  sent: 'ارسال‌شده', viewed: 'دیده‌شده', in_dialogue: 'در گفت‌وگو', accepted: 'پذیرفته‌شده',
  converted_to_project: 'تبدیل‌شده به پروژه', rejected_by_student: 'ردشده',
  withdrawn: 'پس‌گرفته‌شده', superseded: 'جایگزین‌شده',
}
export const STATUS_BADGE = {
  draft: 'gray', published: 'teal', offers_received: 'amber', negotiating: 'amber',
  initial_agreement: 'teal', pending_university_approval: 'amber', connected_to_project: 'green',
  cancelled: 'red', expired: 'red', closed_no_agreement: 'red',
}
export const SCOPE_LABEL = { all: 'قابل مشاهده برای همه اساتید', faculty: 'فقط دانشکده مشخص', selected: 'فقط اساتید منتخب' }
