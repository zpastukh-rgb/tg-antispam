<script setup>
import { ref, watch, nextTick, computed, onBeforeUnmount } from 'vue'
import { useApi, syncInitDataState } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import {
  revokeBroadcastMediaPreviewUrl,
  uploadChatRulesPhoto,
  fetchChatRulesPhotoPreviewUrl,
  deleteChatRulesPhoto,
} from '../api/client'
import { normalizeHtmlForTelegram, telegramHtmlToEditorInnerHtml } from '../utils/telegramHtmlForTg'
import {
  editorSplitBlockquoteAtCaret,
  editorSoftBreakInsideBlockquote,
  editorPlaceCaretAtEditableStart,
  editorResetTypingExecCommands,
  editorUnwrapRangeInsideContainer,
  editorUnwrapElementFully,
  editorApplyMonospaceFormat,
} from '../utils/richEditorDom'
import { useI18n } from 'vue-i18n'
import { guardFilterChain } from '../utils/guardDebugLog.js'
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

const { api, error, fetchSilent } = useApi()
const { showToast } = useToast()

const rulesChat = ref(null)
const loadError = ref(false)
const loadBusy = ref(false)

const form = ref({ enabled: false, text: '', deleteWindowSec: 0 })
const buttonRows = ref([[{ text: '', url: '', web_app_url: '', callback_data: '' }]])
const busy = ref(false)
const saveBusy = ref(false)
const sendBusy = ref(false)
const previewUrl = ref('')
const photoUploadBusy = ref(false)
const bodyRef = ref(null)
const history = ref([])
const historyIndex = ref(-1)
const formatState = ref({
  bold: false,
  italic: false,
  underline: false,
  strike: false,
  quote: false,
  spoiler: false,
  mono: false,
  link: false,
})
const linkModalOpen = ref(false)
const linkUrl = ref('')
const linkRange = ref(null)
const savedRange = ref(null)
const showButtonsModal = ref(false)
const imagePreviewUrl = ref('')
const activePanel = ref('menu') // menu | rules
const pendingPhotoUrl = ref('')
const photoChangedInForm = ref(false)
const postRulesInfoOpen = ref(false)
const localNotice = ref('')
const localNoticeTone = ref('info') // info | ok | err

let autoSaveTimer = null
let deferredPhotoSaveTimer = null

function unlockPostRulesDocumentScrollHard() {
  if (typeof document === 'undefined') return
  try {
    document.documentElement.style.overflow = ''
    document.body.style.overflow = ''
  } catch {
    //
  }
}

/** Закрытие только явно — тап по «фону» в TG WebApp даёт «фантомный» click и ломает интеракцию. */
function close() {
  unlockPostRulesDocumentScrollHard()
  emit('update:modelValue', false)
}

function onPostRulesEscapeKey(ev) {
  if (!props.modelValue) return
  if (ev.key !== 'Escape' && ev.code !== 'Escape') return
  ev.preventDefault()
  ev.stopPropagation()
  close()
}

let escapeKeyBound = false
function bindPostRulesEscapeGuard(on) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  try {
    if (on && !escapeKeyBound) {
      document.addEventListener('keydown', onPostRulesEscapeKey, true)
      escapeKeyBound = true
      return
    }
    if (!on && escapeKeyBound) {
      document.removeEventListener('keydown', onPostRulesEscapeKey, true)
      escapeKeyBound = false
    }
  } catch {
    //
  }
}

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
  const baseDirty =
    fingerprintFromServerRule(r) !==
    fingerprintRulesState(buttonRows, form.value.enabled, form.value.text, form.value.deleteWindowSec)
  return baseDirty || !!photoChangedInForm.value
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
  const textDirty =
    fingerprintFromServerRule(rulesChat.value.rule) !==
    fingerprintRulesState(buttonRows, form.value.enabled, form.value.text, form.value.deleteWindowSec)
  if (!textDirty && !photoChangedInForm.value) return
  autoSaveTimer = setTimeout(async () => {
    autoSaveTimer = null
    if (!props.modelValue || !rulesChat.value?.rule || !isDirty.value) return
    await save({ silent: true })
  }, 2500)
}


function setLocalNotice(message = '', tone = 'info') {
  localNotice.value = String(message || '')
  localNoticeTone.value = String(tone || 'info')
}

function applyRuleFromRulesChatIntoForm(opts = {}) {
  const reloadEditor = opts.reloadEditor !== false
  const r = rulesChat.value?.rule
  if (!r) return
  form.value = {
    enabled: !!r.rules_channel_enabled,
    text: String(r.rules_channel_text || '').trim(),
    deleteWindowSec: Number(r.rules_channel_delete_window_sec || 0),
  }
  buttonRows.value = keyboardRowsFromRule(r.rules_channel_buttons || [])
  if (reloadEditor) editorLoadFromForm({ silent: true })
}

