# cron 工具归档

## 工具定位
`cron` 是旧工具系统里负责“让模型自己创建/管理定时任务”的工具层。它和 `services/cron.py` 配合：
- 工具层负责增删查手动触发
- 服务层负责真正调度与执行

对应实现：`tools/cron.py`

## 对外暴露的函数
- `cron_create`
- `cron_list`
- `cron_delete`
- `cron_run`

## 主要能力
### 1. `cron_create`
创建任务，需要：
- `name`
- `cron_expression`
- `prompt`

工具层只做非常轻的 cron 校验：
- 必须正好 5 个字段

真正任务会写入 cache，再由同步线程入库。

### 2. `cron_list`
从缓存读取当前用户全部任务，展示：
- 名称
- enabled 状态
- cron 表达式
- prompt 预览
- 最近执行时间

### 3. `cron_delete`
按名称删除任务。

### 4. `cron_run`
立即触发某个任务，内部转调 `services.cron.run_cron_task()`。

## 设计特点
### 1. 工具层只做管理，不做调度
真正的调度循环并不在这里，而是在 `services/cron.py`。

### 2. 基于用户作用域
任务按 `user_id` 隔离，每个用户最多 10 个。

### 3. 与平台消息发送联动
文案明确说明：定时任务结果会发送回当前平台（Telegram / Discord）。

## 与服务层的分工
- `tools/cron.py`：面向模型的 tool API
- `services/cron.py`：轮询、匹配 cron、调用 AI、发送结果

这是典型的“管理入口”和“执行引擎”拆分。

## 如果以后要恢复
至少要恢复：
1. 4 个 schema
2. cache 中 cron task 的增删改查能力
3. `services/cron.py` 调度线程
4. 平台消息发送桥接

## 恢复时建议
如果未来不再恢复完整 function calling，也可以只保留：
- 用户命令创建 cron
- 后台服务执行

即保留 cron 能力本身，但不再让模型自由创建任务。这样会更安全、也更可控。
