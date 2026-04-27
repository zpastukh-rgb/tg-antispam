import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import ChatsView from '../views/ChatsView.vue'
import ProtectionView from '../views/ProtectionView.vue'
import ReportsView from '../views/ReportsView.vue'
import ConnectView from '../views/ConnectView.vue'
import ReferralView from '../views/ReferralView.vue'
import GiftsView from '../views/GiftsView.vue'
import CommunityView from '../views/CommunityView.vue'
import TokensView from '../views/TokensView.vue'
import HistoryView from '../views/HistoryView.vue'
import AdminView from '../views/AdminView.vue'
import { useDashboardSection } from '../composables/useDashboardSection'

const routes = [
  { path: '/', name: 'Dashboard', component: DashboardView, meta: { title: 'Главная' } },
  { path: '/chats', name: 'Chats', component: ChatsView, meta: { title: 'Подключённые чаты' } },
  { path: '/protection', name: 'Protection', component: ProtectionView, meta: { title: 'Защита' } },
  { path: '/reports', name: 'Reports', component: ReportsView, meta: { title: 'Отчёты' } },
  { path: '/billing', name: 'Billing', redirect: '/' },
  { path: '/tokens', name: 'Tokens', component: TokensView, meta: { title: 'Токены' } },
  { path: '/history', name: 'History', component: HistoryView, meta: { title: 'История средств' } },
  { path: '/referral', name: 'Referral', component: ReferralView, meta: { title: 'Реферальная программа' } },
  { path: '/gifts', name: 'Gifts', component: GiftsView, meta: { title: 'Подарки' } },
  { path: '/community', name: 'Community', component: CommunityView, meta: { title: 'Сообщество' } },
  { path: '/connect', name: 'Connect', component: ConnectView, meta: { title: 'Подключить группу' } },
  { path: '/admin', name: 'Admin', component: AdminView, meta: { title: 'Админка' } },
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