async function refreshRulesPanelData() {
  const discussionId = Number(props.discussionChatId || 0)
  if (!discussionId || !rulesChat.value?.rule) return
  try {
    const chatData = await fetchSilent(() => api.chat(discussionId, { refreshTelegram: true }))
    if (chatData?.rule) rulesChat.value = chatData
    pendingPhotoUrl.value = ''
    photoChangedInForm.value = false
    applyRuleFromRulesChatIntoForm({ reloadEditor: true })
    await loadPhotoPreview()
  } catch {
    //
  }
}

async function openRulesPanel() {
  guardFilterChain('ChannelRules', 'openRulesPanel', {
    discussionChatId: Number(props.discussionChatId || 0),
    channelId: Number(props.channelId || 0),
  })
  activePanel.value = 'rules'
  await nextTick()
  await nextTick()
  try {
    await refreshRulesPanelData()
  } catch {
    //
  }
  /* Пока была панель «меню», contenteditable не в DOM — editorLoadFromForm ранее мог не сработать.
   * После refresh и монтирования редактора применяем form.text явно (иначе возможен «левый» текст/рассинхрон). */
  await flushPostRulesEditorFromForm()
}

function backToChannelRulesMenu() {
  activePanel.value = 'menu'
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
  const s = String(dataUrl || '')
  const m = /^data:([^;,]*)(;base64)?,(.*)$/s.exec(s)
  if (!m) {
    return fetch(s).then((r) => r.blob())
  }
  const mime = (m[1] || 'image/jpeg').trim() || 'image/jpeg'
  const isB64 = !!m[2]
  const payload = m[3] || ''
  let binary
  try {
    binary = isB64 ? atob(payload) : decodeURIComponent(payload.replace(/\+/g, '%20'))
  } catch {
    return fetch(s).then((r) => r.blob())
  }
  const len = binary.length
  const bytes = new Uint8Array(len)
  for (let i = 0; i < len; i += 1) bytes[i] = binary.charCodeAt(i)
  return Promise.resolve(new Blob([bytes], { type: mime || 'image/jpeg' }))
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

function paintEditorFromForm() {
  const el = bodyRef.value
  if (!el) return false
  el.innerHTML = telegramHtmlToEditorInnerHtml(editorTextGet())
  history.value = [String(el.innerHTML || '')]
  historyIndex.value = 0
  return true
}

function editorLoadFromForm(opts = {}) {
  void opts?.silent
  nextTick(() => {
    if (paintEditorFromForm()) return
    nextTick(() => {
      if (paintEditorFromForm()) return
      requestAnimationFrame(() => {
        paintEditorFromForm()
      })
    })
  })
}

async function flushPostRulesEditorFromForm() {
  await nextTick()
  await nextTick()
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
  if (paintEditorFromForm()) return
  await new Promise((r) => requestAnimationFrame(r))
  paintEditorFromForm()
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
  updateFormatState()
}
function redo() {
  if (!canRedo()) return
  historyIndex.value += 1
  const el = bodyRef.value
  if (!el) return
  el.innerHTML = String(history.value[historyIndex.value] || '')
  editorTextSet(el.innerHTML)
  updateFormatState()
}

function elementUnderlineInRenderedEditor(elem) {
  if (!(elem instanceof HTMLElement)) return false
  try {
    const cs = window.getComputedStyle(elem)
    const line = `${cs.textDecorationLine || ''} ${cs.textDecoration || ''}`
    return line.includes('underline')
  } catch {
    return false
  }
}

function coerceUnderlineSpansToU(root) {
  if (!(root instanceof HTMLElement)) return
  const spans = root.querySelectorAll('span')
  for (let i = spans.length - 1; i >= 0; i -= 1) {
    const sp = spans.item(i)
    if (!(sp instanceof HTMLElement)) continue
    if (String(sp.getAttribute('data-spoiler') || '') === '1') continue
    if (String(sp.tagName || '').toLowerCase() === 'tg-spoiler') continue
    if (!elementUnderlineInRenderedEditor(sp)) continue
    const u = document.createElement('u')
    while (sp.firstChild) u.appendChild(sp.firstChild)
    sp.parentNode?.replaceChild(u, sp)
  }
}

function insertHtmlAtCursor(html) {
  const el = bodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0) : savedRange.value
  if (!range) return
  range.deleteContents()
  const temp = document.createElement('div')
  temp.innerHTML = html
  const frag = document.createDocumentFragment()
  let node = null
  while ((node = temp.firstChild)) frag.appendChild(node)
  range.insertNode(frag)
  range.collapse(false)
  if (sel) {
    sel.removeAllRanges()
    sel.addRange(range)
  }
  savedRange.value = range.cloneRange()
  onBodyInput()
}

function selectedTextFromRange(range) {
  if (!range) return ''
  try {
    return String(range.cloneContents().textContent || '')
  } catch {
    return ''
  }
}

