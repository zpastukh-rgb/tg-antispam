<script setup>
import { ref, watch, nextTick, computed, onBeforeUnmount } from 'vue'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import {
  revokeBroadcastMediaPreviewUrl,
  uploadChatRulesPhoto,
  fetchChatRulesPhotoPreviewUrl,
  deleteChatRulesPhoto,
} from '../api/client'
import { normalizeHtmlForTelegram } from '../utils/telegramHtmlForTg'
import { useI18n } from 'vue-i18n'
import GuardTeleport from './GuardTeleport.vue'

const { t: tt, locale: i18nLocale } = useI18n()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** ID супергруппы обсуждения (куда шлётся API и куда уходят комментарии) */
  discussionChatId: { type: Number, default: 0 },
  /** ID канала-владельца, используется как ключ изоляции черновиков */
  channelId: { type: Number, default: 0 },
  /** Название канала (для заголовка) */
  channelTitle: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const { api, error, fetchSilent, hasInitData } = useApi()
const { showToast } = useToast()

const rulesChat = ref(null)
const loadError = ref(false)
const loadBusy = ref(false)

const form = ref({ enabled: false, text: '', deleteWindowSec: 0 })
const buttonRows = ref([[{ text: '', url: '', web_app_url: '', callback_data: '' }]])
const manualThreadId = ref('')
const busy = ref(false)
const saveBusy = ref(false)
const sendBusy = ref(false)
const previewUrl = ref('')
const photoUploadBusy = ref(false)
const bodyRef = ref(null)
const history = ref([])
const historyIndex = ref(-1)
const formatState = ref({ bold: false, italic: false, underline: false, strike: false })
const linkModalOpen = ref(false)
const linkUrl = ref('')
const linkRange = ref(null)
const savedRange = ref(null)
const showButtonsModal = ref(false)
const imagePreviewUrl = ref('')
const activePanel = ref('menu') // menu | rules
const channelDrafts = ref([])
const activeDraftId = ref('')
const editingDraftId = ref('')
const renameDraftId = ref('')
const renameDraftTitle = ref('')
const draftPhotoDataUrl = ref('')
const photoChangedInForm = ref(false)
const postRulesInfoOpen = ref(false)
const draftSaveBusy = ref(false)
const draftSyncBusy = ref(false)
const runDraftBusyId = ref('')
const localNotice = ref('')
const localNoticeTone = ref('info') // info | ok | err

let autoSaveTimer = null
let draftsSyncTimer = null
let deferredPhotoSaveTimer = null

const protToggleOff =
  'border border-white/12 bg-white/[0.06] text-zinc-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.07)] backdrop-blur-sm hover:border-white/18 hover:bg-white/[0.09]'

function boolToggleClass(on) {
  return on ? 'guard-green-soft' : protToggleOff
}

const inlineButtonCount = computed(() => {
  let n = 0
  for (const row of buttonRows.value || []) {
    for (const b of row || []) {
      if (String(b?.text || '').trim()) n += 1
    }
  }
  return n
})

function emptyBtn() {
  return { text: '', url: '', web_app_url: '', callback_data: '' }
}

function keyboardRowsFromRule(rows) {
  const fromApi = []
  for (const row of rows || []) {
    if (!Array.isArray(row) || !row.length) continue
    const line = row.map((b) => ({
      text: String(b?.text || ''),
      url: String(b?.url || ''),
      web_app_url: String(b?.web_app_url || ''),
      callback_data: String(b?.callback_data || ''),
    }))
    fromApi.push(line)
  }
  if (!fromApi.length) return [[emptyBtn()]]
  return fromApi
}

function buildKeyboardPayload(rowsRef) {
  const out = []
  for (const row of rowsRef.value || []) {
    const line = []
    for (const b of row || []) {
      const text = String(b.text || '').trim()
      if (!text) continue
      const url = String(b.url || '').trim()
      const wu = String(b.web_app_url || '').trim()
      const cb = String(b.callback_data || '').trim()
      if (url) line.push({ text, url })
      else if (wu) line.push({ text, web_app_url: wu })
      else if (cb) line.push({ text, callback_data: cb })
    }
    if (line.length) out.push(line)
  }
  return out.slice(0, 8)
}

function cloneButtons(rows) {
  return keyboardRowsFromRule(buildKeyboardPayload({ value: rows || [[emptyBtn()]] }))
}

function fingerprintRulesState(rowsRef, enabled, text, deleteWindowSec) {
  const delSec = Math.max(0, Math.min(600, Number(deleteWindowSec || 0)))
  return JSON.stringify({
    e: !!enabled,
    t: String(text || '').slice(0, 4000),
    d: delSec,
    b: buildKeyboardPayload(rowsRef),
  })
}

function fingerprintFromServerRule(rule) {
  if (!rule) return ''
  const fakeRef = { value: keyboardRowsFromRule(rule.rules_channel_buttons || []) }
  return fingerprintRulesState(
    fakeRef,
    rule.rules_channel_enabled,
    rule.rules_channel_text,
    rule.rules_channel_delete_window_sec,
  )
}

const isDirty = computed(() => {
  const r = rulesChat.value?.rule
  if (!r) return false
  return (
    fingerprintFromServerRule(r) !==
    fingerprintRulesState(buttonRows, form.value.enabled, form.value.text, form.value.deleteWindowSec)
  )
})

function clearAutoSaveTimer() {
  if (autoSaveTimer) {
    clearTimeout(autoSaveTimer)
    autoSaveTimer = null
  }
}
function clearDeferredPhotoSaveTimer() {
  if (deferredPhotoSaveTimer) {
    clearTimeout(deferredPhotoSaveTimer)
    deferredPhotoSaveTimer = null
  }
}
function scheduleDeferredPhotoSave() {
  clearDeferredPhotoSaveTimer()
  deferredPhotoSaveTimer = setTimeout(() => {
    deferredPhotoSaveTimer = null
    if (!props.modelValue || saveBusy.value || !photoChangedInForm.value) return
    void save({ silent: true })
  }, 250)
}
function scheduleAutoSave() {
  clearAutoSaveTimer()
  if (!props.modelValue || !rulesChat.value?.rule || loadBusy.value) return
  // Do not autosave server rules from non-active draft editor.
  if (activeDraftId.value && String(editingDraftId.value || '') !== String(activeDraftId.value || '')) return
  if (!isDirty.value) return
  autoSaveTimer = setTimeout(async () => {
    autoSaveTimer = null
    if (!props.modelValue || !rulesChat.value?.rule || !isDirty.value) return
    await save({ silent: true })
  }, 2500)
}

function clearDraftsSyncTimer() {
  if (draftsSyncTimer) {
    clearTimeout(draftsSyncTimer)
    draftsSyncTimer = null
  }
}

function setLocalNotice(message = '', tone = 'info') {
  localNotice.value = String(message || '')
  localNoticeTone.value = String(tone || 'info')
}

