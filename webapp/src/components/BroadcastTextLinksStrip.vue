<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { extractEditorTextLinks } from '../utils/telegramHtmlForTg'

const props = defineProps({
  html: { type: String, default: '' },
})

const { t: tt } = useI18n()

const links = computed(() => extractEditorTextLinks(props.html))
</script>

<template>
  <div v-if="links.length" class="mt-2 space-y-1.5">
    <p class="text-[11px] font-semibold text-slate-400">{{ tt('admin.broadcast_ui.text_links_title') }}</p>
    <div
      v-for="(link, i) in links"
      :key="`${i}-${link.url}-${link.text}`"
      class="rounded-lg border border-sky-400/25 bg-sky-500/8 px-2.5 py-2 text-[11px] leading-snug"
    >
      <p class="truncate font-semibold text-sky-100">{{ link.text }}</p>
      <p class="mt-0.5 break-all text-sky-200/75">{{ link.url }}</p>
    </div>
  </div>
</template>
