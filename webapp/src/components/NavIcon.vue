<script setup>
defineProps({
  name: { type: String, required: true },
  class: { type: String, default: 'w-5 h-5' },
})

const partnerHandshakeSrc = `${import.meta.env.BASE_URL}icons/partner-handshake.png`
const supportHeadsetSrc = `${import.meta.env.BASE_URL}icons/support-headset.png`
</script>

<template>
  <svg :class="[$props.class, ' shrink-0']" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <!-- dashboard -->
    <template v-if="name === 'dashboard'">
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </template>
    <!-- chats -->
    <template v-else-if="name === 'chats'">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </template>
    <!-- bell -->
    <template v-else-if="name === 'bell'">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </template>
    <!-- shield -->
    <template v-else-if="name === 'shield'">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </template>
    <!-- reports -->
    <template v-else-if="name === 'reports'">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <line x1="10" y1="9" x2="8" y2="9" />
    </template>
    <!-- billing -->
    <template v-else-if="name === 'billing'">
      <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
      <line x1="1" y1="10" x2="23" y2="10" />
      <path d="M12 15h4" />
    </template>
    <!-- connect -->
    <template v-else-if="name === 'connect'">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <line x1="19" y1="8" x2="19" y2="14" />
      <line x1="22" y1="11" x2="16" y2="11" />
    </template>
    <!-- gift -->
    <template v-else-if="name === 'gift'">
      <rect x="3" y="8" width="18" height="13" rx="2" />
      <path d="M12 8v13" />
      <path d="M3 12h18" />
      <path d="M12 8c-1.8 0-3.5-1-3.5-2.6S9.7 2 11.1 3.1C12 3.8 12 5 12 8z" />
      <path d="M12 8c1.8 0 3.5-1 3.5-2.6S14.3 2 12.9 3.1C12 3.8 12 5 12 8z" />
    </template>
    <!-- account -->
    <template v-else-if="name === 'account'">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </template>
    <!-- partner: PNG рукопожатие из макета (public/icons/partner-handshake.png) -->
    <template v-else-if="name === 'partner'">
      <image
        :href="partnerHandshakeSrc"
        x="0"
        y="0"
        width="24"
        height="24"
        preserveAspectRatio="xMidYMid meet"
      />
    </template>
    <!-- support: техподдержка (PNG гарнитура) -->
    <template v-else-if="name === 'support'">
      <image
        :href="supportHeadsetSrc"
        x="0"
        y="0"
        width="24"
        height="24"
        preserveAspectRatio="xMidYMid meet"
      />
    </template>
    <!-- telegram -->
    <template v-else-if="name === 'telegram'">
      <path
        d="M3.2 11.56c5.21-2.27 8.68-3.77 10.42-4.49 4.95-2.06 5.98-2.42 6.66-2.43.15 0 .48.03.71.2.19.14.24.33.27.47.03.14.07.45.04.69-.33 2.8-1.42 9.58-1.98 12.71-.24 1.32-.71 1.76-1.17 1.8-.99.09-1.74-.65-2.7-1.28-1.5-.98-2.34-1.59-3.79-2.55-1.68-1.1-.59-1.71.37-2.7.25-.26 4.63-4.24 4.72-4.6.01-.05.02-.23-.09-.33-.11-.1-.27-.07-.39-.04-.17.04-2.87 1.83-8.11 5.37-.77.53-1.47.79-2.1.77-.7-.02-2.05-.4-3.05-.73-1.23-.4-2.21-.61-2.12-1.29.05-.36.54-.72 1.47-1.09z"
        fill="currentColor"
        stroke="none"
      />
    </template>
    <!-- community -->
    <template v-else-if="name === 'community'">
      <path d="M21 11.5a8.5 8.5 0 1 1-3.2-6.6" />
      <path d="M22 2l-8.5 8.5" />
      <path d="M22 2l-5 14-3.5-5.5L8 7z" />
    </template>
    <!-- bolt -->
    <template v-else-if="name === 'bolt'">
      <polygon points="13 2 4 14 11 14 9 22 20 9 13 9" />
    </template>
    <!-- help -->
    <template v-else-if="name === 'help'">
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 1.8-2.5 2.2-2.5 4" />
      <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none" />
    </template>
    <!-- chevrons-down -->
    <template v-else-if="name === 'chevrons-down'">
      <polyline points="7 9 12 14 17 9" />
      <polyline points="7 14 12 19 17 14" />
    </template>
    <!-- settings -->
    <template v-else-if="name === 'settings'">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1 1 0 0 0 .2 1.1l.1.1a1 1 0 0 1 0 1.4l-1.4 1.4a1 1 0 0 1-1.4 0l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a1 1 0 0 1-1.4 0l-1.4-1.4a1 1 0 0 1 0-1.4l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H4a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a1 1 0 0 1 0-1.4l1.4-1.4a1 1 0 0 1 1.4 0l.1.1a1 1 0 0 0 1.1.2H9a1 1 0 0 0 .6-.9V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v.2a1 1 0 0 0 .6.9 1 1 0 0 0 1.1-.2l.1-.1a1 1 0 0 1 1.4 0l1.4 1.4a1 1 0 0 1 0 1.4l-.1.1a1 1 0 0 0-.2 1.1V9c0 .4.2.7.6.9H20a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1h-.2a1 1 0 0 0-.4 2z" />
    </template>
    <!-- calculator -->
    <template v-else-if="name === 'calculator'">
      <rect x="5" y="2" width="14" height="20" rx="2" />
      <rect x="8" y="5" width="8" height="3" rx="0.5" />
      <rect x="8" y="11" width="2.5" height="2.5" rx="0.3" />
      <rect x="11.25" y="11" width="2.5" height="2.5" rx="0.3" />
      <rect x="14.5" y="11" width="2.5" height="2.5" rx="0.3" />
      <rect x="8" y="14.5" width="2.5" height="2.5" rx="0.3" />
      <rect x="11.25" y="14.5" width="2.5" height="2.5" rx="0.3" />
      <rect x="14.5" y="14.5" width="2.5" height="6" rx="0.3" />
      <rect x="8" y="18" width="5.75" height="2.5" rx="0.3" />
    </template>
    <!-- sun -->
    <template v-else-if="name === 'sun'">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </template>
    <!-- moon -->
    <template v-else-if="name === 'moon'">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </template>
    <!-- back / arrow-left -->
    <template v-else-if="name === 'back' || name === 'arrow-left'">
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </template>
    <!-- menu -->
    <template v-else-if="name === 'menu'">
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </template>
    <!-- bar chart -->
    <template v-else-if="name === 'chart-bar'">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </template>
    <!-- users -->
    <template v-else-if="name === 'users'">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </template>
    <!-- send / plane -->
    <template v-else-if="name === 'send'">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </template>
    <!-- chevron-right -->
    <template v-else-if="name === 'chevron-right'">
      <polyline points="9 18 15 12 9 6" />
    </template>
    <template v-else>
      <circle cx="12" cy="12" r="2" />
    </template>
  </svg>
</template>