async function saveDraftsStorageNow() {
  const id = Number(props.channelId || props.discussionChatId || 0)
  if (!id) return
  const payload = (Array.isArray(channelDrafts.value) ? channelDrafts.value : []).slice(0, 20)
  draftSyncBusy.value = true
  try {
    const data = await fetchSilent(() => api.channelRuleDraftsSet(id, payload))
    const synced = Array.isArray(data?.drafts) ? data.drafts : null
    if (synced) {
      channelDrafts.value = synced.slice(0, 20)
      activeDraftId.value = String((synced.find((d) => d?.isActive)?.id) || '')
    }
  } finally {
    draftSyncBusy.value = false
  }
}

function saveDraftsStorage(immediate = false) {
  clearDraftsSyncTimer()
  if (immediate) {
    void saveDraftsStorageNow()
    return
  }
  draftsSyncTimer = setTimeout(() => {
    draftsSyncTimer = null
    void saveDraftsStorageNow()
  }, 250)
}

async function refreshRulesPanelData() {
  const discussionId = Number(props.discussionChatId || 0)
  const draftsScopeId = Number(props.channelId || props.discussionChatId || 0)
  if (!discussionId || !draftsScopeId || !rulesChat.value?.rule) return
  try {
    const [chatData, draftsData] = await Promise.all([
      fetchSilent(() => api.chat(discussionId)),
      fetchSilent(() => api.channelRuleDraftsGet(draftsScopeId)),
    ])
    if (chatData?.rule) {
      rulesChat.value = chatData
    }
    const drafts = Array.isArray(draftsData?.drafts) ? draftsData.drafts : []
    channelDrafts.value = drafts.slice(0, 20)
    activeDraftId.value = String((drafts.find((x) => x?.isActive)?.id) || '')
    const current = (channelDrafts.value || []).find((x) => String(x?.id || '') === String(editingDraftId.value || ''))
    const preferred = current || (channelDrafts.value || []).find((x) => String(x?.id || '') === String(activeDraftId.value || '')) || channelDrafts.value?.[0]
    if (preferred) {
      editingDraftId.value = String(preferred.id || '')
      applyDraftToForm(preferred)
    }
  } catch {
    //
  }
}

async function openRulesPanel() {
  activePanel.value = 'rules'
  await refreshRulesPanelData()
}

async function loadDraftsStorage() {
  const id = Number(props.channelId || props.discussionChatId || 0)
  if (!id) return []
  const data = await fetchSilent(() => api.channelRuleDraftsGet(id))
  const parsed = data?.drafts
  return Array.isArray(parsed) ? parsed : []
}

function draftTitleById(id) {
  const sid = String(id || '')
  return String(
    (channelDrafts.value || []).find((d) => String(d?.id || '') === sid)?.name || tt('channel_rules_modal.draft_default'),
  )
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => {
      const src = String(r.result || '')
      const img = new Image()
      img.onload = () => {
        const w = Number(img.naturalWidth || 0)
        const h = Number(img.naturalHeight || 0)
        if (!w || !h) return resolve(src)
        const maxSide = 1600
        const ratio = Math.min(1, maxSide / Math.max(w, h))
        const tw = Math.max(1, Math.round(w * ratio))
        const th = Math.max(1, Math.round(h * ratio))
        const canvas = document.createElement('canvas')
        canvas.width = tw
        canvas.height = th
        const ctx = canvas.getContext('2d')
        if (!ctx) return resolve(src)
        ctx.drawImage(img, 0, 0, tw, th)
        const out = canvas.toDataURL('image/jpeg', 0.82)
        resolve(String(out || src))
      }
      img.onerror = () => resolve(src)
      img.src = src
    }
    r.onerror = () => reject(new Error('file-read-failed'))
    r.readAsDataURL(file)
  })
}

function dataUrlToBlob(dataUrl) {
  return fetch(String(dataUrl || '')).then((r) => r.blob())
}

async function recompressDataUrl(dataUrl, maxSide = 1280, quality = 0.72) {
  const src = String(dataUrl || '')
  if (!src) return ''
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const w = Number(img.naturalWidth || 0)
      const h = Number(img.naturalHeight || 0)
      if (!w || !h) return resolve(src)
      const ratio = Math.min(1, maxSide / Math.max(w, h))
      const tw = Math.max(1, Math.round(w * ratio))
      const th = Math.max(1, Math.round(h * ratio))
      const canvas = document.createElement('canvas')
      canvas.width = tw
      canvas.height = th
      const ctx = canvas.getContext('2d')
      if (!ctx) return resolve(src)
      ctx.drawImage(img, 0, 0, tw, th)
      resolve(String(canvas.toDataURL('image/jpeg', quality) || src))
    }
    img.onerror = () => resolve(src)
    img.src = src
  })
}

function currentFormToDraft(name) {
  const nm = name != null ? String(name) : tt('channel_rules_modal.draft_default')
  return {
    id: `d-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: nm.slice(0, 48),
    enabled: !!form.value.enabled,
    text: String(form.value.text || '').slice(0, 4000),
    deleteWindowSec: Math.max(0, Math.min(600, Number(form.value.deleteWindowSec || 0))),
    buttons: buildKeyboardPayload(buttonRows),
    manualThreadId: String(manualThreadId.value || ''),
    photoDataUrl: String(draftPhotoDataUrl.value || ''),
    isActive: false,
    updatedAt: Date.now(),
  }
}

function applyDraftToForm(d) {
  if (!d) return
  form.value = {
    enabled: !!d.enabled,
    text: String(d.text || ''),
    deleteWindowSec: Math.max(0, Math.min(600, Number(d.deleteWindowSec || 0))),
  }
  buttonRows.value = keyboardRowsFromRule(d.buttons || [])
  manualThreadId.value = String(d.manualThreadId || '')
  draftPhotoDataUrl.value = String(d.photoDataUrl || '')
  previewUrl.value = draftPhotoDataUrl.value || ''
  photoChangedInForm.value = true
  editorLoadFromForm({ silent: true })
}

function upsertEditingDraftSnapshot() {
  const eid = String(editingDraftId.value || '')
  if (!eid) return
  channelDrafts.value = (channelDrafts.value || []).map((d) =>
    String(d?.id || '') === eid
      ? {
          ...currentFormToDraft(draftTitleById(eid)),
          id: eid,
          isActive: String(activeDraftId.value || '') === eid,
          name: String(d?.name || draftTitleById(eid) || tt('channel_rules_modal.draft_default')),
        }
      : d,
  )
}

async function saveCurrentAsDraft() {
  syncFormTextFromEditor()
  draftSaveBusy.value = true
  const eid = String(editingDraftId.value || '')
  if (eid) {
    channelDrafts.value = (channelDrafts.value || []).map((d) =>
      String(d?.id || '') === eid
        ? { ...currentFormToDraft(draftTitleById(eid)), id: eid, isActive: String(activeDraftId.value || '') === eid }
        : d,
    )
  } else {
    const base = currentFormToDraft(
      channelDrafts.value.length
        ? tt('channel_rules_modal.draft_numbered', { n: channelDrafts.value.length + 1 })
        : tt('channel_rules_modal.draft_numbered', { n: 1 }),
    )
    channelDrafts.value = [base, ...(channelDrafts.value || [])].slice(0, 20)
    editingDraftId.value = String(base.id)
  }
  try {
    await saveDraftsStorageNow()
    setLocalNotice(tt('channel_rules_modal.notice_draft_saved'), 'ok')
    showToast(tt('channel_rules_modal.notice_draft_saved'))
  } catch {
    setLocalNotice(error.value || tt('channel_rules_modal.err_draft_save'), 'err')
    showToast(error.value || tt('channel_rules_modal.err_draft_save'))
  } finally {
    draftSaveBusy.value = false
  }
}

function createDraft() {
  upsertEditingDraftSnapshot()
  const nextNum = (channelDrafts.value || []).length + 1
  const base = {
    id: `d-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: tt('channel_rules_modal.draft_numbered', { n: nextNum }),
    enabled: false,
    text: '',
    deleteWindowSec: 0,
    buttons: [],
    manualThreadId: '',
    photoDataUrl: '',
    isActive: false,
    updatedAt: Date.now(),
  }
  channelDrafts.value = [base, ...(channelDrafts.value || [])].slice(0, 20)
  editingDraftId.value = String(base.id)
  form.value = { enabled: false, text: '', deleteWindowSec: 0 }
  buttonRows.value = [[emptyBtn()]]
  manualThreadId.value = ''
  draftPhotoDataUrl.value = ''
  previewUrl.value = ''
  photoChangedInForm.value = true
  editorLoadFromForm({ silent: true })
  saveDraftsStorage()
}

