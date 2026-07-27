<script setup lang="ts">
import { onMounted } from 'vue'
import MainLayout from '@/layouts/MainLayout.vue'
import { initTheme } from '@/composables/useTheme'

onMounted(() => {
  initTheme()
})
</script>

<template>
  <MainLayout />
</template>
