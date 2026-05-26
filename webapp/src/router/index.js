import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import ChatsView from '../views/ChatsView.vue'
import ProtectionView from '../views/ProtectionView.vue'
import ReportsView from '../views/ReportsView.vue'
import SettingsView from '../views/SettingsView.vue'
import AdminView from '../views/AdminView.vue'
import ConnectView from '../views/ConnectView.vue'
import TokensView from '../views/TokensView.vue'
import HistoryView from '../views/HistoryView.vue'
import ReferralView from '../views/ReferralView.vue'
import GiftsView from '../views/GiftsView.vue'
import CommunityView from '../views/CommunityView.vue'
import YookassaPayView from '../views/YookassaPayView.vue'
import { useDashboardSection } from '../composables/useDashboardSection'
import { api } from '../api/client'
import { prefetchReportsView } from '../utils/reportsViewCache.js'

/** Vite base './' даёт относительные ассеты; history оставляем от корня сайта. Явный префикс — через import.meta.env.BASE_URL. */
function routerHistoryBase() {
  const b = import.meta.env.BASE_URL
  if (typeof b !== 'string' || b === '' || b === './') return '/'
  return b.endsWith('/') ? b : `${b}/`
}

/**
 * Все экраны — синхронный импорт: в Telegram WebView при неверном base/static URL или рассинхроне
 * деплоя динамический import() даёт 404 на чанк → пустой router-view без явной ошибки.
 */
const routes = [
  { path: '/', name: 'Dashboard', component: DashboardView, meta: { titleKey: 'nav.dashboard' } },
  { path: '/chats', name: 'Chats', component: ChatsView, meta: { titleKey: 'nav.chats' } },
  { path: '/protection', name: 'Protection', component: ProtectionView, meta: { titleKey: 'nav.protection' } },
  { path: '/reports', name: 'Reports', component: ReportsView, meta: { titleKey: 'nav.reports' } },
  { path: '/billing', name: 'Billing', redirect: '/' },
  { path: '/tokens', name: 'Tokens', component: TokensView, meta: { titleKey: 'nav.tokens' } },
  { path: '/history', name: 'History', component: HistoryView, meta: { titleKey: 'nav.history' } },
  { path: '/referral', name: 'Referral', component: ReferralView, meta: { titleKey: 'nav.referral' } },
  { path: '/gifts', name: 'Gifts', component: GiftsView, meta: { titleKey: 'nav.gifts' } },
  { path: '/community', name: 'Community', component: CommunityView, meta: { titleKey: 'nav.community' } },
  { path: '/connect', name: 'Connect', component: ConnectView, meta: { titleKey: 'nav.connect' } },
  { path: '/settings', name: 'Settings', component: SettingsView, meta: { titleKey: 'nav.settings' } },
  { path: '/pay/yookassa', name: 'YookassaPay', component: YookassaPayView, meta: { titleKey: 'billing.checkout.title' } },
  { path: '/admin', name: 'Admin', component: AdminView, meta: { titleKey: 'nav.admin' } },
  { path: '/:pathMatch(.*)*', name: 'CatchAll', redirect: '/' },
]

const router = createRouter({
  // Hash-роутер ломается в Telegram: открывают https://host/?tgWebAppStartParam=... без #/ — маршрут не совпадает, экран пустой.
  history: createWebHistory(routerHistoryBase()),
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
    if (
      wanted === 'billing' ||
      wanted === 'partner' ||
      wanted === 'account' ||
      wanted === 'subscription' ||
      wanted === 'tokens'
    ) {
      setDashboardSection(wanted)
    }
  }
  if (to.path === '/reports') {
    void prefetchReportsView(api)
  }
  return true
})

export default router