function beginRenameDraft(d) {
  renameDraftId.value = String(d?.id || '')
  renameDraftTitle.value = String(d?.name || '')
  editingDraftId.value = String(d?.id || '')
}

function confirmRenameDraft(d) {
  const id = String(d?.id || '')
  if (!id) return
  const title = String(renameDraftTitle.value || '').trim().slice(0, 48) || tt('channel_rules_modal.draft_default')
  channelDrafts.value = (channelDrafts.value || []).map((x) => (String(x.id) === id ? { ...x, name: title, updatedAt: Date.now() } : x))
  renameDraftId.value = ''
  renameDraftTitle.value = ''
  saveDraftsStorage()
}

function editDraft(d) {
  upsertEditingDraftSnapshot()
  saveDraftsStorage()
  editingDraftId.value = String(d?.id || '')
  applyDraftToForm(d)
}

function deleteDraft(d) {
  const id = String(d?.id || '')
  if (!id) return
  const rest = (channelDrafts.value || []).filter((x) => String(x?.id || '') !== id)
  const wasEditing = String(editingDraftId.value || '') === id
  const wasActive = String(activeDraftId.value || '') === id
  channelDrafts.value = rest
  if (wasActive) {
    activeDraftId.value = ''
    form.value.enabled = false
  }
  if (wasEditing) {
    const next = rest[0] || null
    editingDraftId.value = String(next?.id || '')
    if (next) {
      applyDraftToForm(next)
    } else {
      form.value = { enabled: false, text: '', deleteWindowSec: 0 }
      buttonRows.value = [[emptyBtn()]]
      manualThreadId.value = ''
      draftPhotoDataUrl.value = ''
      previewUrl.value = ''
      editorLoadFromForm({ silent: true })
    }
  }
  saveDraftsStorage(true)
  setLocalNotice(tt('channel_rules_modal.notice_draft_deleted'), 'ok')
}

async function toggleRunDraft(d) {
  const id = String(d?.id || '')
  if (!id) return
  if (runDraftBusyId.value) return
  runDraftBusyId.value = id
  try {
    editingDraftId.value = id
    if (String(activeDraftId.value || '') === id) {
      form.value.enabled = false
      const ok = await save({ silent: false, skipPhoto: true, useCurrentForm: true })
      if (!ok) return
      activeDraftId.value = ''
      channelDrafts.value = (channelDrafts.value || []).map((x) => ({ ...x, isActive: false }))
      saveDraftsStorage(true)
      setLocalNotice(tt('channel_rules_modal.notice_run_off'), 'ok')
      if (photoChangedInForm.value) scheduleDeferredPhotoSave()
      return
    }
    applyDraftToForm(d)
    form.value.enabled = true
    const ok = await save({ silent: false, skipPhoto: true, useCurrentForm: true })
    if (!ok) return
    activeDraftId.value = id
    channelDrafts.value = (channelDrafts.value || []).map((x) => ({ ...x, isActive: String(x.id) === id }))
    saveDraftsStorage(true)
    setLocalNotice(tt('channel_rules_modal.notice_started', { title: draftTitleById(id) }), 'ok')
    if (photoChangedInForm.value) scheduleDeferredPhotoSave()
  } finally {
    runDraftBusyId.value = ''
  }
}

function addRow() {
  if (!Array.isArray(buttonRows.value)) buttonRows.value = []
  buttonRows.value.push([emptyBtn()])
  buttonRows.value = buttonRows.value.slice()
}

function addButton(ri) {
  if (!buttonRows.value[ri] || buttonRows.value[ri].length >= 6) return
  buttonRows.value[ri].push(emptyBtn())
  buttonRows.value = buttonRows.value.slice()
}

function removeButton(ri, bi) {
  if (!buttonRows.value[ri]) return
  buttonRows.value[ri].splice(bi, 1)
  if (!buttonRows.value[ri].length) buttonRows.value.splice(ri, 1)
  if (!buttonRows.value.length) buttonRows.value = [[emptyBtn()]]
  buttonRows.value = buttonRows.value.slice()
}

function editorTextGet() {
  return String(form.value.text || '')
}

function editorTextSet(v) {
  form.value.text = normalizeHtmlForTelegram(String(v || ''))
}

function editorLoadFromForm(opts = {}) {
  const silent = !!opts?.silent
  nextTick(() => {
    const el = bodyRef.value
    if (!el) return
    el.innerHTML = String(editorTextGet() || '')
    history.value = [String(el.innerHTML || '')]
    historyIndex.value = 0
    if (!silent) {
      /* noop */
    }
  })
}

function recordHistory(force = false) {
  const el = bodyRef.value
  if (!el) return
  const html = String(el.innerHTML || '')
  if (!force) {
    const cur = history.value[historyIndex.value]
    if (cur === html) return
  }
  if (historyIndex.value < history.value.length - 1) {
    history.value = history.value.slice(0, historyIndex.value + 1)
  }
  history.value.push(html)
  if (history.value.length > 120) history.value.shift()
  historyIndex.value = history.value.length - 1
}

function onBodyInput() {
  const el = bodyRef.value
  if (!el) return
  editorTextSet(String(el.innerHTML || ''))
  recordHistory()
}

function syncFormTextFromEditor() {
  const el = bodyRef.value
  if (!el) return
  editorTextSet(String(el.innerHTML || ''))
}

