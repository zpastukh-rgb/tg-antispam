<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'

const { t } = useI18n()

/**
 * Публичные PDF на Яндекс.Диске (AI Guard).
 * @see https://disk.yandex.ru/d/OrHmjMN39p0mDA
 */
const LEGAL_DOC_LINKS = {
  privacy: 'https://disk.yandex.ru/i/jNOP_341SFiyFA',
  storagePolicy: 'https://disk.yandex.ru/i/QDA7ObS0mtPcog',
  storagePd: 'https://disk.yandex.ru/i/jWOWM7Jkwh4lHw',
  destroyPd: 'https://disk.yandex.ru/i/KDwazlTk-Lv0vg',
  terms: 'https://disk.yandex.ru/i/w6rAjp9i6nVU6A',
  offer: 'https://disk.yandex.ru/i/4FDc5NkKCj7lHQ',
  pdProcessing: 'https://disk.yandex.ru/i/bf9ezUYiGyuN3w',
  marketing: 'https://disk.yandex.ru/i/tHT7Mr-xTautBg',
}

const legalBundleDocs = computed(() => [
  { title: t('legal.doc_privacy'), url: LEGAL_DOC_LINKS.privacy },
  { title: t('legal.doc_storage_policy'), url: LEGAL_DOC_LINKS.storagePolicy },
  { title: t('legal.doc_storage_pd'), url: LEGAL_DOC_LINKS.storagePd },
  { title: t('legal.doc_destroy_pd'), url: LEGAL_DOC_LINKS.destroyPd },
  { title: t('legal.doc_terms'), url: LEGAL_DOC_LINKS.terms },
  { title: t('legal.doc_offer'), url: LEGAL_DOC_LINKS.offer },
])
/**
 * true — окно при каждом открытии Mini App (для настройки текстов).
 * false — один раз на устройстве (ключ в localStorage), смените LEGAL_CONSENT_STORAGE_KEY при обновлении пакета документов.
 */
const LEGAL_GATE_EVERY_VISIT = false
const LEGAL_CONSENT_STORAGE_KEY = 'guard_legal_accepted_v1'

const emit = defineEmits(['accepted'])

const visible = ref(true)
const acceptBundle = ref(false)
const acceptPd = ref(false)
const acceptMarketing = ref(false)

