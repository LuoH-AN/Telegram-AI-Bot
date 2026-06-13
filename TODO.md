# 重构收尾待办

> 背景:`ecaec4f` 移除了 onebot / wechat 平台与 `platforms/shared` 共享层,
> 并把 telegram 平台从 `platforms/telegram/` 提升为顶层包 `telegram_bot/`。
> 本文记录这次重构后**尚未完成 / 需要确认**的事项。

## 1. [严重] 生命周期命令的导入还指向旧文件

`/stop`、`/update`、`/restart` 三个命令已经被拆分到新文件
`telegram_bot/commands/lifecycle.py`,但包入口仍然从 `basic.py` 导入它们:

```python
# telegram_bot/commands/__init__.py:3
from .basic import start, help_command, clear, stop, update, restart
```

而 `basic.py` 现在只定义 `start / help_command / clear`,不再有
`stop / update / restart`。一旦 `telegram` 依赖可用、真正加载这个包,
启动时就会抛 `ImportError`。

**修复方式**:把入口拆成两行——

```python
from .basic import start, help_command, clear
from .lifecycle import stop, update, restart
```

> 注:本地环境未安装 `telegram` 库,只能做语法编译 + 导入链推演,
> 该错误尚未在真实运行中复现。修复后请实际启动验证。

## 2. [次要] `handlers/__init__.py` 的 `__all__` 漏了 `stop`

`telegram_bot/handlers/__init__.py` 里 `stop` 已正常 import,
但 `__all__` 列表只列了 `restart / update`,漏掉了 `stop`。
不影响 `from telegram_bot.handlers import stop`(`__all__` 只作用于
`import *`),属于一致性问题,建议补上。

## 3. 运行时未端到端验证

当前环境缺少 `telegram` 等运行依赖,本次重构只通过了:

- `py_compile` 全量字节码编译(通过)
- 残留引用扫描:无 `import platforms` / `onebot` / `wechat` 残留
- 非代码文件(README、Dockerfile、.env.example 等)无旧平台引用

仍需在装好依赖的环境里实跑一次 `python -m telegram_bot`(或 `python main.py`)
确认命令注册、消息处理、媒体上传链路均正常。

## 建议处理顺序

1. 修第 1 条(阻塞启动)。
2. 顺手补第 2 条。
3. 跑一遍第 3 条做端到端确认。