function canUndo() {
  return historyIndex.value > 0
}
function canRedo() {
  return historyIndex.value >= 0 && historyIndex.value < history.value.length - 1
}
function undo() {
  if (!canUndo()) return
  historyIndex.value -= 1
  const el = bodyRef.value
  if (!el) return
  el.innerHTML = String(history.value[historyIndex.value] || '')
  editorTextSet(el.innerHTML)
}
function redo() {
  if (!canRedo()) return
  historyIndex.value += 1
  const el = bodyRef.value
  if (!el) return
  el.innerHTML = String(history.value[historyIndex.value] || '')
  editorTextSet(el.innerHTML)
}
function exec(cmd) {
  const el = bodyRef.value
  if (!el) return
  el.focus()
  document.execCommand(cmd, false)
  onBodyInput()
  updateFormatState()
}
function updateFormatState() {
  const sel = window.getSelection?.()
  if (sel && sel.rangeCount) {
    const r = sel.getRangeAt(0)
    const el = bodyRef.value
    if (el && (el.contains(r.startContainer) || el.contains(r.endContainer))) {
      savedRange.value = r.cloneRange()
    }
  }
  formatState.value = {
    bold: !!document.queryCommandState('bold'),
    italic: !!document.queryCommandState('italic'),
    underline: !!document.queryCommandState('underline'),
    strike: !!document.queryCommandState('strikeThrough'),
  }
}
function formatLink() {
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : savedRange.value
  const selectedText = String(range?.toString() || '').trim()
  if (!selectedText) {
    showToast(tt('channel_rules_modal.toast_select_link_text'))
    return
  }
  linkRange.value = range || null
  linkUrl.value = ''
  linkModalOpen.value = true
}
function applyLinkModal() {
  const url = String(linkUrl.value || '').trim()
  if (!url) return
  const el = bodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const range = linkRange.value || savedRange.value || (sel && sel.rangeCount ? sel.getRangeAt(0) : null)
  if (!range) {
    showToast(tt('channel_rules_modal.toast_select_link_text'))
    return
  }
  const text = String(range.toString() || '').trim()
  if (!text) {
    showToast(tt('channel_rules_modal.toast_select_link_text'))
    return
  }
  const safeText = text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  const safeUrl = url.replaceAll('"', '&quot;')
  range.deleteContents()
  const tmp = document.createElement('div')
  tmp.innerHTML = `<a href="${safeUrl}">${safeText}</a>`
  const node = tmp.firstChild
  if (node) {
    range.insertNode(node)
    range.setStartAfter(node)
    range.collapse(true)
    sel?.removeAllRanges()
    sel?.addRange(range)
    savedRange.value = range.cloneRange()
  }
  onBodyInput()
  linkModalOpen.value = false
  linkRange.value = null
}
function clearFormatting() {
  const el = bodyRef.value
  if (!el) return
  el.focus()
  document.execCommand('removeFormat', false)
  onBodyInput()
}

async function loadPhotoPreview() {
  const id = Number(props.discussionChatId || 0)
  if (!id) return
  try {
    const url = await fetchChatRulesPhotoPreviewUrl(id, 'channel')
    if (previewUrl.value) revokeBroadcastMediaPreviewUrl(previewUrl.value)
    previewUrl.value = url
  } catch {
    if (previewUrl.value) revokeBroadcastMediaPreviewUrl(previewUrl.value)
    previewUrl.value = ''
  }
}

async function loadDiscussionChat() {
  const id = Number(props.discussionChatId || 0)
  if (!id || !hasInitData.value) return
  loadBusy.value = true
  loadError.value = false
  rulesChat.value = null
  try {
    const data = await fetchSilent(() => api.chat(id))
    if (!data?.rule) {
      loadError.value = true
      return
    }
    rulesChat.value = data
    form.value = {
      enabled: !!data.rule.rules_channel_enabled,
      text: String(data.rule.rules_channel_text || ''),
      deleteWindowSec: Number(data.rule.rules_channel_delete_window_sec || 0),
    }
    buttonRows.value = keyboardRowsFromRule(data.rule.rules_channel_buttons || [])
    manualThreadId.value = ''
    editorLoadFromForm({ silent: true })
    const [stored] = await Promise.all([loadDraftsStorage(), loadPhotoPreview()])
    channelDrafts.value = stored.slice(0, 20)
    activeDraftId.value = String((stored.find((d) => d?.isActive)?.id) || '')
    draftPhotoDataUrl.value = ''
    photoChangedInForm.value = false
    const initialDraft = (channelDrafts.value || []).find((d) => String(d?.id || '') === String(activeDraftId.value || '')) || channelDrafts.value?.[0]
    editingDraftId.value = String(initialDraft?.id || '')
    if (initialDraft) applyDraftToForm(initialDraft)
  } catch {
    loadError.value = true
  } finally {
    loadBusy.value = false
  }
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!document?.body?.style) return
    document.body.style.overflow = open ? 'hidden' : ''
    if (open) {
      activePanel.value = 'menu'
      postRulesInfoOpen.value = false
      setLocalNotice('', 'info')
      await loadDiscussionChat()
      await nextTick()
    } else {
      clearAutoSaveTimer()
      clearDraftsSyncTimer()
      rulesChat.value = null
      loadError.value = false
      showButtonsModal.value = false
      linkModalOpen.value = false
      imagePreviewUrl.value = ''
      activePanel.value = 'menu'
      channelDrafts.value = []
      activeDraftId.value = ''
      editingDraftId.value = ''
      renameDraftId.value = ''
      renameDraftTitle.value = ''
      postRulesInfoOpen.value = false
      setLocalNotice('', 'info')
      draftPhotoDataUrl.value = ''
      photoChangedInForm.value = false
      if (previewUrl.value) revokeBroadcastMediaPreviewUrl(previewUrl.value)
      previewUrl.value = ''
    }
  },
)

function close() {
  emit('update:modelValue', false)
}

async function onPhotoPicked(event) {
  const f = event?.target?.files?.[0]
  event.target.value = ''
  if (!f) return
  photoUploadBusy.value = true
  try {
    const dataUrl = await fileToDataUrl(f)
    draftPhotoDataUrl.value = dataUrl
    previewUrl.value = dataUrl
    photoChangedInForm.value = true
    upsertEditingDraftSnapshot()
    saveDraftsStorage()
    showToast(tt('channel_rules_modal.toast_photo_added'))
  } catch {
    showToast(error.value || tt('channel_rules_modal.toast_photo_read_fail'))
  } finally {
    photoUploadBusy.value = false
  }
}

function removePhoto() {
  if (previewUrl.value && String(previewUrl.value).startsWith('blob:')) {
    revokeBroadcastMediaPreviewUrl(previewUrl.value)
  }
  previewUrl.value = ''
  draftPhotoDataUrl.value = ''
  photoChangedInForm.value = true
  upsertEditingDraftSnapshot()
  saveDraftsStorage()
  showToast(tt('channel_rules_modal.toast_photo_removed'))
}

