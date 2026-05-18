import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/authStore.js'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginPage.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/RegisterPage.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: () => import('../views/ForgotPasswordPage.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/DashboardPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/interview/:id',
    name: 'InterviewRoom',
    component: () => import('../views/InterviewRoom.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/messages',
    name: 'Messages',
    component: () => import('../views/MessagePage.vue'),
  },
  {
    path: '/report/:interviewId',
    name: 'Report',
    component: () => import('../views/ReportPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/admin/questions',
    name: 'QuestionManage',
    component: () => import('../views/admin/QuestionManage.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/documents',
    name: 'DocumentUpload',
    component: () => import('../views/admin/DocumentUpload.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/monitor',
    name: 'AdminMonitor',
    component: () => import('../views/admin/AdminMonitor.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    next('/login')
    return
  }

  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    next('/dashboard')
    return
  }

  if ((to.path === '/login' || to.path === '/register') && authStore.isLoggedIn) {
    next('/dashboard')
    return
  }

  next()
})

export default router
