---
name: 本地服务中控
description: Windows 原生 Tk 服务导航与日志工作区
colors:
  workspace: "#f3f5f8"
  surface: "#ffffff"
  text: "#19283b"
  muted: "#526478"
  border: "#d5dde8"
  accent: "#2458b5"
  current-service: "#173e73"
  current-secondary: "#d6e5fa"
  navigation-hover: "#edf2fa"
  selection: "#e7effc"
  log-toolbar: "#eaf2fc"
  success: "#236848"
  start-tint: "#e5f5ed"
  warning: "#875200"
  restart-tint: "#fff3d6"
  warning-log: "#fff8e8"
  error: "#a52a37"
  stop-tint: "#fbeaec"
  error-log: "#fff1f2"
  open: "#116b78"
  open-tint: "#e1f3f5"
  scroll-thumb: "#7e8da0"
  scroll-hover: "#62748b"
typography:
  headline:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "22pt"
    fontWeight: 700
  title:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "18pt"
    fontWeight: 700
  navigation:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "11pt"
    fontWeight: 700
  body:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "10pt"
  label:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "9pt"
  log:
    fontFamily: "Consolas"
    fontSize: "11pt"
spacing:
  compact: "8px"
  regular: "12px"
  content: "16px"
  shell: "20px"
components:
  navigation:
    backgroundColor: "{colors.surface}"
    width: "288px"
  navigation-current:
    backgroundColor: "{colors.current-service}"
    textColor: "{colors.surface}"
    padding: "9px 12px"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    padding: "6px 12px"
  button-start:
    backgroundColor: "{colors.start-tint}"
    textColor: "{colors.success}"
  button-stop:
    backgroundColor: "{colors.stop-tint}"
    textColor: "{colors.error}"
  button-restart:
    backgroundColor: "{colors.restart-tint}"
    textColor: "{colors.warning}"
  button-open:
    backgroundColor: "{colors.open-tint}"
    textColor: "{colors.open}"
  tab:
    padding: "8px 16px"
  log:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    padding: "12px 16px"
---

# 本地服务中控设计系统

## Overview

采用清晰、克制的桌面操作台视觉：左侧选择和控制服务，右侧观察当前服务。保留原生 Tk 交互，优先保证状态辨认、日志阅读与小窗口可用性。设计值以 frontmatter 为准，具体实现见 `app.py`、`service_list.py`、`log_panel.py`。

## Colors

主色蓝用于全局启动、选中页签和交互焦点；深蓝用于当前服务导航项及右侧标题。白色内容区搭配浅灰工作区，正文深蓝灰，次要信息弱化。

绿色表示运行和启动，玫红表示错误和停止，琥珀表示变更、警告和重启，青色表示打开页面。状态摘要使用绿色运行数、蓝色外部服务数、琥珀变更数。日志警告与错误分别使用浅琥珀、浅红底色，工具栏使用淡蓝底色。

**The 选择优先 Rule.** 当前项始终使用深蓝底、白色名称及“当前”文字；状态色不能覆盖选中底色。离开鼠标或键盘焦点不取消选中，状态与源码变更始终保留文字说明。

## Typography

中文界面使用 Microsoft YaHei UI。当前服务标题使用 headline，应用标题使用 title，服务名称使用 navigation，正文使用 body，状态、端口与紧凑操作使用 label。日志使用 log，中文交由系统字体回退；日志级别加粗，时间和堆栈次要信息弱化，行前后各增加 2 px 间距。

## Layout

窗口默认 1180×860，最小 960×640；外边距与两栏间隔使用 shell。顶部左侧应用标题、右侧批量操作，其下为状态摘要。主体左侧固定宽度白色服务目录，右侧工作区随窗口扩展，底部保留全局说明。

服务目录独立滚动；上下键切换、Enter/空格选择。选中服务或缩小窗口时自动露出当前项及其操作。右侧依次为服务标题、类型/端口/PID、启动信息入口、运行状态、按需展开的启动信息及日志/变更页签。

“专注日志”隐藏左侧服务目录以增加日志宽度，当前服务标题与详情保留；“显示服务”恢复目录。布局以 Tk 尺寸和滚动行为适配，不使用 Web 断点。

## Elevation & Depth

无阴影。白色面板、浅灰背景、间距和少量细分隔线建立层级；不以浮起卡片或凸起边框组织服务。

## Shapes

保持 Tk 扁平矩形控件。横纵滚动条统一为 12 px，无箭头、凸起边框或纹路；浅灰轨道搭配灰蓝滑块，悬停加深，拖动使用 muted，无需滚动时融入轨道。保留原生拖动、轨道点击及滚轮行为。

## Components

- **服务导航项**：每项展示名称、前后端类型或“当前”、运行状态、端口、源码变更及启停重启按钮；前端另有“打开页面”。导航按钮使用 9 pt、四边 5 px 内边距。点击动作或前端端口时先选择该服务，右侧上下文同步切换。前端端口带下划线和手型指针，按钮提供键盘入口。
- **动作按钮**：启动、停止、重启、打开页面使用各自语义色，悬停和按下加深；禁用态统一浅灰背景和 muted 文字。操作期间禁用冲突动作，停止仍可取消构建；未确认端口归属时不提供进程控制。
- **当前服务详情**：标题固定使用深蓝，不随项目或健康状态换色。“启动信息”内联展开工作目录与健康检查地址；源码变化和错误在主界面说明，不以弹窗打断阅读。外部服务明确标记“外部”，日志区说明历史输出位置。
- **页签**：“运行日志”和“变更文件”使用相同字号与内边距；选中时只改变颜色，宽高保持一致，避免切换跳动。
- **日志工具栏**：固定两行，首行显示缓冲行数、警告/错误数与专注日志入口；次行提供自动换行、复制日志和回到底部。白色日志正文支持选择复制；有选区时复制所选，否则复制全部当前日志。
- **日志阅读**：空日志明确说明服务启动后会出现输出；增量更新保留选区和历史阅读位置，重复选择当前服务不重置滚动。日志级别保留原文，ANSI 控制码仅在展示时移除，磁盘日志不改写。

## Do's and Don'ts

- **Do** 同时以持久选中底色、“当前”文字及右侧标题确认操作对象。
- **Do** 在最小窗口检查服务目录滚动、前端四个按钮和两行日志工具栏均可用。
- **Do** 用状态文字配合语义色说明运行、外部服务、失败及源码变化。
- **Don't** 恢复顶部横表或按项目给整行着色；当前服务的选择优先于状态色。
- **Don't** 因刷新、焦点离开或重复选择当前服务而清除选中或打断日志阅读。
- **Don't** 将源码变化改成弹窗或自动重启。
