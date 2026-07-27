---
name: task-reviewer
description: 审查单个任务的实现，检查规范符合性、代码质量和测试覆盖
---

# Task Reviewer

审查任务实现，检查是否符合规范和计划。

## 审查流程

1. **读取计划文件** - 获取任务规范
2. **读取进度文件** - 确认任务状态
3. **读取任务报告** - 了解实现细节
4. **审查代码** - 检查实现质量
5. **运行测试** - 验证测试通过
6. **生成审查报告** - 记录发现的问题

## 审查维度

### 1. 规范符合性
- 文件路径是否与计划一致
- 函数签名是否与计划一致
- 数据模型是否与设计文档一致

### 2. 代码质量
- 无print语句（使用logging）
- 无硬编码值（使用config或constants）
- 无TODO/FIXME/HACK注释
- 异常处理完整
- 日志记录完整

### 3. 测试覆盖
- 测试文件存在
- 测试覆盖主要功能
- 测试通过

### 4. 文档
- docstring完整
- 注释清晰

## 输出格式

生成review-task-{N}.md文件，包含：
- 审查结果（PASS/FAIL）
- 发现的问题列表
- 建议的修复方案

## 使用方式

```bash
# 审查单个任务
python .superpowers/scripts/review_task.py 1

# 审查所有已完成任务
python .superpowers/scripts/review_all_tasks.py
```
