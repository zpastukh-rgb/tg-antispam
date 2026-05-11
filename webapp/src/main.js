import './bootstrapLocation.js'
import './themeBootstrap.js'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { installRouteTransitionLoader } from './composables/useRouteTransitionLoader.js'
import './styles.css'

installRouteTransitionLoader(router)

// До mount: на части клиентов initData появляется только после ready(); иначе первые запросы к API без подписи → 401 и «приложение не открывается».
const tg = window.Telegram?.WebApp
if (tg && typeof tg.ready === 'function') {
  try {
    tg.ready()
  } catch {
    //
  }
  try {
    if (typeof tg.expand === 'function') tg.expand()
  } catch {
    //
  }
}

const app = createApp(App)
app.use(router)
app.mount('#app')
