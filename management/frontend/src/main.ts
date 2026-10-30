import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { ElAlert, ElButton, ElConfigProvider, ElDrawer, ElEmpty, ElInput, ElPagination, ElSkeleton, ElTable, ElTableColumn, ElTag } from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import RunIndex from './views/RunIndex.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: RunIndex },
    { path: '/runs/:run_id', component: () => import('./views/RunView.vue') },
    { path: '/users/:account_id?', component: () => import('./views/UserView.vue') },
    { path: '/:pathMatch(.*)*', component: () => import('./views/NotFound.vue') },
  ],
  scrollBehavior(to, from) { return to.path === from.path ? undefined : { top: 0 } },
})
const app = createApp(App).use(router)
for (const [name, component] of Object.entries({ ElAlert, ElButton, ElConfigProvider, ElDrawer, ElEmpty, ElInput, ElPagination, ElSkeleton, ElTable, ElTableColumn, ElTag })) {
  app.component(name, component)
}
app.mount('#app')
