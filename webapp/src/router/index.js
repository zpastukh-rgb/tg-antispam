import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: 'Главная' } },
  { path: '/chats', name: 'Chats', component: () => import('../views/ChatsView.vue'), meta: { title: 'Подключённые чаты' } },
  { path: '/protection', name: 'Protection', component: () => import('../views/ProtectionView.vue'), meta: { title: 'Защита' } },
  { path: '/reports', name: 'Reports', component: () => import('../views/ReportsView.vue'), meta: { title: 'Отчёты' } },
  { path: '/billing', name: 'Billing', component: () => import('../views/BillingView.vue'), meta: { title: 'Тариф и оплата' } },
  { path: '/connect', name: 'Connect', component: () => import('../views/ConnectView.vue'), meta: { title: 'Подключить группу' } },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
