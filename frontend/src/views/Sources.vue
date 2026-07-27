<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import SourceCard from '@/components/SourceCard.vue'
import SourceForm from '@/components/SourceForm.vue'
import api from '@/api/client'
import {
  listSources,
  createSource,
  updateSource,
  deleteSource,
} from '@/api/sources'
import type { Source, SourceCreate } from '@/types/source'

const sources = ref<Source[]>([])
const loading = ref(false)
const scanning = ref(false)

// Dialog state
const showForm = ref(false)
const editingSource = ref<Source | null>(null)

async function loadSources() {
  loading.value = true
  try {
    sources.value = await listSources()
  } catch (err: unknown) {
    ElMessage.error(`Failed to load sources: ${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  editingSource.value = null
  showForm.value = true
}

function openEditDialog(source: Source) {
  editingSource.value = source
  showForm.value = true
}

async function handleSubmit(data: SourceCreate) {
  try {
    if (editingSource.value) {
      await updateSource(editingSource.value.id, data)
      ElMessage.success('视频源已更新')
    } else {
      await createSource(data)
      ElMessage.success('视频源已创建')
    }
    showForm.value = false
    await loadSources()
  } catch (err: unknown) {
    ElMessage.error(`Operation failed: ${err instanceof Error ? err.message : err}`)
  }
}

async function handleDelete(source: Source) {
  try {
    await ElMessageBox.confirm(
      `确定要删除视频源 "${source.name}" 吗？`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await deleteSource(source.id)
    ElMessage.success('视频源已删除')
    await loadSources()
  } catch (err: unknown) {
    // User cancelled or API error
    if (err !== 'cancel' && !(err instanceof Error && err.message === 'cancel')) {
      ElMessage.error(`Delete failed: ${err instanceof Error ? err.message : err}`)
    }
  }
}

async function handleScanAll() {
  scanning.value = true
  try {
    const result = await api.post('/api/scan/all')
    ElMessage.success(`扫描完成: 发现 ${result.data.total_files} 个文件, ${result.data.total_new_videos} 个新视频`)
    await loadSources()
  } catch (err: unknown) {
    ElMessage.error(`扫描失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    scanning.value = false
  }
}

async function handleScanSource(source: Source) {
  try {
    const result = await api.post(`/api/sources/${source.id}/scan`)
    ElMessage.success(`扫描 "${source.name}" 完成: 发现 ${result.data.files_found} 个文件, ${result.data.new_videos} 个新视频`)
    await loadSources()
  } catch (err: unknown) {
    ElMessage.error(`扫描失败: ${err instanceof Error ? err.message : err}`)
  }
}

onMounted(loadSources)
</script>

<template>
  <div class="sources-page">
    <div class="page-header">
      <h2>视频源管理</h2>
      <div class="header-actions">
        <el-button type="success" :icon="Search" :loading="scanning" @click="handleScanAll">
          扫描全部
        </el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">
          添加视频源
        </el-button>
      </div>
    </div>

    <el-empty v-if="!loading && sources.length === 0" description="尚未配置视频源。">
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">
        添加第一个视频源
      </el-button>
    </el-empty>

    <div v-loading="loading" class="source-grid">
      <SourceCard
        v-for="source in sources"
        :key="source.id"
        :source="source"
        @edit="openEditDialog"
        @delete="handleDelete"
        @scan="handleScanSource"
      />
    </div>

    <SourceForm
      v-model:visible="showForm"
      :source="editingSource"
      @submit="handleSubmit"
    />
  </div>
</template>

<style scoped>
.sources-page {
  padding: 4px 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}
</style>
