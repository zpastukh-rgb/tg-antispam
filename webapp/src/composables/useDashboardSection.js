import { ref } from 'vue'

const section = ref('account')
/** Открытие оплаты из модалки статистики группы (кнопка «Назад к статистике») */
const billingFromGroupStats = ref(false)

export function useDashboardSection() {
  function setDashboardSection(next) {
    section.value = next || 'account'
  }
  return {
    dashboardSection: section,
    setDashboardSection,
    billingFromGroupStats,
  }
}
