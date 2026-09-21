<script setup lang="ts">
import { ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { SOURCE_TYPE_LABELS } from '@/types/source'
import type { Source, SourceCreate } from '@/types/source'

/** Props for the dialog. */
const props = defineProps<{
  visible: boolean
  source?: Source | null // null = create mode, non-null = edit mode
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'submit', val: SourceCreate): void
}>()

const formRef = ref<FormInstance>()

const form = ref({
  name: '',
  path: '',
  type: 'local' as SourceCreate['type'],
  scan_interval: 3600,
  is_active: true,
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入视频源名称', trigger: 'blur' },
    { min: 1, max: 255, message: '1 - 255 个字符', trigger: 'blur' },
  ],
  path: [
    { required: true, message: '请输入路径', trigger: 'blur' },
    { min: 1, max: 1024, message: '1 - 1024 个字符', trigger: 'blur' },
  ],
  type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  scan_interval: [
    { required: true, message: '请设置扫描间隔', trigger: 'change' },
  ],
}

// When the source prop changes, populate the form (edit mode).
watch(
  () => props.source,
  (val) => {
    if (val) {
      form.value = {
        name: val.name,
        path: val.path,
        type: val.type,
        scan_interval: val.scan_interval,
        is_active: val.is_active,
      }
    } else {
      form.value = {
        name: '',
        path: '',
        type: 'local',
        scan_interval: 3600,
        is_active: true,
      }
    }
  },
  { immediate: true },
)

const isEditing = () => !!props.source

function handleClose() {
  emit('update:visible', false)
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  emit('submit', { ...form.value })
}

const typeOptions = Object.entries(SOURCE_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}))

const pathPlaceholder = () =>
  form.value.type === 'minio' ? '例如：s3://my-videos/shows' : '例如：/mnt/videos 或 \\\\nas\\media'
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="isEditing() ? '编辑视频源' : '添加视频源'"
    width="520px"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="120px"
      label-position="right"
    >
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="例如：我的NAS" maxlength="255" />
      </el-form-item>

      <el-form-item label="类型" prop="type">
        <el-select v-model="form.type" style="width: 100%">
          <el-option
            v-for="opt in typeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="路径" prop="path">
        <el-input
          v-model="form.path"
          :placeholder="pathPlaceholder()"
          maxlength="1024"
        />
        <p v-if="form.type === 'minio'" class="path-hint">
          对象存储里的影片可以直接播放，但没有缩略图、转码和字幕（外挂与内嵌都不支持），
          需要在 backend/.env 里配置 S3 凭证。
        </p>
      </el-form-item>

      <el-form-item label="扫描间隔" prop="scan_interval">
        <el-input-number
          v-model="form.scan_interval"
          :min="60"
          :max="86400"
          :step="60"
        />
        <span class="interval-hint">秒</span>
      </el-form-item>

      <el-form-item label="启用">
        <el-switch v-model="form.is_active" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit">
        {{ isEditing() ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.interval-hint {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

/* el-form-item 的内容区是 flex 行，不换行就会挤在输入框右边。 */
.path-hint {
  width: 100%;
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
</style>