function wrapEditorRange(range, htmlOpen, htmlClose) {
  if (!range) return false
  const text = selectedTextFromRange(range)
  if (!text.trim()) return false
  const sel = window.getSelection?.()
  if (sel) {
    sel.removeAllRanges()
    sel.addRange(range)
  }
  insertHtmlAtCursor(`${htmlOpen}${text}${htmlClose}`)
  return true
}

function caretSemanticFlags() {
  const el = bodyRef.value
  const sel = window.getSelection?.()
  if (!el || !sel?.focusNode) {
    return { quote: false, spoiler: false, mono: false, link: false }
  }
  if (!sel.rangeCount || !el.contains(sel.focusNode)) {
    return { quote: false, spoiler: false, mono: false, link: false }
  }
  let n = sel.focusNode.nodeType === Node.TEXT_NODE ? sel.focusNode.parentElement : sel.focusNode
  let quote = false
  let spoiler = false
  let mono = false
  let link = false
  while (n && n !== el) {
    if (!(n instanceof HTMLElement)) {
      n = n.parentElement
      continue
    }
    const tag = String(n.tagName || '').toLowerCase()
    if (tag === 'blockquote') quote = true
    if (tag === 'span' && String(n.getAttribute('data-spoiler') || '') === '1') spoiler = true
    if (tag === 'tg-spoiler') spoiler = true
    if (tag === 'pre' || tag === 'code') mono = true
    if (tag === 'a') link = true
    n = n.parentElement
  }
  return { quote, spoiler, mono, link }
}

function exec(cmd) {
  const el = bodyRef.value
  if (!el) return
  el.focus()
  if (cmd === 'bold' || cmd === 'italic' || cmd === 'underline' || cmd === 'strikeThrough') {
    try {
      document.execCommand('styleWithCSS', false, false)
    } catch {
      //
    }
  }
  document.execCommand(cmd, false)
  if (cmd === 'underline') coerceUnderlineSpansToU(el)
  onBodyInput()
  updateFormatState()
}

function formatBlockquote() {
  const el = bodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0) : savedRange.value
  if (!range) {
    showToast(tt('channel_rules_modal.hint_select_quote'))
    return
  }
  let n = range.commonAncestorContainer
  if (n.nodeType === Node.TEXT_NODE) n = n.parentElement
  const bq = n?.closest?.('blockquote')
  if (bq && el.contains(bq)) {
    if (range.collapsed) {
      editorUnwrapElementFully(bq)
    } else if (!selectedTextFromRange(range).trim()) {
      showToast(tt('channel_rules_modal.hint_select_quote'))
      return
    } else if (!editorUnwrapRangeInsideContainer(bq, range)) {
      showToast(tt('channel_rules_modal.hint_select_quote'))
      return
    }
    onBodyInput()
    updateFormatState()
    return
  }
  if (!wrapEditorRange(range, '<blockquote>', '</blockquote>')) {
    showToast(tt('channel_rules_modal.hint_select_quote'))
  }
  updateFormatState()
}

function formatSpoiler() {
  const el = bodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0) : savedRange.value
  if (!range) {
    showToast(tt('channel_rules_modal.hint_select_spoiler'))
    return
  }
  let n = range.commonAncestorContainer
  if (n.nodeType === Node.TEXT_NODE) n = n.parentElement
  const spoiler = n?.closest?.('[data-spoiler="1"], tg-spoiler')
  if (spoiler && el.contains(spoiler)) {
    if (range.collapsed) {
      editorUnwrapElementFully(spoiler)
    } else if (!selectedTextFromRange(range).trim()) {
      showToast(tt('channel_rules_modal.hint_select_spoiler'))
      return
    } else if (!editorUnwrapRangeInsideContainer(spoiler, range)) {
      showToast(tt('channel_rules_modal.hint_select_spoiler'))
      return
    }
    onBodyInput()
    updateFormatState()
    return
  }
  if (!wrapEditorRange(range, '<span data-spoiler="1">', '</span>')) {
    showToast(tt('channel_rules_modal.hint_select_spoiler'))
  }
  updateFormatState()
}

function formatMonospace() {
  const el = bodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0) : savedRange.value
  if (!range) {
    showToast(tt('channel_rules_modal.hint_select_mono'))
    return
  }
  if (sel) {
    sel.removeAllRanges()
    sel.addRange(range)
  }
  if (!editorApplyMonospaceFormat(el, range, { onEmpty: () => showToast(tt('channel_rules_modal.hint_select_mono')) })) {
    return
  }
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
  const sem = caretSemanticFlags()
  formatState.value = {
    bold: !!document.queryCommandState('bold'),
    italic: !!document.queryCommandState('italic'),
    underline: !!document.queryCommandState('underline'),
    strike: !!document.queryCommandState('strikeThrough'),
    quote: sem.quote,
    spoiler: sem.spoiler,
    mono: sem.mono,
    link: sem.link,
  }
}

