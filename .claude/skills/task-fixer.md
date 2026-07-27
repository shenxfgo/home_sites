---
name: task-fixer
description: 修复task-reviewer发现的问题
---

# Task Fixer

修复task-reviewer发现的问题。

## 修复流程

1. **读取审查报告** - 了解问题详情
2. **分析问题** - 确定修复方案
3. **实施修复** - 修改代码
4. **运行测试** - 验证修复
5. **提交修复** - 创建新commit
6. **更新进度** - 标记问题已修复

## 修复策略

### 1. 路径不一致
- 创建正确的目录结构
- 移动文件到正确位置
- 更新所有引用

### 2. 代码质量问题
- 替换print为logging
- 提取硬编码为常量
- 添加异常处理
- 完善日志记录

### 3. 测试问题
- 修复失败的测试
- 添加缺失的测试
- 提高测试覆盖率

### 4. 文档问题
- 添加docstring
- 完善注释

## 输出格式

生成fix-task-{N}.md文件，包含：
- 修复的问题列表
- 修改的文件
- 新增的commit

## 使用方式

```bash
# 修复指定任务的问题
python .superpowers/scripts/fix_task.py 1

# 修复所有任务的问题
python .superpowers/scripts/fix_all_tasks.py
```
