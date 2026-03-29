import './bootstrapLocation.js'
import './themeBootstrap.js'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './styles.css'

const app = createApp(App)
app.use(router)
app.mount('#app')

const tg = window.Telegram?.WebApp
if (tg && typeof tg.ready === 'function') {
  tg.ready()
  try {
    if (typeof tg.expand === 'function') tg.expand()
  } catch {
    //
  }
}
