import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Devices from '../views/Devices.vue'
import Alerts from '../views/Alerts.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/devices', component: Devices },
  { path: '/alerts', component: Alerts }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