async function save(opts = {}) {
  const useCurrentForm = !!opts.useCurrentForm
  if (!useCurrentForm) syncFormTextFromEditor()
  const silent = !!opts.silent
  const skipPhoto = !!opts.skipPhoto
  clearAutoSaveTimer()
  const id = Number(props.discussionChatId || 0)
  if (!id || !rulesChat.value?.rule) return false
  saveBusy.value = true
  try {
    const buttons = buildKeyboardPayload(buttonRows)
    const delSec = Math.max(0, Math.min(600, Number(form.value.deleteWindowSec || 0)))
    const data = await fetchSilent(() =>
      api.updateRule(id, {
        rules_channel_enabled: !!form.value.enabled,
        rules_channel_text: String(form.value.text || '').slice(0, 4000),
        rules_channel_buttons: buttons,
        rules_channel_delete_window_sec: delSec,
        rules_channel_autopost_enabled: false,
        rules_channel_autopost_times: [],
      }),
    )
    const photoDataUrl = String(draftPhotoDataUrl.value || '')
    if (!skipPhoto && photoChangedInForm.value) {
      try {
        if (photoDataUrl) {
          try {
            const photoBlob = await dataUrlToBlob(photoDataUrl)
            const photoFile = new File([photoBlob], 'rules-photo.jpg', { type: photoBlob.type || 'image/jpeg' })
            await uploadChatRulesPhoto(id, 'channel', photoFile)
          } catch {
            // fallback: stronger recompress and retry once
            const compact = await recompressDataUrl(photoDataUrl, 1024, 0.66)
            const compactBlob = await dataUrlToBlob(compact)
            const compactFile = new File([compactBlob], 'rules-photo-compact.jpg', { type: compactBlob.type || 'image/jpeg' })
            await uploadChatRulesPhoto(id, 'channel', compactFile)
            draftPhotoDataUrl.value = String(compact || photoDataUrl)
          }
        } else {
          try {
            await fetchSilent(() => deleteChatRulesPhoto(id, 'channel'))
          } catch {
            // no photo on backend is not a save blocker
          }
        }
        await loadPhotoPreview()
        if (photoDataUrl) draftPhotoDataUrl.value = photoDataUrl
        photoChangedInForm.value = false
      } catch {
        setLocalNotice(tt('channel_rules_modal.notice_saved_partial_photo'), 'err')
      }
    }
    rulesChat.value.rule = data.rule
    if (!silent) {
      setLocalNotice(tt('channel_rules_modal.notice_rules_saved'), 'ok')
      showToast(tt('channel_rules_modal.notice_rules_saved'))
    }
    return true
  } catch {
    setLocalNotice(error.value || tt('channel_rules_modal.err_save'), 'err')
    showToast(error.value || tt('channel_rules_modal.err_save'))
    return false
  } finally {
    saveBusy.value = false
  }
}

async function sendNow() {
  syncFormTextFromEditor()
  const id = Number(props.discussionChatId || 0)
  if (!id) return
  upsertEditingDraftSnapshot()
  await saveDraftsStorageNow()
  await refreshRulesPanelData()
  const threadId = Number(manualThreadId.value || 0)
  if (!Number.isFinite(threadId) || threadId <= 0) {
    showToast(tt('channel_rules_modal.toast_thread_id'))
    return
  }
  if (isDirty.value) {
    const ok = await save({ silent: true })
    if (!ok) return
  }
  sendBusy.value = true
  try {
    await fetchSilent(() =>
      api.sendChatRulesNow(id, {
        target: 'channel_comments',
        message_thread_id: Math.floor(threadId),
      }),
    )
    showToast(tt('channel_rules_modal.toast_sent_comments'))
  } catch {
    showToast(error.value || tt('channel_rules_modal.err_send_comments'))
  } finally {
    sendBusy.value = false
  }
}

async function saveButtonsFromModal() {
  upsertEditingDraftSnapshot()
  saveDraftsStorage()
  await save()
}

const discussionTitle = computed(() => String(rulesChat.value?.title || '').trim() || `ID ${props.discussionChatId}`)
const draftStatusLabel = computed(() => {
  void i18nLocale.value
  return isDirty.value ? tt('channel_rules_modal.status_draft_dirty') : tt('channel_rules_modal.status_draft_clean')
})
const editingDraftLabel = computed(() => {
  void i18nLocale.value
  const suf = isDirty.value
    ? tt('channel_rules_modal.status_editing_suffix_dirty')
    : tt('channel_rules_modal.status_editing_suffix_clean')
  return `${draftTitleById(editingDraftId.value)} · ${suf}`
})

watch(
  () => [
    props.modelValue,
    form.value.enabled,
    form.value.text,
    form.value.deleteWindowSec,
    buttonRows.value,
  ],
  () => {
    if (props.modelValue) scheduleAutoSave()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  clearAutoSaveTimer()
  clearDraftsSyncTimer()
  clearDeferredPhotoSaveTimer()
})
</script>

