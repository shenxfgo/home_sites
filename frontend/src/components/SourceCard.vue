<script setup lang="ts">
import { computed } from 'vue'
import { VideoCamera, Connection, Box, Search } from '@element-plus/icons-vue'
import type { Source, SourceType } from '@/types/source'
import { SOURCE_TYPE_LABELS } from '@/types/source'

const props = defineProps<{
  source: Source
}>()

const emit = defineEmits<{
  (e: 'edit', source: Source): void
  (e: 'delete', source: Source): void
  (e: 'scan', source: Source): void
}>()

const typeIcon: Record<SourceType, typeof VideoCamera> = {
  local: VideoCamera,
  nas: Connection,
  minio: Box,
}

const icon = computed(() => typeIcon[props.source.type])
const typeLabel = computed(() => SOURCE_TYPE_LABELS[props.source.type])

const formattedInterval = computed(() => {
  const s = props.source.scan_interval
  if (s < 3600) return `${Math.round(s / 60)}m`
  return `${(s / 3600).toFixed(1)}h`
})

function formatDateTime(iso: string | null): string {
  if (!iso) return '从未'
  return new Date(iso).toLocaleString()
}
</script>

<template>
  <el-card shadow="hover" class="source-card">
    <div class="card-header">
      <div class="card-title">
        <el-icon class="type-icon" :size="20">
          <component :is="icon" />
        </el-icon>
        <span class="source-name">{{ source.name }}</span>
      </div>
      <el-tag :type="source.is_active ? 'success' : 'info'" size="small">
        {{ source.is_active ? '启用' : '停用' }}
      </el-tag>
    </div>

    <div class="card-body">
      <div class="info-row">
        <span class="label">类型</span>
        <span>{{ typeLabel }}</span>
      </div>
      <div class="info-row">
        <span class="label">路径</span>
        <span class="path-value" :title="source.path">{{ source.path }}</span>
      </div>
      <div class="info-row">
        <span class="label">扫描</span>
        <span>每 {{ formattedInterval }}</span>
      </div>
      <div class="info-row">
        <span class="label">上次扫描</span>
        <span>{{ formatDateTime(source.last_scan_at) }}</span>
      </div>
    </div>

    <div class="card-footer">
      <el-button text type="success" :icon="Search" @click="emit('scan', source)">
        扫描
      </el-button>
      <el-button text type="primary" @click="emit('edit', source)">
        编辑
      </el-button>
      <el-button text type="danger" @click="emit('delete', source)">
        删除
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.source-card {
  display: flex;
  flex-direction: column;
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border) !important;
  border-radius: 20px !important;
  box-shadow: var(--glass-shadow) !important;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.25s ease;
}

.source-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--glass-shadow-hover) !important;
}

.source-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 18px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-glass);
}

.type-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: var(--grad-primary);
  color: #fff !important;
  box-shadow: 0 4px 12px rgba(124, 108, 255, 0.35);
}

.card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  line-height: 1.6;
}

.info-row .label {
  color: var(--el-text-color-secondary);
}

.path-value {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}

.card-footer {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
