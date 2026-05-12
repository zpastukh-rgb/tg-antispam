<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const isEn = computed(() => t('common.locale_code') === 'en')
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-gray-900 dark:text-white md:text-2xl">{{ t('gifts.title') }}</h1>
    <div class="rounded-2xl border border-cyan-300/60 bg-slate-900 p-5 text-center text-cyan-100 shadow">
      <p class="text-lg font-semibold">{{ isEn ? 'No gifts yet 🙁' : 'Подарков пока нет 🙁' }}</p>
      <p class="mt-2 text-sm text-cyan-200/90">
        {{ isEn ? 'Join the referral program and follow community updates.' : 'Участвуйте в реферальной программе и следите за новостями сообщества.' }}
      </p>
    </div>
  </div>
</template>
