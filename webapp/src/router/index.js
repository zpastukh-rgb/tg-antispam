import { createRouter, createWebHashHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import ChatsView from '../views/ChatsView.vue'
import ProtectionView from '../views/ProtectionView.vue'
import ReportsView from '../views/ReportsView.vue'
import BillingView from '../views/BillingView.vue'
import ConnectView from '../views/ConnectView.vue'

const routes = [
  { path: '/', name: 'Dashboard', component: DashboardView, meta: { title: 'Главная' } },
  { path: '/chats', name: 'Chats', component: ChatsView, meta: { title: 'Подключённые чаты' } },
  { path: '/protection', name: 'Protection', component: ProtectionView, meta: { title: 'Защита' } },
  { path: '/reports', name: 'Reports', component: ReportsView, meta: { title: 'Отчёты' } },
  { path: '/billing', name: 'Billing', component: BillingView, meta: { title: 'Тариф и оплата' } },
  { path: '/connect', name: 'Connect', component: ConnectView, meta: { title: 'Подключить группу' } },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
