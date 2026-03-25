<script setup>
import { ref } from 'vue'
import AppHeader from './components/AppHeader.vue'
import AppSidebar from './components/AppSidebar.vue'
import AppToast from './components/AppToast.vue'

const sidebarOpen = ref(false)

function openMenu() {
  sidebarOpen.value = true
}

function closeSidebar() {
  sidebarOpen.value = false
}
</script>

<template>
  <div class="min-h-screen bg-[#f2f4ef] dark:bg-guardian-surface">
    <AppToast />
    <AppHeader :sidebar-open="sidebarOpen" @menu-click="openMenu" />
    <AppSidebar :open="sidebarOpen" @close="closeSidebar" />
    <main class="min-h-[calc(100vh-3.5rem)] md:pl-64">
      <div class="p-4 md:p-6">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
