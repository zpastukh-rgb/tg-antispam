<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ChatAvatar from './ChatAvatar.vue'

const props = defineProps({
  groups: { type: Array, default: () => [] },
  channels: { type: Array, default: () => [] },
  selectedGroupIds: { type: Array, default: () => [] },
  selectedChannelIds: { type: Array, default: () => [] },
  normalizeChatId: { type: Function, required: true },
  showPausedBadge: { type: Boolean, default: false },
  listMaxHeight: { type: String, default: 'max-h-[min(52dvh,22rem)]' },
})

const emit = defineEmits(['update:selectedGroupIds', 'update:selectedChannelIds'])

const { t: tt, locale } = useI18n()

const activeTab = ref('groups')

watch(
  () => [props.groups.length, props.channels.length],
  () => {
    if (activeTab.value === 'groups' && !props.groups.length && props.channels.length) {
      activeTab.value = 'channels'
    } else if (activeTab.value === 'channels' && !props.channels.length && props.groups.length) {
      activeTab.value = 'groups'
    }
  },
  { immediate: true },
)

const groupCount = computed(() => (props.groups || []).length)
const channelCount = computed(() => (props.channels || []).length)

const currentItems = computed(() => (activeTab.value === 'channels' ? props.channels : props.groups) || [])

const selectedSet = computed(() => {
  const src = activeTab.value === 'channels' ? props.selectedChannelIds : props.selectedGroupIds
  return new Set((src || []).map((x) => Number(x || 0)).filter((x) => x !== 0))
})

function localeIsEn() {
  return String(locale.value || 'ru').toLowerCase().startsWith('en')
}

function fmtCount(n) {
  const v = Math.max(0, Math.trunc(Number(n || 0)))
  return new Intl.NumberFormat(localeIsEn() ? 'en-US' : 'ru-RU').format(v)
}

function ruPlural(n, one, few, many) {
  const v = Math.abs(Number(n || 0))
  const d100 = v % 100
  if (d100 >= 11 && d100 <= 14) return many
  const d10 = v % 10
  if (d10 === 1) return one
  if (d10 >= 2 && d10 <= 4) return few
  return many
}

function memberLabel(item, kind) {
  const mc = item?.member_count
  if (mc == null || !Number.isFinite(Number(mc)) || Number(mc) < 0) return ''
  const n = Math.trunc(Number(mc))
  const formatted = fmtCount(n)
  if (kind === 'channels') {
    if (localeIsEn()) {
      return n === 1
        ? tt('admin.broadcast_ui.subscribers_one', { n: formatted })
        : tt('admin.broadcast_ui.subscribers_other', { n: formatted })
    }
    return `${formatted} ${ruPlural(n, 'подписчик', 'подписчика', 'подписчиков')}`
  }
  if (localeIsEn()) {
    return n === 1
      ? tt('admin.broadcast_ui.members_one', { n: formatted })
      : tt('admin.broadcast_ui.members_other', { n: formatted })
  }
  return `${formatted} ${ruPlural(n, 'участник', 'участника', 'участников')}`
}

function itemTitle(item) {
  return String(item?.title || item?.username || props.normalizeChatId(item) || '').trim() || '—'
}

function itemChatId(item) {
  return props.normalizeChatId(item)
}

function isSelected(item) {
  return selectedSet.value.has(props.normalizeChatId(item))
}

function emitSelected(kind, ids) {
  const clean = [...new Set(ids.map((x) => Number(x || 0)).filter((x) => x !== 0))]
  if (kind === 'channels') emit('update:selectedChannelIds', clean)
  else emit('update:selectedGroupIds', clean)
}

function toggleItem(item) {
  const id = props.normalizeChatId(item)
  if (!id) return
  const kind = activeTab.value === 'channels' ? 'channels' : 'groups'
  const src = kind === 'channels' ? props.selectedChannelIds : props.selectedGroupIds
  const set = new Set((src || []).map((x) => Number(x || 0)).filter((x) => x !== 0))
  if (set.has(id)) set.delete(id)
  else set.add(id)
  emitSelected(kind, [...set])
}

function selectAllCurrent() {
  const kind = activeTab.value === 'channels' ? 'channels' : 'groups'
  const src = kind === 'channels' ? props.channels : props.groups
  const ids = (src || []).map((c) => props.normalizeChatId(c)).filter((x) => x < 0)
  emitSelected(kind, ids)
}