function onEditorKeydown(e) {
  if (e.key !== 'Enter' || e.isComposing) return
  const el = bodyRef.value
  if (!el || e.target !== el) return
  if (e.shiftKey) {
    if (editorSoftBreakInsideBlockquote(el)) {
      e.preventDefault()
      e.stopPropagation()
      onBodyInput()
      requestAnimationFrame(() => {
        editorResetTypingExecCommands(el, { coerceUnderlineSpans: coerceUnderlineSpansToU })
        updateFormatState()
      })
    }
    return
  }
  if (editorSplitBlockquoteAtCaret(el, editorPlaceCaretAtEditableStart)) {
    e.preventDefault()
    e.stopPropagation()
    onBodyInput()
    requestAnimationFrame(() => {
      editorResetTypingExecCommands(el, { coerceUnderlineSpans: coerceUnderlineSpansToU })
      updateFormatState()
    })
    return
  }
  e.preventDefault()
  try {
    document.execCommand('insertLineBreak')
  } catch {
    document.execCommand('insertHTML', false, '<br>')
  }
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      editorResetTypingExecCommands(el, { coerceUnderlineSpans: coerceUnderlineSpansToU })
      onBodyInput()
      updateFormatState()
    })
  })
}

function formatLink() {
  const el = bodyRef.value
  if (!el) return
  el.focus()
  const sel = window.getSelection?.()
  const range = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : savedRange.value
  let n = range?.commonAncestorContainer
  if (n && n.nodeType === Node.TEXT_NODE) n = n.parentElement
  const linkEl = n?.closest?.('a')
  if (linkEl && el.contains(linkEl)) {
    try {
      const rg = document.createRange()
      rg.selectNodeContents(linkEl)
      sel?.removeAllRanges()
      sel?.addRange(rg)
      document.execCommand('unlink', false, null)
    } catch {
      //
    }
    onBodyInput()
    updateFormatState()
    return
  }
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
  const plain = String(el.innerText || '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  el.innerHTML = ''
  el.innerText = plain
  editorTextSet(String(el.innerHTML || ''))
  recordHistory(true)
  updateFormatState()
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
  if (!id) return
  syncInitDataState()
  guardFilterChain('ChannelRules', 'loadDiscussionChat:start', {
    discussionChatId: id,
    channelId: Number(props.channelId || 0),
  })
  loadBusy.value = true
  loadError.value = false
  rulesChat.value = null
  try {
    const data = await fetchSilent(() => api.chat(id, { refreshTelegram: true }))
    if (!data?.rule) {
      guardFilterChain('ChannelRules', 'loadDiscussionChat:no_rule_in_payload', {
        discussionChatId: id,
        keys: data && typeof data === 'object' ? Object.keys(data).slice(0, 40) : [],
      })
      loadError.value = true
      return
    }
    guardFilterChain('ChannelRules', 'loadDiscussionChat:got_rule', {
      discussionChatId: id,
      chatTitleLen: String(data?.title || '').length,
    })
    rulesChat.value = data
    form.value = {
      enabled: !!data.rule.rules_channel_enabled,
      text: String(data.rule.rules_channel_text || '').trim(),
      deleteWindowSec: Number(data.rule.rules_channel_delete_window_sec || 0),
    }
    buttonRows.value = keyboardRowsFromRule(data.rule.rules_channel_buttons || [])
    editorLoadFromForm({ silent: true })
    await loadPhotoPreview()
    pendingPhotoUrl.value = ''
    photoChangedInForm.value = false
    editorLoadFromForm({ silent: true })
  } catch (e) {
    guardFilterChain('ChannelRules', 'loadDiscussionChat:request_failed', {
      discussionChatId: id,
      status: e && typeof e === 'object' ? e.status : null,
      detail:
        e && typeof e === 'object' && e.body && typeof e.body === 'object'
          ? e.body.detail ?? e.body
          : e && typeof e === 'object' && 'message' in e
            ? e.message
            : String(e),
    })
    loadError.value = true
  } finally {
    loadBusy.value = false
  }
}

watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      bindPostRulesEscapeGuard(true)
      activePanel.value = 'rules'
      postRulesInfoOpen.value = false
      setLocalNotice('', 'info')
      await loadDiscussionChat()
      await nextTick()
      return
    }
    bindPostRulesEscapeGuard(false)
    unlockPostRulesDocumentScrollHard()
    clearAutoSaveTimer()
    rulesChat.value = null
    loadError.value = false
    showButtonsModal.value = false
    linkModalOpen.value = false
    imagePreviewUrl.value = ''
    activePanel.value = 'menu'
    postRulesInfoOpen.value = false
    setLocalNotice('', 'info')
    pendingPhotoUrl.value = ''
    photoChangedInForm.value = false
    if (previewUrl.value) revokeBroadcastMediaPreviewUrl(previewUrl.value)
    previewUrl.value = ''
  },
)

