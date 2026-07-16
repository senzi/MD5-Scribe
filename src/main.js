import { createApp } from 'vue'
import App from './App.vue'
import './frontend.css'

createApp(App).mount('#app')

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js', { updateViaCache: 'none' })
      .then((registration) => registration.update())
      .catch(() => {})
  })
}
