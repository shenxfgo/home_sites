<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  createUser,
  listUsers,
  resetUserPassword,
  revokeUserSessions,
  setUserRole,
  setUserStatus,
  type NewUser,
} from '@/api/users'
import { useAuth } from '@/composables/useAuth'
import type { AdminUser, UserRole } from '@/types/auth'

const { user } = useAuth()

const users = ref<AdminUser[]>([])
const loading = ref(false)

const showCreate = ref(false)
const submitting = ref(false)
const emptyForm = (): NewUser => ({ username: '', password: '', role: 'member', display_name: '' })
const form = ref<NewUser>(emptyForm())

const roleOptions: { label: string; value: UserRole }[] = [
  { label: '管理员', value: 'owner' },
  { label: '成员', value: 'member' },
]

function isSelf(row: AdminUser): boolean {
  return row.id === user.value?.id
}

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—'
}

async function loadUsers() {
  loading.value = true
  try {
    users.value = await listUsers()
  } catch (err: unknown) {
    ElMessage.error(`加载账号失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!form.value.username.trim() || !form.value.password) {
    ElMessage.warning('账号和密码都要填')
    return
  }
  submitting.value = true
  try {
    await createUser({
      ...form.value,
      username: form.value.username.trim(),
      display_name: form.value.display_name?.trim() || null,
    })
    ElMessage.success('账号已创建')
    showCreate.value = false
    form.value = emptyForm()
    await loadUsers()
  } catch (err: unknown) {
    ElMessage.error(`创建失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    submitting.value = false
  }
}

// 每一个改动都整表重载：服务端还会顺带踢会话、改设备数，只更新本地一行会显示假状态。
async function applyRole(row: AdminUser, role: UserRole) {
  try {
    await setUserRole(row.id, role)
    ElMessage.success(`${row.username} 已设为${role === 'owner' ? '管理员' : '成员'}`)
  } catch (err: unknown) {
    ElMessage.error(`改角色失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    await loadUsers()
  }
}

async function applyStatus(row: AdminUser, isActive: boolean) {
  try {
    await setUserStatus(row.id, isActive)
    ElMessage.success(isActive ? '账号已启用' : '账号已停用，该账号的所有浏览器都已退出')
  } catch (err: unknown) {
    ElMessage.error(`操作失败: ${err instanceof Error ? err.message : err}`)
  } finally {
    await loadUsers()
  }
}

async function handleResetPassword(row: AdminUser) {
  let password: string
  try {
    const result = await ElMessageBox.prompt(
      `为 ${row.username} 设置新密码。该账号当前登录的所有浏览器都会被退出。`,
      '重置密码',
      {
        inputType: 'password',
        inputPlaceholder: '至少 8 位',
        confirmButtonText: '重置',
        cancelButtonText: '取消',
        inputValidator: (value: string) => value.length >= 8 || '密码至少 8 位',
      },
    )
    password = result.value
  } catch {
    return
  }
  try {
    await resetUserPassword(row.id, password)
    ElMessage.success(`已重置 ${row.username} 的密码`)
    await loadUsers()
  } catch (err: unknown) {
    ElMessage.error(`重置失败: ${err instanceof Error ? err.message : err}`)
  }
}

async function handleRevokeSessions(row: AdminUser) {
  try {
    await ElMessageBox.confirm(
      `退出 ${row.username} 的所有浏览器？本人需要重新登录才能继续观看。`,
      '踢下线',
      { confirmButtonText: '退出登录', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const revoked = await revokeUserSessions(row.id)
    ElMessage.success(`已退出 ${revoked} 个设备`)
    await loadUsers()
  } catch (err: unknown) {
    ElMessage.error(`操作失败: ${err instanceof Error ? err.message : err}`)
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="users-page">
    <div class="page-header">
      <h2>用户管理</h2>
      <el-button type="primary" :icon="Plus" @click="showCreate = true">新建账号</el-button>
    </div>

    <p class="page-note">
      管理员可以改动视频源、系统设置和其他账号；成员只能看片、收藏、建自己的片单。
      停用的账号会立即在所有浏览器退出，历史与收藏都会保留。
    </p>

    <el-table v-loading="loading" :data="users" class="users-table">
      <el-table-column label="账号" min-width="180">
        <template #default="{ row }">
          <div class="cell-account">
            <span class="cell-username">{{ row.username }}</span>
            <span v-if="row.display_name" class="cell-display">{{ row.display_name }}</span>
            <em v-if="isSelf(row)" class="cell-self">本人</em>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="角色" width="130">
        <template #default="{ row }">
          <el-select
            :model-value="row.role"
            size="small"
            @change="(role: UserRole) => applyRole(row, role)"
          >
            <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <!-- 停用自己等于把自己锁在门外，只能回命令行救，所以这一格直接不给点。 -->
          <el-switch
            :model-value="row.is_active"
            :disabled="isSelf(row)"
            :title="isSelf(row) ? '不能停用自己的账号' : undefined"
            @change="(value: boolean) => applyStatus(row, value)"
          />
        </template>
      </el-table-column>

      <el-table-column label="登录设备" width="100">
        <template #default="{ row }">{{ row.signed_in_devices }}</template>
      </el-table-column>

      <el-table-column label="最近登录" width="200">
        <template #default="{ row }">{{ formatDate(row.last_login_at) }}</template>
      </el-table-column>

      <el-table-column label="创建时间" width="200">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>

      <el-table-column label="操作" min-width="190">
        <template #default="{ row }">
          <div class="cell-actions">
            <el-button text type="primary" size="small" @click="handleResetPassword(row)">
              重置密码
            </el-button>
            <el-button
              text
              type="danger"
              size="small"
              :disabled="!row.signed_in_devices"
              @click="handleRevokeSessions(row)"
            >
              踢下线
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showCreate" title="新建账号" width="440px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="账号" required>
          <el-input v-model="form.username" placeholder="小写字母、数字或 . _ -" maxlength="64" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="form.password" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="form.display_name" placeholder="顶栏显示的名字，可留空" maxlength="64" />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="form.role">
            <el-radio v-for="item in roleOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.users-page {
  padding: 4px 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.page-note {
  margin: 0 0 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-glass-secondary);
}

.users-table {
  width: 100%;
}

.cell-account {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.cell-username {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.cell-display,
.cell-self {
  font-size: 12px;
  font-style: normal;
  color: var(--text-glass-secondary);
}

.cell-actions {
  display: flex;
  gap: 4px;
}
</style>