async function onPhotoPicked(event) {
  const f = event?.target?.files?.[0]
  event.target.value = ''
  if (!f) return
  photoUploadBusy.value = true
  try {
    const dataUrl = await fileToDataUrl(f)
    pendingPhotoUrl.value = dataUrl
    previewUrl.value = dataUrl
    photoChangedInForm.value = true
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
  pendingPhotoUrl.value = ''
  photoChangedInForm.value = true
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
    const photoDataUrl = String(pendingPhotoUrl.value || '')
    if (!skipPhoto && photoChangedInForm.value) {
      try {
        if (photoDataUrl) {
          try {
            const photoBlob = await dataUrlToBlob(photoDataUrl)
            const mime =
              photoBlob.type && String(photoBlob.type).toLowerCase().startsWith('image/')
                ? photoBlob.type
                : 'image/jpeg'
            const photoFile = new File([photoBlob], 'rules-photo.jpg', { type: mime })
            await uploadChatRulesPhoto(id, 'channel', photoFile)
          } catch {
            // fallback: stronger recompress and retry once
            const compact = await recompressDataUrl(photoDataUrl, 1024, 0.66)
            const compactBlob = await dataUrlToBlob(compact)
            const cm =
              compactBlob.type && String(compactBlob.type).toLowerCase().startsWith('image/')
                ? compactBlob.type
                : 'image/jpeg'
            const compactFile = new File([compactBlob], 'rules-photo-compact.jpg', { type: cm })
            await uploadChatRulesPhoto(id, 'channel', compactFile)
            pendingPhotoUrl.value = String(compact || photoDataUrl)
          }
        } else {
          try {
            await fetchSilent(() => deleteChatRulesPhoto(id, 'channel'))
          } catch {
            // no photo on backend is not a save blocker
          }
        }
        await loadPhotoPreview()
        if (photoDataUrl) pendingPhotoUrl.value = photoDataUrl
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
  if (isDirty.value || photoChangedInForm.value) {
    const ok = await save({ silent: true })
    if (!ok) return
  }
  sendBusy.value = true
  try {
    await fetchSilent(() =>
      api.sendChatRulesNow(id, {
        target: 'channel_comments',
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
  await save()
}

const discussionTitle = computed(() => String(rulesChat.value?.title || '').trim() || `ID ${props.discussionChatId}`)
const statusLabel = computed(() => {
  void i18nLocale.value
  if (isDirty.value || photoChangedInForm.value) return tt('channel_rules_modal.status_unsaved')
  return form.value.enabled ? tt('channel_rules_modal.status_on') : tt('channel_rules_modal.status_off')
})

async function onToggleEnabled() {
  form.value.enabled = !form.value.enabled
  void save({ silent: true })
}

function blurPostRulesEditorFromModalPointer(ev) {
  const ed = bodyRef.value
  if (!ed) return
  const raw = ev?.target
  if (!(raw instanceof Element)) return
  if (ed.contains(raw)) return
  if (raw.closest('button,label,a,input,textarea,select')) return
  ed.blur()
  try {
    window.getSelection()?.removeAllRanges()
  } catch {
    //
  }
}

watch(
  () => [
    props.modelValue,
    form.value.enabled,
    form.value.text,
    form.value.deleteWindowSec,
    buttonRows.value,
    photoChangedInForm.value,
    pendingPhotoUrl.value,
  ],
  () => {
    if (props.modelValue) scheduleAutoSave()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  bindPostRulesEscapeGuard(false)
  unlockPostRulesDocumentScrollHard()
  clearAutoSaveTimer()
  clearDeferredPhotoSaveTimer()
})
</script>

<template>
  <GuardTeleport guard-to="body">
    <div
      v-if="modelValue"
      style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 2147483100"
      class="flex max-h-[100dvh] min-h-0 items-start justify-center overflow-y-auto overscroll-y-contain bg-black/60 p-3 pt-[max(10px,env(safe-area-inset-top))] pb-[max(10px,env(safe-area-inset-bottom))] backdrop-blur-[2px] sm:p-4 sm:pt-[max(12px,env(safe-area-inset-top))]"
      role="dialog"
      aria-modal="true"
    >
      <div
        class="relative z-[2] my-auto flex min-h-0 w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-zinc-950/92 p-0 text-zinc-100 shadow-[0_28px_70px_-34px_rgba(0,0,0,0.9)] ring-1 ring-zinc-700/40 backdrop-blur-2xl backdrop-saturate-150"
      >
        <div class="flex items-center justify-between border-b border-zinc-800/80 px-4 py-3">
          <div>
            <div class="flex items-center gap-2">
              <h3 class="text-sm font-semibold text-white">{{ tt('channel_rules_modal.header') }}</h3>
              <span
                v-if="rulesChat && !loadBusy"
                class="inline-flex h-2.5 w-2.5 rounded-full"
                :class="isDirty ? 'bg-rose-400' : 'bg-emerald-400'"
                :title="statusLabel"
              />
            </div>
            <p v-if="rulesChat && !loadBusy" class="text-[10px] leading-snug" :class="isDirty || photoChangedInForm ? 'text-rose-300' : (form.enabled ? 'text-emerald-300/95' : 'text-zinc-500')">{{ statusLabel }}</p>
          </div>
          <button type="button" class="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/10" @click="close">✕</button>
        </div>
        <div v-if="rulesChat && !loadBusy" class="space-y-2 px-4 pt-2">
          <div class="flex items-center justify-end gap-1.5">
              <button type="button" class="inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-950/40 px-1 text-[10px] font-extrabold text-emerald-200/95" :aria-label="tt('protection.ui.info_group_rules_telegram_aria')" @click="postRulesInfoOpen = !postRulesInfoOpen">i</button>
              <button
                type="button"
                :class="boolToggleClass(!!form.enabled)"
                class="min-w-[5rem] rounded-lg px-2.5 py-1 text-xs font-medium"
                @click="onToggleEnabled"
              >
                {{ form.enabled ? tt('protection.ui.on_short') : tt('protection.ui.off_short') }}
              </button>
            </div>
          <div v-if="postRulesInfoOpen" class="rounded-lg border border-emerald-500/20 bg-emerald-950/25 px-2.5 py-2 text-[11px] text-emerald-100/95">
            <p class="mb-1 font-semibold text-emerald-50">{{ tt('protection.ui.channel_rules_help_title') }}</p>
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

        <div
          class="flex min-h-0 max-h-[min(78dvh,32rem)] flex-1 flex-col space-y-3 overflow-y-auto px-3 py-3 selection:bg-emerald-500/25 selection:text-emerald-50 sm:max-h-[min(82vh,40rem)] sm:px-4"
          @pointerdown.capture="blurPostRulesEditorFromModalPointer"
        >
          <div v-if="loadBusy" class="py-8 text-center text-sm text-slate-400">{{ tt('protection.ui.channel_rules_loading') }}</div>
          <div v-else-if="loadError || !rulesChat" class="py-6 text-center text-sm text-rose-300">
            {{ tt('protection.ui.channel_rules_load_error') }}
          </div>
          <template v-else>
            <div class="glass-panel p-3">
              <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{{ tt('channel_rules_modal.rules_text_heading') }}</p>
              <div class="mb-1.5 flex flex-wrap gap-1.5">
                <button type="button" class="post-rules-tool-btn font-semibold" :class="formatState.bold ? 'post-rules-tool-active' : ''" @mousedown.prevent @click="exec('bold')">{{ tt('channel_rules_modal.fmt_bold') }}</button>
                <button type="button" class="post-rules-tool-btn italic" :class="formatState.italic ? 'post-rules-tool-active' : ''" @mousedown.prevent @click="exec('italic')">{{ tt('channel_rules_modal.fmt_italic') }}</button>
                <button type="button" class="post-rules-tool-btn underline" :class="formatState.underline ? 'post-rules-tool-active' : ''" @mousedown.prevent @click="exec('underline')">{{ tt('channel_rules_modal.fmt_underline') }}</button>
                <button type="button" class="post-rules-tool-btn line-through" :class="formatState.strike ? 'post-rules-tool-active' : ''" @mousedown.prevent @click="exec('strikeThrough')">{{ tt('channel_rules_modal.fmt_strike') }}</button>
                <button type="button" class="post-rules-tool-btn text-[11px]" :class="formatState.quote ? 'post-rules-tool-active' : ''" :title="tt('channel_rules_modal.fmt_quote_title')" @mousedown.prevent @click="formatBlockquote">{{ tt('channel_rules_modal.fmt_quote') }}</button>
                <button type="button" class="post-rules-tool-btn text-[11px]" :class="formatState.spoiler ? 'post-rules-tool-active' : ''" :title="tt('channel_rules_modal.fmt_spoiler_title')" @mousedown.prevent @click="formatSpoiler">{{ tt('channel_rules_modal.fmt_spoiler') }}</button>
                <button type="button" class="post-rules-tool-btn font-mono text-[11px]" :class="formatState.mono ? 'post-rules-tool-active' : ''" :title="tt('channel_rules_modal.fmt_mono_title')" @mousedown.prevent @click="formatMonospace">{{ tt('channel_rules_modal.fmt_mono') }}</button>
                <button type="button" class="post-rules-tool-btn" :class="formatState.link ? 'post-rules-tool-active' : ''" @mousedown.prevent @click="formatLink">{{ tt('channel_rules_modal.link_btn') }}</button>
                <button type="button" class="post-rules-tool-btn" @mousedown.prevent @click="clearFormatting">{{ tt('channel_rules_modal.clear_fmt') }}</button>
              </div>
              <div class="mb-1.5 flex flex-wrap items-center gap-1.5">
                <button type="button" class="post-rules-tool-btn min-w-[2.1rem] px-2 text-base leading-none text-zinc-200" :class="!canUndo() ? 'opacity-40' : ''" :disabled="!canUndo()" :title="tt('channel_rules_modal.undo')" @mousedown.prevent @click="undo">↶</button>
                <button type="button" class="post-rules-tool-btn min-w-[2.1rem] px-2 text-base leading-none text-zinc-200" :class="!canRedo() ? 'opacity-40' : ''" :disabled="!canRedo()" :title="tt('channel_rules_modal.redo')" @mousedown.prevent @click="redo">↷</button>
                <label class="post-rules-tool-btn cursor-pointer">
                  {{ photoUploadBusy ? tt('channel_rules_modal.photo_uploading') : tt('channel_rules_modal.file_btn') }}
                  <input type="file" accept="image/*" class="hidden" :disabled="busy || photoUploadBusy" @change="onPhotoPicked" />
                </label>
                <span v-if="photoUploadBusy" class="text-[10px] text-emerald-400/95">{{ tt('channel_rules_modal.photo_processing') }}</span>
                <div v-if="previewUrl" class="post-rules-thumb-wrap group relative h-8 w-8 shrink-0 overflow-hidden rounded-lg border border-white/12 bg-black/40">
                  <button type="button" class="absolute inset-0 z-0" :aria-label="tt('channel_rules_modal.photo_preview_open')" @click="imagePreviewUrl = previewUrl"></button>
                  <img :src="previewUrl" alt="" class="pointer-events-none relative z-0 h-full w-full object-cover" />
                  <button
                    type="button"
                    class="post-rules-thumb-remove absolute right-0 top-0 z-10 flex h-5 w-5 items-center justify-center rounded-bl-md bg-black/75 text-[13px] font-bold leading-none text-white hover:bg-rose-600/90"
                    :aria-label="tt('channel_rules_modal.remove_photo_aria')"
                    @click.stop.prevent="removePhoto"
                  >
                    ×
                  </button>
                </div>
                <div class="flex items-center gap-1">
                  <button type="button" class="post-rules-tool-btn" @click="showButtonsModal = true">{{ tt('channel_rules_modal.buttons_btn') }}</button>
                  <span v-if="inlineButtonCount > 0" class="rounded-md border border-emerald-500/30 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-bold text-emerald-100">{{ inlineButtonCount }}</span>
                </div>
              </div>
              <div
                ref="bodyRef"
                contenteditable="true"
                class="post-rules-rich-editor select-text max-h-[min(42dvh,15rem)] min-h-[9.5rem] w-full overflow-y-auto rounded-xl border border-zinc-700/65 bg-zinc-950 px-3 py-2 text-sm leading-relaxed text-zinc-100 outline-none ring-0 focus-within:border-emerald-500/45 focus-within:shadow-[inset_0_0_0_1px_rgba(52,211,153,0.22)] sm:max-h-[min(48vh,18rem)]"
                :data-placeholder="tt('channel_rules_modal.editor_placeholder')"
                @keydown="onEditorKeydown"
                @input="onBodyInput"
                @mouseup="updateFormatState"
                @keyup="updateFormatState"
                @click="updateFormatState"
              />
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
          </template>
        </div>

        <div class="post-rules-footer flex flex-col gap-2 border-t border-zinc-800/80 px-3 py-2.5 sm:px-4">
          <div class="flex flex-wrap items-center justify-end gap-2">
          <button type="button" class="post-rules-action-btn post-rules-action-btn--cancel" @click="close">{{ tt('channel_rules_modal.close') }}</button>
          <button
            v-if="rulesChat && !loadBusy"
            type="button"
            class="post-rules-action-btn guard-green-soft border border-transparent font-semibold text-slate-950 hover:brightness-[1.04]"
            :disabled="sendBusy || saveBusy || !rulesChat"
            @click="sendNow()"
          >
            {{ sendBusy ? tt('channel_rules_modal.send_busy') : tt('channel_rules_modal.send_to_comments') }}
          </button>
          <button v-if="rulesChat && !loadBusy" type="button" class="post-rules-action-btn guard-green-soft border border-transparent font-semibold text-slate-950 shadow-sm hover:brightness-[1.05]" :disabled="saveBusy || !rulesChat" @click="save()">
            {{ saveBusy ? tt('channel_rules_modal.save_busy') : tt('channel_rules_modal.save') }}
          </button>
          </div>
        </div>
      </div>
    </div>
  </GuardTeleport>

  <GuardTeleport guard-to="body">
    <div
      v-if="showButtonsModal && modelValue && rulesChat"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:2147483120;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
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

  <GuardTeleport guard-to="body">
    <div
      v-if="linkModalOpen && modelValue"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:2147483120;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
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

  <GuardTeleport guard-to="body">
    <div
      v-if="imagePreviewUrl"
      style="position:fixed;top:0;left:0;right:0;bottom:0;z-index:2147483120;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);padding:16px" class="flex items-center justify-center bg-black/75 p-4"
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
  border: 1px solid rgba(63, 63, 70, 0.65);
  background: linear-gradient(165deg, rgba(24, 24, 27, 0.72) 0%, rgba(9, 9, 11, 0.62) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(12px) saturate(125%);
}
.post-rules-tool-btn {
  border-radius: 0.65rem;
  border: 1px solid rgba(63, 63, 70, 0.85);
  background: linear-gradient(165deg, rgba(24, 24, 27, 0.75) 0%, rgba(15, 23, 42, 0.4) 100%);
  padding: 0.28rem 0.55rem;
  font-size: 11px;
  color: #e4e4e7;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
}
.post-rules-tool-btn:hover {
  border-color: rgba(163, 230, 53, 0.35);
  background: linear-gradient(165deg, rgba(39, 52, 18, 0.42) 0%, rgba(24, 24, 27, 0.65) 100%);
}
.post-rules-tool-active {
  border-color: rgba(52, 211, 153, 0.55) !important;
  background: linear-gradient(160deg, rgba(6, 78, 59, 0.55) 0%, rgba(15, 23, 42, 0.52) 100%) !important;
  color: #ecfdf5 !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 0 18px -6px rgba(52, 211, 153, 0.35);
}
@media (hover: hover) {
  .post-rules-thumb-remove {
    opacity: 0;
    transition: opacity 0.15s ease;
  }
  .post-rules-thumb-wrap:hover .post-rules-thumb-remove {
    opacity: 1;
  }
}
@media (hover: none) {
  .post-rules-thumb-remove {
    opacity: 0.88;
  }
}
.post-rules-rich-editor :deep(b),
.post-rules-rich-editor :deep(strong) {
  font-weight: 700;
}
.post-rules-rich-editor :deep(blockquote) {
  display: block;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  margin: 0.35rem 0;
  padding: 0.35rem 1.35rem 0.35rem 0.65rem;
  border-left: 3px solid rgba(56, 189, 248, 0.88);
  background: rgba(59, 130, 246, 0.12);
  border-radius: 0.4rem;
  position: relative;
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.post-rules-rich-editor :deep(blockquote)::after {
  content: '\201d';
  position: absolute;
  top: 0.12rem;
  right: 0.38rem;
  font-size: 0.95rem;
  line-height: 1;
  font-weight: 600;
  color: rgba(56, 189, 248, 0.72);
  pointer-events: none;
}
.post-rules-rich-editor :deep(pre) {
  margin: 0.35rem 0;
  padding: 0.35rem 0.5rem;
  border-radius: 0.35rem;
  background: rgba(15, 23, 42, 0.85);
  font-family: ui-monospace, monospace;
  font-size: 0.85em;
  white-space: pre-wrap;
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
.post-rules-rich-editor :deep([data-spoiler='1']),
.post-rules-rich-editor :deep(tg-spoiler) {
  color: transparent !important;
  -webkit-text-fill-color: transparent;
  border-radius: 0.35rem;
  padding: 0 0.2rem;
  background-color: rgba(148, 163, 184, 0.22);
  background-image: radial-gradient(rgba(226, 232, 240, 0.9) 0.85px, transparent 0.9px);
  background-size: 5px 5px;
  transition: color 0.15s ease, background-color 0.15s ease;
}
.post-rules-rich-editor :deep([data-spoiler='1']:hover),
.post-rules-rich-editor :deep(tg-spoiler:hover) {
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.post-rules-rich-editor :deep([data-spoiler='1'].reveal),
.post-rules-rich-editor :deep(tg-spoiler.reveal) {
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.post-rules-rich-editor :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.92em;
  padding: 0.05rem 0.25rem;
  border-radius: 0.25rem;
  background: rgba(148, 163, 184, 0.14);
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
  white-space: pre-wrap;
  word-break: break-word;
}
.post-rules-rich-editor :deep(pre) {
  display: block;
  max-width: 100%;
  box-sizing: border-box;
  margin: 0.35rem 0;
  padding: 0.35rem 0.5rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.92em;
  border-radius: 0.35rem;
  background: rgba(148, 163, 184, 0.12);
  color: #e2e8f0 !important;
  -webkit-text-fill-color: #e2e8f0;
}
.post-rules-rich-editor :deep(a) {
  color: #60a5fa !important;
  -webkit-text-fill-color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.post-rules-footer {
  background: linear-gradient(180deg, rgba(9, 9, 11, 0.85), rgba(9, 9, 11, 0.94));
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
  color: #a1a1aa;
  background: rgba(24, 24, 27, 0.92);
  border-color: rgba(63, 63, 70, 0.95);
}
.post-rules-action-btn--cancel:hover {
  border-color: rgba(82, 82, 91, 0.95);
  color: #e4e4e7;
}
</style>