<template>
  <GuardTeleport>
    <div
      v-if="modelValue"
      class="fixed inset-0 z-[340] flex items-center justify-center bg-black/55 p-3 sm:p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      @click.self="close"
    >
      <div
        class="flex max-h-[min(90vh,48rem)] w-full max-w-3xl flex-col overflow-hidden rounded-[1.35rem] border border-white/12 bg-zinc-950/76 p-0 text-zinc-100 shadow-[0_34px_90px_-28px_rgba(0,0,0,0.78),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl backdrop-saturate-150"
        @click.stop
      >
        <div class="flex items-center justify-between border-b border-white/6 bg-gradient-to-r from-white/[0.04] to-transparent px-4 py-3">
          <div>
            <div class="flex items-center gap-2">
              <h3 class="text-sm font-semibold text-white">{{ tt('channel_rules_modal.header') }}</h3>
              <span
                v-if="rulesChat && !loadBusy && activePanel === 'rules'"
                class="inline-flex h-2.5 w-2.5 rounded-full"
                :class="isDirty ? 'bg-rose-400' : 'bg-emerald-400'"
                :title="draftStatusLabel"
              />
            </div>
            <p v-if="rulesChat && !loadBusy && activePanel === 'rules'" class="text-[10px]" :class="isDirty ? 'text-rose-300' : 'text-emerald-300'">{{ editingDraftLabel }}</p>
          </div>
          <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10" @click="close">✕</button>
        </div>
        <div v-if="rulesChat && !loadBusy && activePanel === 'rules'" class="space-y-2 px-4 pt-2">
          <div class="flex items-center justify-between gap-2">
            <button type="button" class="whitespace-nowrap rounded-lg border border-white/15 bg-white/10 px-2 py-1 text-[11px] text-slate-200 hover:bg-white/15" @click="activePanel = 'menu'">{{ tt('protection.ui.channel_rules_back_menu') }}</button>
            <div class="flex items-center gap-1.5">
              <button type="button" class="inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-cyan-400/35 bg-cyan-950/30 px-1 text-[10px] font-extrabold text-cyan-200" :aria-label="tt('protection.ui.info_group_rules_telegram_aria')" @click="postRulesInfoOpen = !postRulesInfoOpen">i</button>
              <button
                type="button"
                :class="boolToggleClass(!!form.enabled)"
                class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium"
                @click="form.enabled = !form.enabled"
              >
                {{ form.enabled ? tt('protection.ui.on_short') : tt('protection.ui.off_short') }}
              </button>
            </div>
          </div>
          <div v-if="postRulesInfoOpen" class="rounded-lg border border-cyan-400/20 bg-cyan-950/20 px-2.5 py-2 text-[11px] text-cyan-100">
            <p class="mb-1 font-semibold text-cyan-50">{{ tt('protection.ui.channel_rules_help_title') }}</p>
            <p>{{ tt('protection.ui.channel_rules_help_1') }}</p>
            <p>{{ tt('protection.ui.channel_rules_help_2') }}</p>
            <p>{{ tt('protection.ui.channel_rules_help_3') }}</p>
            <p>{{ tt('protection.ui.channel_rules_help_4') }}</p>
            <p>{{ tt('protection.ui.channel_rules_help_5') }}</p>
            <p>{{ tt('protection.ui.channel_rules_help_6') }}</p>
          </div>
          <div
            v-if="localNotice"
            class="rounded-lg px-2.5 py-2 text-[11px]"
            :class="localNoticeTone === 'err' ? 'border border-rose-400/25 bg-rose-950/25 text-rose-200' : (localNoticeTone === 'ok' ? 'border border-emerald-400/25 bg-emerald-950/25 text-emerald-200' : 'border border-white/15 bg-white/8 text-slate-200')"
          >
            {{ localNotice }}
          </div>
        </div>

        <div class="min-h-[min(36vh,13rem)] max-h-[min(76vh,44rem)] flex-1 space-y-3 overflow-y-auto px-3 py-3 sm:px-4">
          <div v-if="loadBusy" class="py-8 text-center text-sm text-slate-400">{{ tt('protection.ui.channel_rules_loading') }}</div>
          <div v-else-if="loadError || !rulesChat" class="py-6 text-center text-sm text-rose-300">
            {{ tt('protection.ui.channel_rules_load_error') }}
          </div>
          <template v-else>
            <template v-if="activePanel === 'menu'">
              <div class="glass-panel p-2.5 sm:p-3">
                <div class="grid gap-2">
                  <button
                    type="button"
                    class="flex items-center justify-between rounded-xl border border-white/12 bg-white/[0.03] px-3 py-2.5 text-left hover:border-cyan-300/25 hover:bg-white/[0.06]"
                    @click="openRulesPanel"
                  >
                    <span>
                      <span class="block text-sm font-semibold text-slate-100">{{ tt('channel_rules_modal.menu_row_title') }}</span>
                    </span>
                    <span class="text-slate-300">→</span>
                  </button>
                </div>
              </div>
            </template>
            <template v-else>
            <div class="glass-panel p-3">
              <div class="mb-2 flex items-center justify-between">
                <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{{ tt('channel_rules_modal.drafts_heading') }}</p>
                <button type="button" class="rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-2 py-1 text-[11px] font-semibold text-emerald-100 hover:bg-emerald-500/25" @click="createDraft">{{ tt('channel_rules_modal.create_draft') }}</button>
              </div>
              <p v-if="editingDraftId" class="mb-2 text-[11px] text-cyan-200">{{ tt('channel_rules_modal.editing_now', { name: draftTitleById(editingDraftId) }) }}</p>
              <p v-if="draftSyncBusy" class="mb-2 text-[10px] text-slate-400">{{ tt('channel_rules_modal.sync_busy') }}</p>
              <div class="space-y-1.5">
                <div
                  v-for="d in channelDrafts"
                  :key="`dr-${d.id}`"
                  class="flex flex-wrap items-center gap-1.5 rounded-lg border px-2 py-1.5"
                  :class="String(editingDraftId || '') === String(d.id) ? 'border-cyan-400/45 bg-cyan-500/12' : 'border-white/10 bg-white/[0.04]'"
                >
                  <span class="inline-flex h-2 w-2 rounded-full" :class="String(activeDraftId || '') === String(d.id) ? 'bg-emerald-400' : 'bg-rose-400'" />
                  <template v-if="String(renameDraftId || '') === String(d.id)">
                    <input v-model.trim="renameDraftTitle" type="text" class="min-w-[8rem] flex-1 rounded border border-white/15 bg-white/[0.06] px-2 py-1 text-[11px]" />
                    <button type="button" class="rounded border border-emerald-400/35 bg-emerald-500/20 px-1.5 py-0.5 text-[10px] text-emerald-100" @click="confirmRenameDraft(d)">✓</button>
                  </template>
                  <template v-else>
                    <span class="min-w-[8rem] flex-1 truncate text-[11px] text-slate-100">{{ d.name || tt('channel_rules_modal.draft_default') }}</span>
                    <button type="button" class="rounded border border-white/20 bg-white/[0.08] px-1.5 py-0.5 text-[10px] text-slate-200" :title="tt('channel_rules_modal.rename_title')" @click="beginRenameDraft(d)">✍️</button>
                  </template>
                  <button
                    type="button"
                    class="rounded border px-1.5 py-0.5 text-[10px]"
                    :class="String(editingDraftId || '') === String(d.id) ? 'border-cyan-300/60 bg-cyan-400/30 text-cyan-50 shadow-[0_0_18px_rgba(34,211,238,0.25)]' : 'border-cyan-400/35 bg-cyan-500/20 text-cyan-100'"
                    @click="editDraft(d)"
                  >
                    {{ tt('channel_rules_modal.btn_edit') }}
                  </button>
                  <button
                    type="button"
                    class="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                    :disabled="!!runDraftBusyId"
                    :class="String(activeDraftId || '') === String(d.id) ? 'border border-rose-400/35 bg-rose-500/20 text-rose-100' : 'border border-emerald-400/35 bg-emerald-500/20 text-emerald-100'"
                    @click="toggleRunDraft(d)"
                  >
                    {{ String(runDraftBusyId || '') === String(d.id) ? tt('channel_rules_modal.btn_busy') : (String(activeDraftId || '') === String(d.id) ? tt('channel_rules_modal.btn_stop') : tt('channel_rules_modal.btn_run')) }}
                  </button>
                  <button
                    type="button"
                    class="rounded border border-rose-400/25 bg-rose-500/15 px-1 py-0.5 text-[10px] text-rose-100 hover:bg-rose-500/25"
                    :title="tt('channel_rules_modal.delete_draft_title')"
                    @click="deleteDraft(d)"
                  >
                    🗑
                  </button>
                </div>
                <p v-if="!channelDrafts.length" class="text-[11px] text-slate-500">{{ tt('channel_rules_modal.drafts_empty') }}</p>
              </div>
            </div>
            <div class="glass-panel p-3">
              <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{{ tt('channel_rules_modal.rules_text_heading') }}</p>
              <div class="mb-1.5 flex flex-wrap gap-1.5">
                <button type="button" class="post-rules-tool-btn font-semibold" :class="formatState.bold ? 'border-cyan-400/50 bg-cyan-500/15' : ''" @mousedown.prevent @click="exec('bold')">{{ tt('channel_rules_modal.fmt_bold') }}</button>
                <button type="button" class="post-rules-tool-btn italic" :class="formatState.italic ? 'border-cyan-400/50 bg-cyan-500/15' : ''" @mousedown.prevent @click="exec('italic')">{{ tt('channel_rules_modal.fmt_italic') }}</button>
                <button type="button" class="post-rules-tool-btn underline" :class="formatState.underline ? 'border-cyan-400/50 bg-cyan-500/15' : ''" @mousedown.prevent @click="exec('underline')">{{ tt('channel_rules_modal.fmt_underline') }}</button>
                <button type="button" class="post-rules-tool-btn line-through" :class="formatState.strike ? 'border-cyan-400/50 bg-cyan-500/15' : ''" @mousedown.prevent @click="exec('strikeThrough')">{{ tt('channel_rules_modal.fmt_strike') }}</button>
                <button type="button" class="post-rules-tool-btn" @mousedown.prevent @click="formatLink">{{ tt('channel_rules_modal.link_btn') }}</button>
                <button type="button" class="post-rules-tool-btn" @mousedown.prevent @click="clearFormatting">{{ tt('channel_rules_modal.clear_fmt') }}</button>
              </div>
              <div class="mb-1.5 flex flex-wrap gap-1.5">
                <button type="button" class="post-rules-tool-btn px-2.5 text-zinc-200" :class="!canUndo() ? 'opacity-40' : ''" :disabled="!canUndo()" @mousedown.prevent @click="undo">{{ tt('channel_rules_modal.undo') }}</button>
                <button type="button" class="post-rules-tool-btn px-2.5 text-zinc-200" :class="!canRedo() ? 'opacity-40' : ''" :disabled="!canRedo()" @mousedown.prevent @click="redo">{{ tt('channel_rules_modal.redo') }}</button>
                <label class="post-rules-tool-btn cursor-pointer">
                  {{ photoUploadBusy ? tt('channel_rules_modal.photo_uploading') : tt('channel_rules_modal.file_btn') }}
                  <input type="file" accept="image/*" class="hidden" :disabled="busy || photoUploadBusy" @change="onPhotoPicked" />
                </label>
                <button type="button" class="post-rules-tool-btn" :disabled="busy || photoUploadBusy || !previewUrl" @click="removePhoto">🗑</button>
                <span v-if="photoUploadBusy" class="text-[10px] text-cyan-300">{{ tt('channel_rules_modal.photo_processing') }}</span>
                <button v-if="previewUrl" type="button" class="h-8 w-8 overflow-hidden rounded-lg border border-white/12 bg-black/40" @click="imagePreviewUrl = previewUrl">
                  <img :src="previewUrl" alt="" class="h-full w-full object-cover" />
                </button>
                <div class="flex items-center gap-1">
                  <button type="button" class="post-rules-tool-btn" @click="showButtonsModal = true">{{ tt('channel_rules_modal.buttons_btn') }}</button>
                  <span v-if="inlineButtonCount > 0" class="rounded-md border border-cyan-400/25 bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-bold text-cyan-100">{{ inlineButtonCount }}</span>
                </div>
              </div>
              <div
                ref="bodyRef"
                contenteditable="true"
                class="post-rules-rich-editor max-h-56 min-h-[8rem] w-full overflow-y-auto rounded-xl border border-white/12 bg-slate-950/90 px-3 py-2 text-sm leading-relaxed text-slate-100 focus-within:border-cyan-400/50 focus-within:ring-1 focus-within:ring-cyan-500/30"
                :data-placeholder="tt('channel_rules_modal.editor_placeholder')"
                @input="onBodyInput"
                @mouseup="updateFormatState"
                @keyup="updateFormatState"
              />
              <div class="mt-2">
                <button type="button" class="rounded-lg border border-violet-400/45 bg-violet-500/20 px-2 py-1 text-[11px] font-semibold text-violet-100 hover:bg-violet-500/30 disabled:opacity-60" :disabled="draftSaveBusy" @click="saveCurrentAsDraft">
                  {{ draftSaveBusy ? tt('channel_rules_modal.save_draft_busy') : tt('channel_rules_modal.save_draft') }}
                </button>
              </div>
            </div>
            <div class="glass-panel p-3">
              <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{{ tt('channel_rules_modal.delete_window_heading') }}</p>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="sec in [0, 10, 30, 60, 180]"
                  :key="`ch-del-${sec}`"
                  type="button"
                  class="rounded-lg px-2 py-1 text-[11px] font-semibold"
                  :class="Number(form.deleteWindowSec || 0) === sec ? 'guard-green-soft text-slate-900' : protToggleOff"
                  @click="form.deleteWindowSec = sec"
                >
                  {{ sec === 0 ? tt('channel_rules_modal.delete_window_none') : tt('channel_rules_modal.delete_window_sec', { n: sec }) }}
                </button>
              </div>
            </div>
            <div class="glass-panel p-3">
              <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{{ tt('channel_rules_modal.manual_thread_heading') }}</p>
              <input
                v-model.trim="manualThreadId"
                type="text"
                inputmode="numeric"
                class="w-full rounded-lg border border-white/14 bg-white/[0.06] px-2 py-1 text-xs"
                :placeholder="tt('channel_rules_modal.manual_thread_ph')"
              />
            </div>
            </template>
          </template>
        </div>

        <div class="post-rules-footer flex flex-col gap-1 border-t border-white/10 px-3 py-2 sm:px-4">
          <p v-if="rulesChat && !loadBusy && activePanel === 'rules'" class="text-[10px] text-slate-500">
            {{ tt('channel_rules_modal.footer_autosave_hint') }}
          </p>
          <div class="flex flex-wrap items-center justify-end gap-2">
          <button type="button" class="post-rules-action-btn post-rules-action-btn--cancel" @click="close">{{ tt('channel_rules_modal.close') }}</button>
          <button
            v-if="activePanel === 'rules'"
            type="button"
            class="post-rules-action-btn border border-cyan-400/40 bg-cyan-500/25 text-cyan-50 hover:bg-cyan-500/35"
            :disabled="sendBusy || saveBusy || !rulesChat || !String(manualThreadId || '').trim()"
            @click="sendNow()"
          >
            {{ sendBusy ? tt('channel_rules_modal.send_busy') : tt('channel_rules_modal.send_to_comments') }}
          </button>
          <button v-if="activePanel === 'rules'" type="button" class="post-rules-action-btn post-rules-action-btn--save" :disabled="saveBusy || !rulesChat" @click="save()">
            {{ saveBusy ? tt('channel_rules_modal.save_busy') : tt('channel_rules_modal.save') }}
          </button>
          </div>
        </div>
      </div>
    </div>
  </GuardTeleport>

  <GuardTeleport>
    <div
      v-if="showButtonsModal && modelValue && rulesChat"
      class="fixed inset-0 z-[345] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      @click.self="showButtonsModal = false"
    >
      <div class="w-full max-w-2xl overflow-hidden rounded-[1.25rem] border border-white/15 bg-zinc-950/90 text-zinc-100 shadow-2xl backdrop-blur-xl ring-1 ring-white/10" @click.stop>
        <div class="flex items-center justify-between border-b border-white/10 bg-gradient-to-r from-white/[0.06] to-transparent px-4 py-2.5">
          <h4 class="text-sm font-semibold text-white">{{ tt('channel_rules_modal.post_buttons_title') }}</h4>
          <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="showButtonsModal = false">✕</button>
        </div>
        <div class="max-h-[70vh] overflow-y-auto px-4 py-3">
          <div v-for="(row, ri) in buttonRows" :key="`chb-row-${ri}`" class="mb-3 rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <p class="mb-2 text-xs font-semibold text-slate-200">{{ tt('channel_rules_modal.row_n', { n: ri + 1 }) }}</p>
            <div
              v-for="(btn, bi) in row"
              :key="`chb-btn-${ri}-${bi}`"
              class="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]"
            >
              <input v-model="btn.text" type="text" class="rounded-lg border border-white/14 bg-white/[0.06] px-2.5 py-1.5 text-xs" :placeholder="tt('channel_rules_modal.btn_text_ph')" />
              <input v-model="btn.url" type="text" class="rounded-lg border border-white/14 bg-white/[0.06] px-2.5 py-1.5 text-xs" placeholder="https://..." />
              <button type="button" class="rounded-lg border border-rose-400/35 bg-rose-500/20 px-2.5 py-1.5 text-xs text-rose-100" @click="removeButton(ri, bi)">{{ tt('channel_rules_modal.remove') }}</button>
              <button
                type="button"
                class="rounded-lg border border-emerald-400/35 bg-emerald-500/20 px-2.5 py-1.5 text-xs font-semibold text-emerald-100"
                :disabled="saveBusy"
                @click="saveButtonsFromModal()"
              >
                {{ tt('channel_rules_modal.save') }}
              </button>
            </div>
            <button type="button" class="text-xs font-semibold text-violet-300" @click="addButton(ri)">{{ tt('channel_rules_modal.add_btn_row') }}</button>
          </div>
          <button type="button" class="w-full rounded-lg border border-violet-500/40 py-2 text-sm font-semibold text-violet-200" @click="addRow">{{ tt('channel_rules_modal.add_row') }}</button>
        </div>
        <div class="flex items-center justify-end gap-2 border-t border-white/10 px-4 py-3">
          <button type="button" class="rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-white/15" @click="showButtonsModal = false">{{ tt('channel_rules_modal.close') }}</button>
          <button type="button" class="guard-green-soft rounded-lg px-3 py-2 text-xs font-semibold text-slate-900 disabled:opacity-50" :disabled="saveBusy" @click="saveButtonsFromModal()">
            {{ saveBusy ? tt('channel_rules_modal.save_busy') : tt('channel_rules_modal.save_buttons') }}
          </button>
        </div>
      </div>
    </div>
  </GuardTeleport>

  <GuardTeleport>
    <div
      v-if="linkModalOpen && modelValue"
      class="fixed inset-0 z-[345] flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      @click.self="linkModalOpen = false"
    >
      <div class="w-full max-w-md overflow-hidden rounded-[1.1rem] border border-white/15 bg-zinc-950/90 text-zinc-100 shadow-2xl backdrop-blur-xl ring-1 ring-white/10" @click.stop>
        <div class="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
          <h4 class="text-sm font-semibold text-white">{{ tt('channel_rules_modal.link_title') }}</h4>
          <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="linkModalOpen = false">✕</button>
        </div>
        <div class="space-y-2 px-4 py-3">
          <input v-model.trim="linkUrl" type="text" class="w-full rounded-lg border border-white/15 bg-white/[0.06] px-3 py-2 text-sm" placeholder="https://..." />
        </div>
        <div class="flex items-center justify-end gap-2 border-t border-white/10 px-4 py-3">
          <button type="button" class="rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200 hover:bg-white/10" @click="linkModalOpen = false">{{ tt('channel_rules_modal.cancel') }}</button>
          <button type="button" class="guard-green-soft rounded-lg px-3 py-2 text-sm font-semibold" @click="applyLinkModal()">{{ tt('channel_rules_modal.apply') }}</button>
        </div>
      </div>
    </div>
  </GuardTeleport>

  <GuardTeleport>
    <div
      v-if="imagePreviewUrl"
      class="fixed inset-0 z-[348] flex items-center justify-center bg-black/75 p-4"
      @click.self="imagePreviewUrl = ''"
    >
      <div class="max-h-[90vh] max-w-3xl overflow-hidden rounded-xl border border-white/15 bg-zinc-950 p-2" @click.stop>
        <div class="mb-2 flex justify-end">
          <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-300 hover:bg-white/10" @click="imagePreviewUrl = ''">✕</button>
        </div>
        <img :src="imagePreviewUrl" alt="preview" class="max-h-[75vh] w-full rounded-lg object-contain" />
      </div>
    </div>
  </GuardTeleport>
