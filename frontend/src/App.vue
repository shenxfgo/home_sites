<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { initTheme } from '@/composables/useTheme'

onMounted(() => {
  initTheme()
})

// 登录页不属于任何导航：它自己就是完整的一屏。
const route = useRoute()
const barePage = computed(() => route.meta.public === true)
</script>

<template>
  <MainLayout v-if="!barePage" />
  <router-view v-else />
</template>
