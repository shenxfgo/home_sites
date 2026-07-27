<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, CollectionTag } from '@element-plus/icons-vue'
import { listTags, createTag, updateTag, deleteTag } from '@/api/tags'
import type { Tag, TagCreate, TagUpdate } from '@/types/video'

const tags = ref<Tag[]>([])
const loading = ref(false)

// Dialog state
const showDialog = ref(false)
const editingTag = ref<Tag | null>(null)
const formData = ref<TagCreate>({ name: '', color: '#409eff' })
const submitting = ref(false)

// Preset colors for quick selection
const presetColors = [
  '#409eff',
  '#67c23a',
  '#e6a23c',
  '#f56c6c',
  '#909399',
  '#00c9a7',
  '#c4b5fd',
  '#fb923c',
  '#f472b6',
  '#38bdf8',
]

async function loadTags() {
  loading.value = true
  try {
    tags.value = await listTags()
  } catch (err: unknown) {
    ElMessage.error(`Failed to load tags: ${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  editingTag.value = null
  formData.value = { name: '', color: '#409eff' }
  showDialog.value = true
}

function openEditDialog(tag: Tag) {
  editingTag.value = tag
  formData.value = { name: tag.name, color: tag.color }
  showDialog.value = true
}

async function handleSubmit() {
  if (!formData.value.name.trim()) {
    ElMessage.warning('Please enter a tag name')
    return
  }

  submitting.value = true
  try {
    if (editingTag.value) {
      const updateData: TagUpdate = {}
      if (formData.value.name !== editingTag.value.name) {
        updateData.name = formData.value.name
      }
      if (formData.value.color !== editingTag.value.color) {
        updateData.color = formData.value.color
      }
      if (Object.keys(updateData).length > 0) {
        await updateTag(editingTag.value.id, updateData)
        ElMessage.success('Tag updated')
      }
    } else {
      await createTag(formData.value)
      ElMessage.success('Tag created')
    }
    showDialog.value = false
    await loadTags()
  } catch (err: unknown) {
    ElMessage.error(`Operation failed: ${err instanceof Error ? err.message : err}`)
  } finally {
    submitting.value = false
  }
}

async function handleDelete(tag: Tag) {
  try {
    await ElMessageBox.confirm(
      `Are you sure you want to delete "${tag.name}"? This will also remove the tag from all associated videos.`,
      'Confirm Delete',
      { confirmButtonText: 'Delete', cancelButtonText: 'Cancel', type: 'warning' },
    )
    await deleteTag(tag.id)
    ElMessage.success('Tag deleted')
    await loadTags()
  } catch (err: unknown) {
    if (err !== 'cancel' && !(err instanceof Error && err.message === 'cancel')) {
      ElMessage.error(`Delete failed: ${err instanceof Error ? err.message : err}`)
    }
  }
}

function selectPresetColor(color: string) {
  formData.value.color = color
}

onMounted(loadTags)
</script>

<template>
  <div class="tags-page">
    <div class="page-header">
      <h2>Tag Management</h2>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">
        Add Tag
      </el-button>
    </div>

    <el-empty v-if="!loading && tags.length === 0" description="No tags created yet.">
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">
        Create Your First Tag
      </el-button>
    </el-empty>

    <div v-loading="loading" class="tags-grid">
      <div
        v-for="tag in tags"
        :key="tag.id"
        class="tag-card"
      >
        <div class="tag-card-content">
          <div class="tag-info">
            <span class="tag-color-dot" :style="{ backgroundColor: tag.color }" />
            <span class="tag-name">{{ tag.name }}</span>
          </div>
          <div class="tag-meta">
            <el-tag size="small" type="info">
              <el-icon><CollectionTag /></el-icon>
              {{ tag.video_count ?? 0 }} videos
            </el-tag>
          </div>
        </div>
        <div class="tag-actions">
          <el-button
            :icon="Edit"
            text
            type="primary"
            size="small"
            @click="openEditDialog(tag)"
          >
            Edit
          </el-button>
          <el-button
            :icon="Delete"
            text
            type="danger"
            size="small"
            @click="handleDelete(tag)"
          >
            Delete
          </el-button>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showDialog"
      :title="editingTag ? 'Edit Tag' : 'Create Tag'"
      width="480px"
      :close-on-click-modal="false"
      @closed="showDialog = false"
    >
      <el-form label-position="top">
        <el-form-item label="Tag Name" required>
          <el-input
            v-model="formData.name"
            placeholder="Enter tag name"
            maxlength="100"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="Color">
          <div class="color-section">
            <el-color-picker
              v-model="formData.color"
              :predefine="presetColors"
              show-alpha
              color-format="hex"
            />
            <div class="preset-colors">
              <span
                v-for="color in presetColors"
                :key="color"
                class="preset-color"
                :class="{ active: formData.color === color }"
                :style="{ backgroundColor: color }"
                @click="selectPresetColor(color)"
              />
            </div>
          </div>
        </el-form-item>

        <el-form-item label="Preview">
          <div class="tag-preview">
            <span class="preview-dot" :style="{ backgroundColor: formData.color }" />
            <span class="preview-name">{{ formData.name || 'Tag Name' }}</span>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ editingTag ? 'Update' : 'Create' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.tags-page {
  padding: 4px 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.tags-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.tag-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.tag-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.tag-card-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.tag-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tag-color-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.tag-meta {
  flex-shrink: 0;
}

.tag-actions {
  display: flex;
  gap: 4px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 10px;
}

.color-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.preset-colors {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.preset-color {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.2s, transform 0.2s;
}

.preset-color:hover {
  transform: scale(1.15);
}

.preset-color.active {
  border-color: var(--el-text-color-primary);
}

.tag-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.preview-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.preview-name {
  font-size: 14px;
  color: var(--el-text-color-primary);
}
</style>
