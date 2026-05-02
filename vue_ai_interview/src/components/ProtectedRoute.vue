<script setup>
import { useAuthStore } from '../stores/authStore.js'
import { useRouter } from 'vue-router'
import { onMounted } from 'vue'

const props = defineProps({
  requireAdmin: { type: Boolean, default: false }
})

const authStore = useAuthStore()
const router = useRouter()

onMounted(() => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }
  if (props.requireAdmin && !authStore.isAdmin) {
    router.push('/dashboard')
  }
})
</script>

<template>
  <slot v-if="authStore.isLoggedIn && (!requireAdmin || authStore.isAdmin)" />
</template>