function clearCurrent() {
  const kind = activeTab.value === 'channels' ? 'channels' : 'groups'
  emitSelected(kind, [])
}
</script>

<template>
  <div class="rounded-2xl border border-white/[0.06] bg-[#0f1118] p-3">
    <p class="text-[15px] font-bold text-white">{{ tt('admin.broadcast_ui.recipients_title') }}</p>

    <div class="mt-3 rounded-xl bg-[#171a22] p-1">
      <div class="grid grid-cols-2 gap-1">
        <button
          type="button"
          class="relative flex items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-[13px] font-semibold transition"
          :class="activeTab === 'groups' ? 'text-white' : 'text-slate-400 hover:text-slate-200'"
          @click="activeTab = 'groups'"
        >
          <span>{{ tt('admin.broadcast_ui.tab_groups') }}</span>
          <span
            class="inline-flex min-w-[1.35rem] items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-bold"
            :class="activeTab === 'groups' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white/[0.08] text-slate-400'"
          >
            {{ groupCount }}
          </span>
          <span
            v-if="activeTab === 'groups'"
            class="absolute inset-x-2 -bottom-0.5 h-0.5 rounded-full bg-emerald-400"
          />
        </button>
        <button
          type="button"
          class="relative flex items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-[13px] font-semibold transition"
          :class="activeTab === 'channels' ? 'text-white' : 'text-slate-400 hover:text-slate-200'"
          @click="activeTab = 'channels'"
        >
          <span>{{ tt('admin.broadcast_ui.tab_channels') }}</span>
          <span
            class="inline-flex min-w-[1.35rem] items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-bold"
            :class="activeTab === 'channels' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white/[0.08] text-slate-400'"
          >
            {{ channelCount }}
          </span>
          <span
            v-if="activeTab === 'channels'"
            class="absolute inset-x-2 -bottom-0.5 h-0.5 rounded-full bg-emerald-400"
          />
        </button>
      </div>
    </div>

    <div class="mt-2.5 flex items-center justify-end gap-3 text-[12px]">
      <button type="button" class="font-semibold text-emerald-300 transition hover:text-emerald-200" @click="selectAllCurrent">
        {{ tt('admin.broadcast_ui.select_all') }}
      </button>
      <button type="button" class="font-semibold text-slate-400 transition hover:text-slate-200" @click="clearCurrent">
        {{ tt('admin.broadcast_ui.clear_all') }}
      </button>
    </div>

    <div class="mt-1 divide-y divide-white/[0.06] overflow-y-auto overscroll-contain touch-pan-y" :class="listMaxHeight">
      <button
        v-for="item in currentItems"
        :key="`${activeTab}-${normalizeChatId(item)}`"
        type="button"
        class="flex w-full items-center gap-3 py-3 text-left transition hover:bg-white/[0.02]"
        @click="toggleItem(item)"
      >
        <ChatAvatar
          :chat-id="itemChatId(item)"
          :title="itemTitle(item)"
          :username="item?.username || ''"
          size-class="h-10 w-10"
          text-class="text-[14px] font-bold"
        />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-[14px] font-semibold text-white">{{ itemTitle(item) }}</span>
          <span v-if="memberLabel(item, activeTab)" class="mt-0.5 block truncate text-[12px] text-slate-400">
            {{ memberLabel(item, activeTab) }}
          </span>
          <span
            v-if="showPausedBadge && item.is_paused"
            class="mt-1 inline-flex rounded-md border border-amber-400/35 bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-amber-200"
          >
            {{ tt('admin.broadcast_shell.group_paused_badge') }}
          </span>
        </span>
        <span
          class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[12px] font-bold transition"
          :class="
            isSelected(item)
              ? 'border-emerald-400/60 bg-emerald-500 text-white shadow-[0_0_12px_-2px_rgba(52,211,153,0.75)]'
              : 'border-white/20 bg-transparent text-transparent'
          "
          aria-hidden="true"
        >
          ✓
        </span>
      </button>
      <p v-if="!currentItems.length" class="py-6 text-center text-[12px] text-slate-500">
        {{ activeTab === 'channels' ? tt('admin.broadcast_ui.no_channels') : tt('admin.broadcast_ui.no_groups') }}
      </p>
    </div>
  </div>
</template>
