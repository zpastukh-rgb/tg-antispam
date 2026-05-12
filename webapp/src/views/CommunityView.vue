<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const isEn = computed(() => t('common.locale_code') === 'en')

function openHelp() {
  const url = 'https://t.me/Help_guard'
  const tg = window.Telegram?.WebApp
  if (typeof tg?.openTelegramLink === 'function') return tg.openTelegramLink(url)
  if (typeof tg?.openLink === 'function') return tg.openLink(url)
  window.open(url, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">{{ t('community.title') }}</h1>
    <div class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-800">
      <p class="text-sm text-slate-700 dark:text-slate-300">
        {{ isEn ? 'Help, support and Guard project updates.' : 'Помощь, поддержка и новости проекта Guard.' }}
      </p>
      <button
        type="button"
        class="mt-3 guard-green-soft rounded-xl px-4 py-2 text-sm font-semibold"
        @click="openHelp"
      >
        {{ isEn ? 'Open @Help_guard' : 'Открыть @Help_guard' }}
      </button>
    </div>
  </div>
</template>
