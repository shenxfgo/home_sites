<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="not-found">
    <div class="glass-panel notice">
      <p class="code gradient-text">404</p>
      <h2 class="title">页面不存在</h2>
      <p class="desc">地址可能拼错了，或者这个页面还没有上线</p>
      <div class="actions">
        <el-button type="primary" @click="router.push('/')">回到首页</el-button>
        <el-button @click="router.back()">返回上一页</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  justify-content: center;
  padding: 64px 20px;
}

.notice {
  max-width: 420px;
  padding: 40px 48px;
  text-align: center;
  border-radius: 24px;
}

.code {
  margin: 0;
  font-size: 64px;
  font-weight: 800;
  line-height: 1;
}

.title {
  margin: 12px 0 4px;
  font-size: 20px;
  color: var(--text-glass);
}

.desc {
  margin: 0 0 24px;
  color: var(--text-glass-secondary);
}

.actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
