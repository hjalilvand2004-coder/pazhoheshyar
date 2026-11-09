import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { api } from '../api.js'

const DEMO_BANNER = (
  <div className="demo-banner">
    <b>⚠️ داده آزمایشی:</b> خروجی‌های این صفحه قاعده‌محور و نمایشی است؛ هوش مصنوعی فقط دستیار تصمیم است،
    باعث حذف خودکار هیچ کاربری نمی‌شود و هیچ احتمال ساختگی یا تضمین پذیرش ارائه نمی‌دهد.
  </div>
)

export default function AiAssistant() {
  const { user, hasRole } = useAuth()
  const [talent, setTalent] = useState(null)
  const [topics, setTopics] = useState(null)
  const [assist, setAssist] = useState(null)
  const [draft, setDraft] = useState({ title: '', problem: '', goals: '', skills: '' })
  const [grants, setGrants] = useState(null)
  const [journals, setJournals] = useState(null)
  const [predict, setPredict] = useState(null)
  const [monitor, setMonitor] = useState(null)
  const [projectId, setProjectId] = useState('')
  const [projects, setProjects] = useState([])

  useEffect(() => {
    api('/projects/mine').then(setProjects).catch(() => {})
  }, [])

  const run = {
    talent: () => api('/ai/talent-analysis').then(setTalent).catch(() => {}),
    topics: () => api('/ai/topic-suggestions', { method: 'POST', body: {} }).then(setTopics).catch(() => {}),
    assist: () => api('/ai/request-assistant', {
      method: 'POST',
      body: { ...draft, skills: draft.skills.split('،').map(s => s.trim()).filter(Boolean) },
    }).then(setAssist).catch(e => alert(e.message)),
    journals: () => api('/ai/journals').then(setJournals).catch(() => {}),
    grants: () => api('/ai/grants').then(setGrants).catch(() => {}),
    predict: () => api('/ai/predict-acceptance', { method: 'POST', body: {} }).then(setPredict).catch(() => {}),
    monitor: () => api(`/ai/progress-monitor/${projectId}`).then(setMonitor).catch(e => alert(e.message)),
  }

  return (
    <>
      <div className="card">
        <h3>🤖 دستیار هوشمند پژوهش</h3>
        {DEMO_BANNER}
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h3>۱) تحلیل استعداد پژوهشی</h3>
          <button className="btn small" onClick={run.talent}>اجرا</button>
          {talent && (
            <div style={{ marginTop: 10 }}>
              {talent.profile_completeness !== undefined && <div className="hint">کامل‌بودن پروفایل: {talent.profile_completeness}٪ — پروفایل کامل‌تر، پیشنهاد دقیق‌تر</div>}
              {talent.areas?.map((a, i) => <div key={i}>🔹 <b>{a.area}</b> — <span className="hint">{a.why}</span></div>)}
              {talent.message && <div className="hint">{talent.message}</div>}
            </div>
          )}
        </div>

        <div className="card">
          <h3>۲) پیشنهاد موضوع پایان‌نامه</h3>
          <button className="btn small" onClick={run.topics}>اجرا</button>
          {topics && (
            <ul style={{ margin: '10px 0 0', paddingRight: 18 }}>
              {topics.suggestions?.map((s, i) => <li key={i}>{s.title}<div className="hint">{s.based_on}</div></li>)}
            </ul>
          )}
        </div>

        <div className="card">
          <h3>۳) دستیار تدوین درخواست</h3>
          <input placeholder="عنوان پیشنهادی" value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} />
          <textarea rows={2} placeholder="شرح مسئله…" value={draft.problem} onChange={e => setDraft({ ...draft, problem: e.target.value })} style={{ marginTop: 6 }} />
          <textarea rows={2} placeholder="اهداف…" value={draft.goals} onChange={e => setDraft({ ...draft, goals: e.target.value })} style={{ marginTop: 6 }} />
          <input placeholder="مهارت‌ها (با ویرگول)" value={draft.skills} onChange={e => setDraft({ ...draft, skills: e.target.value })} style={{ marginTop: 6 }} />
          <button className="btn small" style={{ marginTop: 8 }} onClick={run.assist}>بازخورد بگیر</button>
          {assist && <ul style={{ margin: '10px 0 0', paddingRight: 18 }}>{assist.feedback?.map((f, i) => <li key={i}>{f}</li>)}</ul>}
        </div>

        <div className="card">
          <h3>۴) پایش پیشرفت پروژه</h3>
          <div className="row">
            <select value={projectId} onChange={e => setProjectId(e.target.value)}>
              <option value="">پروژه را انتخاب کنید…</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
            <button className="btn small" style={{ flex: 0 }} disabled={!projectId} onClick={run.monitor}>بررسی تأخیرها</button>
          </div>
          {monitor && (
            <div style={{ marginTop: 10 }}>
              <div className="hint">{monitor.message}</div>
              {monitor.actions?.map((a, i) => <div key={i}>⚠️ <b>{a.task}</b> — <span className="hint">{a.suggestion}</span></div>)}
            </div>
          )}
        </div>

        <div className="card">
          <h3>۵) پیشنهاد مجله و گرنت</h3>
          <div className="row">
            <button className="btn small secondary" onClick={run.journals}>مجلات (نمونه)</button>
            <button className="btn small secondary" onClick={run.grants}>گرنت‌ها (نمونه)</button>
            <button className="btn small ghost" onClick={run.predict}>برآورد پذیرش مقاله</button>
          </div>
          {journals && journals.journals?.map((j, i) => <div key={'j' + i} style={{ marginTop: 8 }}>📰 <b>{j.name}</b> — {j.field} | {j.index} <div className="hint">{j.note}</div></div>)}
          {grants && grants.grants?.map((g, i) => <div key={'g' + i} style={{ marginTop: 8 }}>💰 <b>{g.name}</b> — {g.field} <div className="hint">مهلت: {g.deadline}</div></div>)}
          {predict && <div className="demo-banner" style={{ marginTop: 10 }}>{predict.message}</div>}
        </div>
      </div>
    </>
  )
}