function openDoc(url) {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null
  if (tg && typeof tg.openLink === 'function') {
    try {
      tg.openLink(url)
      return
    } catch {
      //
    }
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

const canContinue = computed(() => acceptBundle.value && acceptPd.value)

async function onContinue() {
  if (!canContinue.value) return
  if (!LEGAL_GATE_EVERY_VISIT) {
    try {
      localStorage.setItem(LEGAL_CONSENT_STORAGE_KEY, '1')
    } catch {
      //
    }
  }
  try {
    await api.postLegalConsent({
      accept_bundle: true,
      accept_pd: true,
      marketing: !!acceptMarketing.value,
    })
  } catch {
    //
  }
  if (acceptMarketing.value) {
    try {
      localStorage.setItem('guard_legal_marketing_opt_in', '1')
    } catch {
      //
    }
  } else {
    try {
      localStorage.removeItem('guard_legal_marketing_opt_in')
    } catch {
      //
    }
  }
  visible.value = false
  emit('accepted', { marketing: acceptMarketing.value })
}

function initVisibility() {
  if (LEGAL_GATE_EVERY_VISIT) {
    visible.value = true
    acceptBundle.value = false
    acceptPd.value = false
    acceptMarketing.value = false
    return
  }
  try {
    visible.value = !localStorage.getItem(LEGAL_CONSENT_STORAGE_KEY)
  } catch {
    visible.value = true
  }
}

initVisibility()

watch(
  visible,
  (v) => {
    if (typeof document === 'undefined') return
    document.body.style.overflow = v ? 'hidden' : ''
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.body.style.overflow = ''
})
</script>

<template>
  <div
    v-if="visible"
    class="isolate fixed inset-0 z-[99999] flex min-h-[100dvh] flex-col bg-black/92 backdrop-blur-md"
    role="dialog"
    aria-modal="true"
    aria-labelledby="legal-gate-title"
  >
      <div class="flex min-h-0 flex-1 flex-col justify-center overflow-y-auto px-4 py-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(1.5rem,env(safe-area-inset-top))]">
        <div
          class="mx-auto w-full max-w-md rounded-2xl border border-white/12 bg-zinc-950/95 p-4 shadow-[0_24px_64px_-16px_rgba(0,0,0,0.95)] ring-1 ring-inset ring-lime-500/15 sm:p-5"
        >
          <h1 id="legal-gate-title" class="text-center text-lg font-extrabold leading-tight tracking-tight text-white">
            {{ t('legal.title') }}
          </h1>
          <p class="mt-2 text-left text-[11px] leading-relaxed text-white/55 sm:text-[12px]">
            {{ t('legal.intro') }}
          </p>

          <div class="mt-4 space-y-2.5 text-left text-[11px] leading-relaxed text-white/[0.88] sm:text-[12px] sm:space-y-3">
            <label
              class="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.04] p-3.5 transition hover:border-white/[0.12] hover:bg-white/[0.06]"
            >
              <input v-model="acceptBundle" type="checkbox" class="mt-0.5 h-4 w-4 shrink-0 rounded border-white/25 bg-black/50 text-lime-500 focus:ring-lime-500/40" />
              <span class="min-w-0 flex-1 text-left">
                <span class="block text-white/[0.92]">{{ t('legal.bundle_checkbox_lead') }}</span>
                <ul class="mt-2 list-none space-y-1.5 border-l-2 border-lime-500/25 pl-3">
                  <li v-for="(doc, idx) in legalBundleDocs" :key="idx" class="leading-snug">
                    <button
                      type="button"
                      class="inline-block max-w-full text-left font-semibold text-lime-400 underline decoration-lime-500/40 underline-offset-[3px] transition hover:text-lime-300"
                      @click.prevent="openDoc(doc.url)"
                    >
                      {{ doc.title }}
                    </button>
                  </li>
                </ul>
              </span>
            </label>

            <label
              class="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.04] p-3.5 transition hover:border-white/[0.12] hover:bg-white/[0.06]"
            >
              <input v-model="acceptPd" type="checkbox" class="mt-0.5 h-4 w-4 shrink-0 rounded border-white/25 bg-black/50 text-lime-500 focus:ring-lime-500/40" />
              <span class="min-w-0 flex-1 text-left leading-snug text-white/[0.92]">
                {{ t('legal.pd_i_give') }}<button
                  type="button"
                  class="inline appearance-none border-0 bg-transparent p-0 align-baseline font-semibold text-lime-400 underline decoration-lime-500/40 underline-offset-[3px] hover:text-lime-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-lime-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950"
                  @click.prevent="openDoc(LEGAL_DOC_LINKS.pdProcessing)"
                >{{ t('legal.pd_link') }}</button>{{ t('legal.pd_after_link') }}
              </span>
            </label>

            <label
              class="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.04] p-3.5 transition hover:border-white/[0.12] hover:bg-white/[0.06]"
            >
              <input v-model="acceptMarketing" type="checkbox" class="mt-0.5 h-4 w-4 shrink-0 rounded border-white/25 bg-black/50 text-lime-500 focus:ring-lime-500/40" />
              <span class="min-w-0 flex-1 text-left leading-snug text-white/[0.92]">
                <span class="block text-white/[0.92]">{{ t('legal.mkt_i_give') }}</span>
                <button
                  type="button"
                  class="mt-0.5 block min-w-0 w-full appearance-none border-0 bg-transparent p-0 text-left font-semibold text-lime-400 underline decoration-lime-500/40 underline-offset-[3px] hover:text-lime-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-lime-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 whitespace-nowrap overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
                  @click.prevent="openDoc(LEGAL_DOC_LINKS.marketing)"
                >{{ t('legal.mkt_link') }}</button><span class="font-normal text-white/[0.92]">{{ t('legal.mkt_after_link') }}</span>
              </span>
            </label>
          </div>

          <button
            type="button"
            class="mt-6 flex w-full items-center justify-center rounded-xl bg-gradient-to-r from-lime-500 to-emerald-600 px-4 py-3.5 text-sm font-extrabold text-lime-950 shadow-[0_8px_28px_-8px_rgba(132,204,22,0.55)] transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100"
            :disabled="!canContinue"
            @click="onContinue"
          >
            {{ t('legal.btn_continue') }}
          </button>
        </div>
      </div>
    </div>
</template>
