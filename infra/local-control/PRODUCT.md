# 本地服务中控

<!-- impeccable:product-schema 1 -->

## Platform

Windows 桌面，Python Tkinter。

## Stack

用户确认 Python 一体化客户端和 Tkinter 精简方案；使用标准库，不拆分前后端。

## Users

在本工作区通过 IDEA / PyCharm 开发和联调的开发者。

## Product Purpose

统一启动、停止和观察三个后端及两个前端；查看日志、源码变化并自行决定重启，减少在 IDE 和终端之间切换。

## Constraints

源码变更只能在主界面提示，不弹窗、不自动重启。沿用产品启动配置；可控制客户端自建进程和已确认身份的外部服务，关闭窗口仅清理自建进程。运行状态必须来自实际进程和 HTTP 探测。
