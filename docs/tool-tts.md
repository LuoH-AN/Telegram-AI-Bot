# tts 工具归档

## 工具定位
`tts` 是旧工具系统里唯一直接产生音频 side effect 的工具。它并不把音频直接通过工具返回给模型，而是：
- 先生成音频
- 再放进进程内 pending 队列
- 最后由 Telegram / Discord 主链路在对话结束后投递语音消息

对应实现：`tools/tts.py`

## 对外暴露的函数
### 1. `tts_speak`
参数：
- `text`
- `voice_name`
- `style`
- `rate`
- `pitch`
- `output_format`

### 2. `tts_list_voices`
参数：
- `locale`
- `limit`

## 执行模型
### `tts_speak`
1. 校验文本不能为空
2. 文本长度限制 2000 字符
3. 从用户设置读取默认值：
   - `tts_voice`
   - `tts_style`
   - `tts_endpoint`
4. 若当前调用显式传入 `voice_name/style`，优先采用显式值
5. 调 `get_voice_list()` 拉取音色清单
6. 检查 `voice_name` 是否存在
7. 若不存在则回退到默认音色，并记录 fallback note
8. 调 `synthesize_voice()` 真正生成音频
9. 根据 `output_format` 推断文件扩展名
10. 把音频二进制和元信息放进 `_PENDING_JOBS[user_id]`
11. 返回一段文本说明“已生成并入队”

### `tts_list_voices`
1. 拉取 voice list
2. 按 locale 过滤
3. 控制最多返回 50 条
4. 格式化为纯文本列表

## 关键结构：pending 队列
### 内部数据结构
- `_PENDING_JOBS: dict[int, list[dict]]`
- `_PENDING_LOCK`

### 作用
工具本身不直接发 Telegram/Discord 语音，而是把结果挂到：
- `audio`
- `filename`
- `caption`

由外层聊天 handler 在本轮模型回复结束后再调用：
- `drain_pending_tts_jobs(user_id)`

这样可以把“模型继续回答”和“媒体发送”解耦。

## 依赖关系
- `services.tts.synthesize_voice`
- `services.tts.get_voice_list`
- 用户设置系统
- 外层 delivery 逻辑

## 设计特点
### 1. side effect 不经模型上下文回流
模型拿到的只是文本确认，不会拿到音频本体。

### 2. 显式参数优先于用户默认设置
这是比较合理的优先级设计：
- 当次意图 > 用户全局默认

### 3. 音色存在性校验
会在生成前验证 voice 是否真的存在，避免直接请求失败。

### 4. 平台发送被延后到聊天外层
这是它和普通文字工具最大的差别。

## 如果以后要恢复
至少需要恢复四块：
1. schema：`tts_speak` / `tts_list_voices`
2. 生成逻辑：`synthesize_voice()` 调用
3. pending 队列：`_PENDING_JOBS` + drain
4. 主消息链路中的语音投递步骤

## 恢复时建议
如果未来重建，建议保留“生成”和“发送”分离：
- Tool 层只产出媒体任务
- Platform handler 层负责真正发送

因为这能明显降低平台耦合，也方便以后支持：
- Telegram voice
- Discord file
- Web 下载链接
等不同投递方式。
