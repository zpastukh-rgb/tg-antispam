<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BC_MAX_MEDIA_ITEMS, BC_MEDIA_FILE_ACCEPT } from '../constants/broadcastMedia.js'

const props = defineProps({
  items: { type: Array, default: () => [] },
  uploading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  maxItems: { type: Number, default: BC_MAX_MEDIA_ITEMS },
  size: { type: String, default: 'md' }, // sm | md
})

const emit = defineEmits(['upload', 'remove', 'view'])

const { t: tt } = useI18n()
const fileInputRef = ref(null)
const dropActive = ref(false)

const tileClass = computed(() =>
  props.size === 'sm'
    ? 'h-[3.5rem] w-[3.5rem] rounded-lg'
    : 'h-[4.5rem] w-[4.5rem] rounded-xl',
)

const canAdd = computed(
  () => !props.disabled && !props.uploading && (props.items?.length || 0) < props.maxItems,
)

function kindLower(kind) {
  return String(kind || '').toLowerCase()
}

function canPreview(item) {
  const k = kindLower(item?.kind)
  return (
    !!item?.previewUrl &&
    (k.includes('photo') || k.includes('video') || k === 'animation' || k === 'document')
  )
}

function isVideoKind(kind) {
  return kindLower(kind).includes('video')
}

function mediaIcon(kind) {
  const k = kindLower(kind)
  if (k === 'photo') return '🖼'
  if (k.includes('video')) return '🎬'
  if (k === 'animation') return '🎞'
  if (k === 'audio') return '🎵'
  if (k === 'document') return '📄'
  return '📎'
}

function onFilesSelected(ev) {
  const input = ev.target
  const files = input?.files
  if (!files?.length) return
  emit('upload', files)
  // Сброс после выбора — на следующем кадре, чтобы Telegram WebView успел отдать files.
  requestAnimationFrame(() => {
    if (input) input.value = ''
  })
}

function openFilePicker(ev) {
  if (!canAdd.value) return
  if (ev?.target === fileInputRef.value) return
  fileInputRef.value?.click()
}

function onDragEnter(ev) {
  if (!canAdd.value) return
  ev.preventDefault()
  dropActive.value = true
}

function onDragOver(ev) {
  if (!canAdd.value) return
  ev.preventDefault()
  dropActive.value = true
}

function onDragLeave(ev) {
  if (ev.currentTarget?.contains?.(ev.relatedTarget)) return
  dropActive.value = false
}

function onDrop(ev) {
  if (!canAdd.value) return
  ev.preventDefault()
  dropActive.value = false
  const files = ev.dataTransfer?.files
  if (files?.length) emit('upload', files)
}
</script>

<template>
  <div class="w-full">
    <div class="flex flex-nowrap items-start gap-2 overflow-x-auto overscroll-x-contain pb-0.5 [-webkit-overflow-scrolling:touch]">
      <div
        v-for="(m, mi) in items"
        :key="`bc-ms-${m.id || mi}`"
        class="relative shrink-0"
      >
        <button
          v-if="canPreview(m)"
          type="button"
          class="group relative block overflow-hidden border border-white/15 bg-slate-950/80 shadow-md ring-1 ring-white/[0.06] transition hover:border-cyan-400/35 hover:ring-cyan-400/25"
          :class="tileClass"
          :title="tt('admin.broadcast_ui.open_large')"
          @click="emit('view', m)"
        >
          <img
            v-if="kindLower(m.kind).includes('photo') || kindLower(m.kind) === 'animation' || (kindLower(m.kind) === 'document' && String(m.name || '').toLowerCase().endsWith('.gif'))"
            :src="m.previewUrl"
            class="h-full w-full object-cover"
            alt=""
          />
          <video
            v-else
            :src="m.previewUrl"
            class="h-full w-full object-cover"
            muted
            playsinline
          />
          <span
            v-if="isVideoKind(m.kind)"
            class="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/25"
            aria-hidden="true"
          >
            <span class="flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-[11px] text-white">▶</span>
          </span>
          <span
            class="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-white/[0.03] opacity-80 group-hover:opacity-100"
          />
        </button>
        <div
          v-else
          class="flex flex-col items-center justify-center gap-0.5 border border-white/10 bg-slate-950/75 p-1 text-center shadow-inner ring-1 ring-white/[0.04]"
          :class="tileClass"
        >
          <span class="text-lg leading-none">{{ mediaIcon(m.kind) }}</span>
          <span class="line-clamp-2 max-w-full px-0.5 text-[8px] leading-tight text-slate-400">{{ m.name }}</span>
        </div>
        <button
          v-if="m.id && !disabled"
          type="button"
          class="absolute -right-1 -top-1 z-[2] flex h-5 w-5 items-center justify-center rounded-full bg-rose-600 text-[10px] font-bold text-white shadow ring-1 ring-white/25"
          :title="tt('admin.broadcast_ui.remove_attachment')"
          @click.stop="emit('remove', m.id)"
        >
          ✕
        </button>
      </div>

      <div
        v-if="uploading"
        class="relative flex shrink-0 flex-col items-center justify-center border border-dashed border-emerald-400/45 bg-emerald-500/10 pointer-events-none"
        :class="tileClass"
        :title="tt('admin.broadcast_ui.uploading_attachment')"
      >
        <span class="bc-media-upload-spinner" aria-hidden="true" />
      </div>

      <div
        v-else-if="canAdd"
        class="relative flex shrink-0 flex-col items-center justify-center border border-dashed transition"
        :class="[
          tileClass,
          dropActive
            ? 'border-emerald-400/70 bg-emerald-500/15 ring-2 ring-emerald-400/35'
            : 'border-white/25 bg-white/[0.03] hover:border-violet-400/45 hover:bg-violet-500/10',
        ]"
        :title="tt('admin.broadcast_ui.add_attachment_hint')"
        @click="openFilePicker"
        @dragenter="onDragEnter"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
      >
        <input
          ref="fileInputRef"
          type="file"
          class="bc-media-file-input"
          multiple
          :accept="BC_MEDIA_FILE_ACCEPT"
          @change="onFilesSelected"
        />
        <span class="pointer-events-none relative z-[1] text-2xl font-light leading-none text-slate-300">+</span>
        <span v-if="dropActive" class="pointer-events-none absolute inset-x-1 bottom-1 z-[1] text-center text-[8px] leading-tight text-emerald-200/90">
          {{ tt('admin.broadcast_ui.drop_to_upload') }}
        </span>
      </div>
    </div>

    <p v-if="(items?.length || 0) >= maxItems" class="mt-1.5 text-[10px] text-slate-500">
      {{ tt('admin.broadcast_ui.media_limit', { max: maxItems }) }}
    </p>
  </div>
</template>

<style scoped>
.bc-media-upload-spinner {
  width: 1.65rem;
  height: 1.65rem;
  border: 2.5px solid rgba(255, 255, 255, 0.18);
  border-top-color: #34d399;
  border-right-color: rgba(52, 211, 153, 0.45);
  border-radius: 9999px;
  animation: bc-media-upload-spin 0.75s linear infinite;
}

.bc-media-file-input {
  position: absolute;
  inset: 0;
  z-index: 3;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  opacity: 0.001;
  cursor: pointer;
  font-size: 16px;
}

@keyframes bc-media-upload-spin {
  to {
    transform: rotate(360deg);
  }
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