</template>

<style scoped>
.glass-panel {
  border-radius: 0.95rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(160deg, rgba(15, 23, 42, 0.56) 0%, rgba(2, 6, 23, 0.48) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(14px) saturate(140%);
}
.post-rules-tool-btn {
  border-radius: 0.65rem;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: linear-gradient(160deg, rgba(15, 23, 42, 0.52) 0%, rgba(2, 6, 23, 0.42) 100%);
  padding: 0.28rem 0.55rem;
  font-size: 11px;
  color: #dbeafe;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}
.post-rules-tool-btn:hover {
  border-color: rgba(103, 232, 249, 0.28);
  background: linear-gradient(160deg, rgba(8, 47, 73, 0.55) 0%, rgba(15, 23, 42, 0.5) 100%);
}
.post-rules-rich-editor {
  color: #f8fafc !important;
  caret-color: #f8fafc !important;
  -webkit-text-fill-color: #f8fafc;
}
.post-rules-rich-editor[data-placeholder]:empty:before {
  content: attr(data-placeholder);
  color: #94a3b8 !important;
  -webkit-text-fill-color: #94a3b8;
  pointer-events: none;
}
.post-rules-rich-editor :deep(a) {
  color: #60a5fa !important;
  -webkit-text-fill-color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.post-rules-footer {
  background: linear-gradient(180deg, rgba(2, 6, 23, 0.2), rgba(2, 6, 23, 0.35));
}
.post-rules-action-btn {
  border-radius: 0.72rem;
  border: 1px solid rgba(148, 163, 184, 0.28);
  padding: 0.42rem 0.82rem;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  transition: all 0.2s ease;
  backdrop-filter: blur(10px);
}
.post-rules-action-btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}
.post-rules-action-btn--cancel {
  color: #cbd5e1;
  background: linear-gradient(145deg, rgba(51, 65, 85, 0.34), rgba(15, 23, 42, 0.9));
}
.post-rules-action-btn--cancel:hover {
  border-color: rgba(148, 163, 184, 0.42);
}
.post-rules-action-btn--save {
  color: #042f2e;
  border-color: rgba(45, 212, 191, 0.5);
  background: linear-gradient(140deg, rgba(45, 212, 191, 0.95), rgba(52, 211, 153, 0.86));
  box-shadow: 0 12px 30px -18px rgba(45, 212, 191, 0.9);
}
.post-rules-action-btn--save:hover {
  filter: brightness(1.06);
}
</style>
