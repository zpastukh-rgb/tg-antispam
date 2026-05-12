<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'

const { t } = useI18n()
const router = useRouter()
const { api, fetchSilent, error, hasInitData } = useApi()
const me = ref(null)
const meReady = ref(false)

const isPremium = computed(() => {
  const tk = (me.value?.tariff || 'free').toLowerCase()
  return ['premium', 'pro', 'business'].includes(tk)
})

const isEn = computed(() => t('common.locale_code') === 'en')

onMounted(async () => {
  if (!hasInitData.value) return
  try {
    me.value = await fetchSilent(() => api.me())
  } catch {
    //
  } finally {
    meReady.value = true
  }
})
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">AURUM</h1>

    <div v-if="!hasInitData" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      {{ isEn ? 'Open the panel from Telegram.' : 'Откройте панель из Telegram.' }}
    </div>
    <div v-else-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>
    <div v-else-if="!meReady" class="rounded-xl border border-gray-200 bg-white p-8 text-center dark:border-gray-700 dark:bg-gray-800">
      <span class="text-gray-500 dark:text-gray-400">{{ t('loading.generic') }}</span>
    </div>
    <div v-else class="rounded-2xl bg-slate-900 p-5 text-white">
      <p class="rounded-xl border border-cyan-300/60 px-4 py-3 text-center text-base text-cyan-100">
        ℹ️ {{ t('tokens.landing_caption') }}
      </p>
      <button
        v-if="!isPremium"
        type="button"
        class="mt-4 guard-green-soft w-full rounded-xl px-4 py-3 text-lg font-semibold"
        @click="router.push('/billing')"
      >
        {{ t('tokens.purchase') }}
      </button>
      <button
        v-else
        type="button"
        class="mt-4 guard-green-soft w-full rounded-xl px-4 py-3 text-lg font-semibold"
        @click="router.push('/billing')"
      >
        {{ t('tokens.open_for_pricing') }}
      </button>
    </div>
  </div>
</template>
