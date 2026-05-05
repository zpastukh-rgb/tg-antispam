import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import { useDashboardSection } from '../composables/useDashboardSection'

const routes = [
  { path: '/', name: 'Dashboard', component: DashboardView, meta: { title: 'Главная' } },
  { path: '/chats', name: 'Chats', component: () => import('../views/ChatsView.vue'), meta: { title: 'Подключённые чаты' } },
  { path: '/protection', name: 'Protection', component: () => import('../views/ProtectionView.vue'), meta: { title: 'Защита' } },
  { path: '/reports', name: 'Reports', component: () => import('../views/ReportsView.vue'), meta: { title: 'Отчёты' } },
  { path: '/billing', name: 'Billing', redirect: '/' },
  { path: '/tokens', name: 'Tokens', component: () => import('../views/TokensView.vue'), meta: { title: 'Токены' } },
  { path: '/history', name: 'History', component: () => import('../views/HistoryView.vue'), meta: { title: 'История средств' } },
  { path: '/referral', name: 'Referral', component: () => import('../views/ReferralView.vue'), meta: { title: 'Реферальная программа' } },
  { path: '/gifts', name: 'Gifts', component: () => import('../views/GiftsView.vue'), meta: { title: 'Подарки' } },
  { path: '/community', name: 'Community', component: () => import('../views/CommunityView.vue'), meta: { title: 'Сообщество' } },
  { path: '/connect', name: 'Connect', component: () => import('../views/ConnectView.vue'), meta: { title: 'Подключить группу' } },
  { path: '/settings', name: 'Settings', component: () => import('../views/SettingsView.vue'), meta: { title: 'Настройки' } },
  { path: '/admin', name: 'Admin', component: () => import('../views/AdminView.vue'), meta: { title: 'Админка' } },
  { path: '/:pathMatch(.*)*', name: 'CatchAll', redirect: '/' },
]

const router = createRouter({
  // Hash-роутер ломается в Telegram: открывают https://host/?tgWebAppStartParam=... без #/ — маршрут не совпадает, экран пустой.
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach((to) => {
  const { setDashboardSection } = useDashboardSection()
  if (to.path === '/billing') {
    setDashboardSection('billing')
    return { path: '/', query: { ...to.query, section: 'billing' } }
  }
  if (to.path === '/') {
    const wanted = String(to.query?.section || '').trim().toLowerCase()
    if (wanted === 'billing' || wanted === 'partner' || wanted === 'account') {
      setDashboardSection(wanted)
    }
  }
  return true
})

export default router
