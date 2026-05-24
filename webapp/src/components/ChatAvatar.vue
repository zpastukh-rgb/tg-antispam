<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { fetchChatAvatarBlobUrl } from '../api/client.js'
import {
  chatAvatarFallbackMeta,
  readCachedChatAvatarUrl,
  writeCachedChatAvatarUrl,
} from '../utils/chatAvatar.js'

const props = defineProps({
  chatId: { type: [String, Number], required: true },
  title: { type: String, default: '' },
  username: { type: String, default: '' },
  sizeClass: { type: String, default: 'h-10 w-10' },
  textClass: { type: String, default: 'text-sm font-bold' },
})

const photoUrl = ref(readCachedChatAvatarUrl(props.chatId))
const photoFailed = ref(false)
let loadToken = 0

const fallback = computed(() =>
  chatAvatarFallbackMeta(props.chatId, props.title, props.username),
)

const showPhoto = computed(() => Boolean(photoUrl.value) && !photoFailed.value)

async function loadPhoto() {
  const cid = String(props.chatId || '').trim()
  if (!cid) return
  const cached = readCachedChatAvatarUrl(cid)
  if (cached) {
    photoUrl.value = cached
    photoFailed.value = false
    return
  }
  const token = ++loadToken
  photoFailed.value = false
  try {
    const url = await fetchChatAvatarBlobUrl(cid)
    if (token !== loadToken) {
      if (url && url !== readCachedChatAvatarUrl(cid)) {
        try {
          URL.revokeObjectURL(url)
        } catch {
          //
        }
      }
      return
    }
    if (!url) {
      photoFailed.value = true
      photoUrl.value = ''
      return
    }
    writeCachedChatAvatarUrl(cid, url)
    photoUrl.value = url
  } catch {
    if (token === loadToken) photoFailed.value = true
  }
}

watch(
  () => [props.chatId, props.title, props.username],
  () => {
    photoUrl.value = readCachedChatAvatarUrl(props.chatId)
    photoFailed.value = false
    void loadPhoto()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  loadToken += 1
})
</script>

<template>
  <div
    class="relative shrink-0 overflow-hidden rounded-full"
    :class="sizeClass"
    :aria-label="title || username || String(chatId)"
  >
    <img
      v-if="showPhoto"
      :src="photoUrl"
      alt=""
      class="h-full w-full object-cover"
      @error="photoFailed = true"
    />
    <div
      v-else
      class="flex h-full w-full items-center justify-center text-white"
      :class="textClass"
      :style="{ background: fallback.background }"
    >
      {{ fallback.letter }}
    </div>
  </div>
</template>
