# 更新日志

## 2026-07-27

### 新增功能

#### 后端
- **Settings API** - 应用设置的增删改查接口
- **Setting 模型** - 存储应用配置的数据库模型

#### 前端
- **Settings 页面** - 应用设置界面，支持配置：
  - 扫描设置（自动扫描开关、间隔时间）
  - 转码设置（默认格式）
  - 缩略图设置（宽度、高度）
  - 界面设置（主题切换）

- **深色模式** - 完整的深色模式支持：
  - `useTheme` composable - 主题管理逻辑
  - `theme.css` - 深色模式样式定义
  - 支持浅色/深色/跟随系统三种模式
  - 主题保存到 localStorage

- **中文化** - 所有界面文字统一改为中文：
  - 侧边栏菜单
  - 页面标题
  - 按钮文字
  - 表单标签
  - 提示信息
  - 确认对话框

- **标签编辑功能** - 视频详情页支持添加/删除标签

- **扫描功能** - 视频源页面添加扫描按钮：
  - 扫描全部视频源
  - 扫描单个视频源

- **文档更新** - 新增和更新项目文档：
  - 创建 README.md - 项目说明文档
  - 更新 CLAUDE.md - 添加文档更新规范
  - 创建 CHANGELOG.md - 更新日志

### 修复问题

- **历史 API 500 错误** - 修复 `played_at` 字段类型不匹配问题
- **Settings API 404 错误** - 修复 API 路径重复 `/api` 前缀问题

### 文件变更

#### 新增文件
- `backend/src/models/setting.py` - Setting 数据模型
- `backend/src/api/settings.py` - Settings API 端点
- `frontend/src/api/settings.ts` - 前端 Settings API 模块
- `frontend/src/views/Settings.vue` - Settings 页面
- `frontend/src/views/Transcode.vue` - 转码页面
- `frontend/src/composables/useTheme.ts` - 主题管理 composable
- `frontend/src/styles/theme.css` - 深色模式样式
- `CHANGELOG.md` - 更新日志
- `README.md` - 项目说明文档

#### 修改文件
- `backend/src/main.py` - 注册 Settings 路由
- `backend/src/models/__init__.py` - 导入 Setting 模型
- `backend/src/api/history.py` - 修复 played_at 字段类型
- `frontend/src/main.ts` - 导入主题样式
- `frontend/src/App.vue` - 初始化主题
- `frontend/src/router/index.ts` - 添加转码页面路由
- `frontend/src/views/VideoDetail.vue` - 添加转码按钮和标签编辑功能
- `frontend/src/views/Sources.vue` - 添加扫描按钮
- `frontend/src/components/SourceCard.vue` - 添加扫描按钮
- `frontend/src/layouts/MainLayout.vue` - 深色模式支持
- `frontend/src/styles/global.css` - 全局样式
- `CLAUDE.md` - 更新项目文档，添加文档更新规范
- `frontend/CLAUDE.md` - 更新前端文档
- `.superpowers/sdd/progress.md` - 更新进度

## 2026-07-26

### 初始版本

- 后端基础框架搭建
- 前端基础框架搭建
- 数据模型定义
- API 端点实现
- 基础前端页面
