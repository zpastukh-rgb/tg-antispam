// usePremiumLock — глобальное состояние модалки «Эта функция доступна с Premium».
//
// Используется для всех мест, где Premium-фича заблокирована для FREE-юзера
// (гранулярные фильтры, кастомное приветствие, авто-отчёты, audit log, и т.д.).
//
// Архитектура:
//  - один общий ref `lockState` хранит текущую открытую фичу и её локализованные
//    параметры (title / description).
//  - useDashboardMe() (опционально) подмешивает свежий me для решения, какую CTA
//    показывать: «🚀 Попробовать 7 дней бесплатно» (trial_eligible) или
//    «👑 Оформить Premium» (платное продление).
//  - PremiumLockModal.vue (один экземпляр в App.vue) подписывается на `lockState`.
//  - `usePremiumLock()` экспортирует API openLock / closeLock / isLockedFor.

import { ref, computed } from 'vue'

const _open = ref(false)
const _feature = ref(null)       // ключ фичи, например 'granular_filters'
const _titleKey = ref(null)      // i18n-ключ заголовка модалки
const _descriptionKey = ref(null)// i18n-ключ описания модалки
const _meSnapshot = ref(null)    // me на момент открытия модалки (для CTA-логики)

function openLock(opts = {}) {
  const feat = opts.feature || 'generic'
  _feature.value = feat
  _titleKey.value = opts.titleKey || 'premium_lock.title'
  // Короткая одна строка под заголовком; длинный pitch — в биллинге, не здесь.
  _descriptionKey.value = opts.descriptionKey || `premium_lock.feature_desc_short.${feat}`
  _meSnapshot.value = opts.me || null
  _open.value = true
}

function closeLock() {
  _open.value = false
  // _feature и ключи оставляем — модалка корректно завершит анимацию закрытия.
}

export function usePremiumLock() {
  return {
    isOpen: computed(() => _open.value),
    feature: computed(() => _feature.value),
    titleKey: computed(() => _titleKey.value),
    descriptionKey: computed(() => _descriptionKey.value),
    me: computed(() => _meSnapshot.value),
    openLock,
    closeLock,
  }
}
