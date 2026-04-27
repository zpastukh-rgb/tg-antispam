<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '../composables/useApi'
import { useToast } from '../composables/useToast'
import { formatDateTimeRu } from '../utils/formatDateTime'

const route = useRoute()
const { api, error, fetchSilent, hasInitData } = useApi()
const referralBoot = ref(true)
const { showToast } = useToast()

const referral = ref(null)
const showInfoModal = ref(false)
const movingBonus = ref(false)

const referralBanner = `${import.meta.env.BASE_URL}referral_banner.jpg`

const activeUntilLabel = computed(() => formatDateTimeRu(referral.value?.active_until))
const bonusCreditsLabel = computed(() => {
  const v = Number(referral.value?.bonus_credits || 0)
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
})
const aurumCreditsLabel = computed(() => {
  const v = Number(referral.value?.aurum_credits || 0)
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
})

async function loadReferral() {
  try {
    referral.value = await fetchSilent(() => api.referral())
  } catch {
    referral.value = null
  } finally {
    referralBoot.value = false
  }
}

async function copyReferralLink() {
  const link = referral.value?.ref_link || ''
  if (!link) return
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(link)
      showToast('Ссылка скопирована')
      return
    }
  } catch {
    //
  }
  showToast('Скопируйте ссылку вручную')
}

function shareReferral() {
  const link = referral.value?.ref_link || ''
  if (!link) return
  fetchSilent(() => api.referralShareHit()).catch(() => {})
  const text = 'Guard защищает чаты от спама. Подключай и настраивай за минуты.'
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`
  const tg = window.Telegram?.WebApp
  if (typeof tg?.openTelegramLink === 'function') {
    tg.openTelegramLink(shareUrl)
    return
  }
  if (typeof tg?.openLink === 'function') {
    tg.openLink(shareUrl)
    return
  }
  window.open(shareUrl, '_blank', 'noopener,noreferrer')
}

async function moveBonusToAurum() {
  movingBonus.value = true
  try {
    const r = await fetchSilent(() => api.referralBonusToAurum())
    const moved = Number(r?.moved || 0)
    if (moved > 0) {
      const movedLabel = Number.isInteger(moved) ? String(moved) : moved.toFixed(2)
      showToast(`Переведено в AURUM: ${movedLabel} ✨`)
    } else {
      showToast('Партнерских токенов пока нет')
    }
    await loadReferral()
  } finally {
    movingBonus.value = false
  }
}

onMounted(async () => {
  if (!hasInitData.value) return
  await loadReferral()
  if ((route.query.info || '') === '1') showInfoModal.value = true
})

watch(
  () => route.query.info,
  (v) => {
    if ((v || '') === '1') showInfoModal.value = true
  }
)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">Реферальная программа</h1>
      <button
        type="button"
        class="inline-flex h-8 min-w-8 items-center justify-center rounded-full border border-sky-300 bg-sky-100 px-2 text-sm font-extrabold text-sky-800 shadow-sm hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-200 dark:hover:bg-sky-900/45"
        aria-label="Подробнее о реферальной программе"
        @click="showInfoModal = true"
      >
        i
      </button>
    </div>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      Откройте панель из Telegram.
    </div>
    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <template v-else-if="referral">
      <img
        :src="referralBanner"
        alt="Реферальная программа Guard"
        draggable="false"
        class="w-full rounded-2xl border border-white/20 shadow-[0_12px_30px_-22px_rgba(16,185,129,0.45)]"
        @dragstart.prevent
      />

      <section class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
        <h2 class="mb-3 text-base font-semibold text-slate-900 dark:text-white">🎁 Реферальная программа Guard</h2>
        <div class="space-y-3 text-[15px] text-slate-800 dark:text-slate-200">
          <p>
            Доступ: ✅ {{ referral.access_label }}<br>
            ├ Осталось дней: <b>{{ referral.days_left }}</b><br>
            └ Активен до: <b>{{ activeUntilLabel }}</b>
          </p>
          <p>
            Баланс:<br>
            ├ AURUM (рассылки/ИИ): <b>{{ aurumCreditsLabel }} ✨</b><br>
            └ Партнёрские токены: <b>{{ bonusCreditsLabel }} ⚡</b>
          </p>
          <p>
            Ваша партнёрская ссылка:<br>
            └ <button type="button" class="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm text-left dark:bg-slate-700" @click="copyReferralLink">{{ referral.ref_link }}</button>
          </p>
          <p>⬆️ Нажмите на неё, чтобы скопировать и поделитесь с друзьями! 🎁</p>
          <p>
            Приглашённых людей:<br>
            └ Всего: <b>{{ referral.invited_count }}</b>, Оплачивают: <b>{{ referral.paid_count }}</b>
          </p>
        </div>
      </section>

      <div class="grid gap-2">
        <button
          type="button"
          class="rounded-xl border border-violet-300 bg-violet-100 px-4 py-3 text-sm font-semibold text-violet-800 transition hover:bg-violet-200 dark:border-violet-700 dark:bg-violet-900/25 dark:text-violet-200 dark:hover:bg-violet-900/40 disabled:opacity-60"
          :disabled="movingBonus"
          @click="moveBonusToAurum"
        >
          ✨ Перевести партнёрские токены в AURUM
        </button>
        <button
          type="button"
          class="rounded-xl border border-sky-300 bg-sky-100 px-4 py-3 text-sm font-semibold text-sky-800 transition hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/25 dark:text-sky-200 dark:hover:bg-sky-900/40"
          @click="shareReferral"
        >
          ⭐ Поделиться
        </button>
      </div>
    </template>

    <div v-else-if="referralBoot" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">Загрузка…</span>
    </div>

    <div
      v-if="showInfoModal"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-3 md:items-center"
      @click.self="showInfoModal = false"
    >
      <div class="w-full max-w-md rounded-2xl border border-sky-300/50 bg-white p-4 shadow-2xl dark:border-sky-700/60 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h3 class="text-base font-semibold text-gray-900 dark:text-white">😈 Партнёрка — без лишней магии</h3>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            @click="showInfoModal = false"
          >
            ✕
          </button>
        </div>
        <ul class="list-disc space-y-1 pl-4 text-sm text-gray-700 dark:text-gray-300">
          <li>У тебя своя ссылка — по ней я понимаю, кого ты привёл.</li>
          <li>Когда приглашённый оплатил, каплю партнёрских ⚡ я начисляю на отдельный счёт.</li>
          <li>Они сами не утекают в рассылку: лежат, пока ты не решишь, что с ними делать.</li>
          <li>Можно перевести в AURUM ✨ для рассылок/ИИ.</li>
          <li>Рассылка списывает AURUM ✨.</li>
        </ul>
      </div>
    </div>
  </div>
</template>
