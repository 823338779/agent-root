"""一体化桌面入口：Tk 主线程绘制，后台线程管理本地服务。"""

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
import webbrowser

from config import load_services
from log_panel import LogPanel
from service_list import ServiceList
from runtime import (ServiceRunner, RUNNING, EXTERNAL, FAILED, EXITED, UNHEALTHY, STOPPING,
                     RUNNING_EXTERNAL, UNHEALTHY_EXTERNAL)

# 文案和设计值集中定义，业务状态始终直接来自运行控制器。
TITLE = '本地服务中控'
SUBTITLE = '统一管理工作区服务 · 源码变更仅在此处提示'
FONT = 'Microsoft YaHei UI'
BACKGROUND, SURFACE, FOREGROUND = '#f3f5f8', '#ffffff', '#19283b'
MUTED, ACCENT, SELECTED = '#526478', '#2458b5', '#e7effc'
SUCCESS, WARNING, ERROR = '#236848', '#875200', '#a52a37'
BORDER = '#d5dde8'
EMPTY = ''
APP_GEOMETRY = '1180x860'
SUMMARY_LOADING = '正在读取启动配置和源码…'
FOOTER = '每 3 秒检测一次 · 已识别的外部服务支持停止 / 重启 · 关闭客户端仅停止由它启动的服务'
FOOTER_CLOSING = '正在停止受管服务并释放日志，请稍候…'
FOOTER_CLOSE_FAILED = '部分服务未能停止。请查看服务详情，处理后再次关闭窗口。'
DETAIL_EMPTY = '选择服务，查看日志和源码变更'
LOG_EXTERNAL = '此服务从外部启动，历史输出请在原 IDE 或终端查看。通过中控重启后，新日志将在这里显示。'
CHANGES_EMPTY = '未发现源码变更。服务成功重启后，将更新检测基线。'
CHANGE_RESTART = '代码已变更 · 建议重启 ({count})'
CHANGE_HMR = '代码已变更 · Vite 热更新 ({count})'
CHANGE_CLEAN = '无变更'
SCAN_FAILED = '源码检测失败'
DETAIL_TEMPLATE = '工作目录：{cwd}\n健康检查：{health}'
LOG_TAB, CHANGES_TAB = '运行日志', '变更文件'
START, STOP, RESTART, OPEN = '启动', '停止', '重启', '打开页面'
START_ALL, STOP_ALL, RESTART_CHANGED = '启动全部', '停止全部', '重启已变更'
ACTION_REJECTED = '服务正在操作，或端口归属尚未确认，请查看运行状态。'
RESTART_NONE = '当前没有需要重启的受管服务。'
ACTION_ACCEPTED = '操作已提交；进度与结果会显示在服务列表和日志中。'
LOAD_ERROR = '无法加载配置：{error}'
KEY_CLOSE = 'WM_DELETE_WINDOW'
STYLE_FRAME, STYLE_LABEL, STYLE_TITLE = 'TFrame', 'TLabel', 'Title.TLabel'
STYLE_MUTED, STYLE_BUTTON, STYLE_PRIMARY = 'Muted.TLabel', 'TButton', 'Primary.TButton'
LOADED, LOAD_FAILED, CLOSED = 'loaded', 'load-failed', 'closed'
STATE_NORMAL, STATE_DISABLED = 'normal', 'disabled'
END, START_INDEX = 'end', '1.0'
NEWLINE = '\n'
LOG_EXPAND, LOG_RESTORE = '专注日志', '显示服务'
INFO_SHOW, INFO_HIDE = '启动信息', '收起信息'
STYLE_SERVICE = 'Service.TLabel'
SERVICE_DIRECTORY = '服务目录'
SERVICE_CONTEXT = '当前服务  ·  {kind}  ·  端口 {port}  ·  PID {pid}'
FRONTEND_KIND, BACKEND_KIND, NO_PID = '前端', '后端', '—'
HOVER = '#edf2f9'
SCROLL_TRACK, SCROLL_THUMB = '#f3f5f8', '#7e8da0'
SCROLL_HOVER, SCROLL_PRESSED = '#62748b', '#526478'
# 动作色明确区分启停、重启与页面入口；禁用态统一退回中性色。
STYLE_START, STYLE_STOP = 'Start.TButton', 'Stop.TButton'
STYLE_RESTART, STYLE_OPEN = 'Restart.TButton', 'Open.TButton'
ACTION_PALETTES = {
    STYLE_START: (SUCCESS, '#e5f5ed', '#cfe9da'),
    STYLE_STOP: (ERROR, '#fbeaec', '#f5d5dc'),
    STYLE_RESTART: (WARNING, '#fff3d6', '#f5e3ae'),
    STYLE_OPEN: ('#116b78', '#e1f3f5', '#c9e8ec'),
}
RUNNING_COUNT, EXTERNAL_COUNT, CHANGED_COUNT = '{count} 运行中', '{count} 外部服务', '{count} 代码变更'


class ControlApp:
    """不跨线程调用 Tk；队列承接初始化与退出结果。"""

    def __init__(self, window: tk.Tk, root: Path, runners=None):
        # workspace 定位固定配置；runners 可由隔离交互测试提供。
        self.window = window
        self.workspace = root
        self.runners = {}
        self._events = queue.Queue()
        self._shutdown = threading.Event()
        self._closing = False
        # 首次初始化也参与关闭握手，避免退出后才创建日志句柄。
        self._loading = runners is None
        self._last_logs = None
        self._last_changes = None
        self._selected_key = None
        self._after_id = None
        # 专注日志时收起左侧服务目录，当前服务标题与详情仍可见。
        self._log_focus = False
        # 工作目录和检查地址按需展开，日志默认获得更多高度。
        self._info_open = False
        self._build_window()
        if runners is None:
            threading.Thread(target=self._load, daemon=True).start()
        else:
            self._attach(runners)
        self._tick()

    def _build_window(self):
        # 左侧承载服务选择与操作，右侧集中展示当前服务上下文。
        self.window.title(TITLE)
        self.window.geometry(APP_GEOMETRY)
        self.window.minsize(960, 640)
        self.window.configure(background=BACKGROUND)
        self.window.protocol(KEY_CLOSE, self.close)
        style = ttk.Style(self.window)
        style.theme_use('clam')
        style.configure('.', font=(FONT, 10))
        style.configure(STYLE_FRAME, background=BACKGROUND)
        style.configure(STYLE_LABEL, background=BACKGROUND, foreground=FOREGROUND)
        style.configure(STYLE_TITLE, font=(FONT, 18, 'bold'), foreground='#18356a')
        style.configure(STYLE_SERVICE, font=(FONT, 22, 'bold'), foreground='#173e73')
        style.configure(STYLE_MUTED, foreground=MUTED)
        style.configure(STYLE_BUTTON, padding=(12, 6), foreground=FOREGROUND,
                        background=SURFACE, bordercolor=BORDER, lightcolor=SURFACE,
                        darkcolor=SURFACE, relief='flat')
        style.map(STYLE_BUTTON, background=[('active', HOVER), ('disabled', BACKGROUND)],
                  foreground=[('disabled', MUTED)])
        style.configure(STYLE_PRIMARY, background=ACCENT, foreground=SURFACE)
        style.map(STYLE_PRIMARY, background=[('active', '#1c4692'), ('disabled', BORDER)],
                  foreground=[('disabled', MUTED)])
        for action_style, (ink, tint, hover) in ACTION_PALETTES.items():
            style.configure(action_style, foreground=ink, background=tint, bordercolor=tint,
                            lightcolor=tint, darkcolor=tint)
            backgrounds = [('disabled', BACKGROUND), ('pressed', hover), ('active', hover)]
            style.map(action_style, background=backgrounds, lightcolor=backgrounds,
                      darkcolor=backgrounds, bordercolor=backgrounds,
                      foreground=[('disabled', MUTED)])
        style.configure('TNotebook', background=BACKGROUND, borderwidth=0)
        style.configure('TNotebook.Tab', padding=(16, 8), background=BACKGROUND,
                        foreground=MUTED, borderwidth=0, lightcolor=BACKGROUND)
        style.map('TNotebook.Tab', background=[('selected', ACCENT), ('active', SELECTED)],
                  foreground=[('selected', SURFACE), ('active', ACCENT)],
                  # clam 默认会缩小选中页签的 padding，必须显式覆盖状态映射。
                  padding=[('selected', (16, 8)), ('!selected', (16, 8))])
        # 全局保留原生滚动行为，仅去掉箭头、凸起边框与滑块纹路。
        for orientation in ('Vertical', 'Horizontal'):
            scrollbar_style = orientation + '.TScrollbar'
            element = orientation + '.Scrollbar.'
            style.layout(scrollbar_style, [(element + 'trough', {
                'sticky': 'nswe', 'children': [(element + 'thumb', {'sticky': 'nswe'})],
            })])
            style.configure(scrollbar_style, arrowsize=12, gripcount=0, sliderlength=28,
                            troughcolor=SCROLL_TRACK, bordercolor=SCROLL_TRACK,
                            background=SCROLL_THUMB, lightcolor=SCROLL_THUMB, darkcolor=SCROLL_THUMB)
            thumb_states = [('disabled', SCROLL_TRACK), ('pressed', SCROLL_PRESSED),
                            ('active', SCROLL_HOVER)]
            # 无需滚动时滑块融入轨道；悬停与拖动时加深，交互仍有清晰反馈。
            style.map(scrollbar_style, background=thumb_states, lightcolor=thumb_states,
                      darkcolor=thumb_states)
        shell = ttk.Frame(self.window, padding=20)
        shell.pack(fill='both', expand=True)
        header = ttk.Frame(shell)
        header.pack(fill='x')
        ttk.Label(header, text=TITLE, style=STYLE_TITLE).pack(side='left')
        toolbar = ttk.Frame(header)
        toolbar.pack(side='right')
        self.bulk_buttons = []
        for label, action, button_style in (
            (START_ALL, self.start_all, STYLE_PRIMARY),
            (STOP_ALL, self.stop_all, STYLE_STOP),
            (RESTART_CHANGED, self.restart_changed, STYLE_RESTART),
        ):
            button = ttk.Button(toolbar, text=label, command=action, style=button_style)
            button.pack(side='left', padx=(8, 0))
            self.bulk_buttons.append(button)
        overview = ttk.Frame(shell)
        overview.pack(fill='x', pady=(12, 18))
        self.summary = tk.StringVar(value=SUMMARY_LOADING)
        self.summary_label = ttk.Label(overview, textvariable=self.summary, style=STYLE_MUTED)
        self.summary_label.pack(side='left')
        self.summary_badges = ttk.Frame(overview)
        self.summary_counts = tuple(tk.StringVar() for _ in range(3))
        for value, (ink, tint) in zip(self.summary_counts, (
                (SUCCESS, '#e5f5ed'), (ACCENT, SELECTED), (WARNING, '#fff3d6'))):
            tk.Label(self.summary_badges, textvariable=value, foreground=ink, background=tint,
                     font=(FONT, 9), padx=10, pady=4).pack(side='left', padx=(0, 8))
        ttk.Label(overview, text=SUBTITLE, style=STYLE_MUTED).pack(side='right')
        # 页脚独立保留空间，服务目录与日志工作区并排呈现。
        self.footer = tk.StringVar(value=FOOTER)
        self.footer_label = ttk.Label(shell, textvariable=self.footer, style=STYLE_MUTED, wraplength=880)
        self.footer_label.pack(side='bottom', fill='x', pady=(12, 0))
        body = ttk.Frame(shell)
        body.pack(fill='both', expand=True)
        self.sidebar = tk.Frame(body, background=SURFACE, width=288)
        self.sidebar.pack(side='left', fill='y', padx=(0, 20))
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text=SERVICE_DIRECTORY, font=(FONT, 11, 'bold'),
                 background=SURFACE, foreground=FOREGROUND, anchor='w', padx=12, pady=12).pack(fill='x')
        self.navigation = ServiceList(self.sidebar, self._select, self._open_service, self.act)
        self.navigation.pack(fill='both', expand=True)
        self.workspace_panel = ttk.Frame(body)
        self.workspace_panel.pack(side='left', fill='both', expand=True)
        # 当前服务标题不随状态换色，选择由标题、导航底色和“当前”三重确认。
        self.selected_name = tk.StringVar(value=DETAIL_EMPTY)
        self.selected_label = ttk.Label(self.workspace_panel, textvariable=self.selected_name,
                                         style=STYLE_SERVICE)
        self.selected_label.pack(anchor='w')
        self.context = tk.StringVar(value=EMPTY)
        ttk.Label(self.workspace_panel, textvariable=self.context, style=STYLE_MUTED).pack(anchor='w', pady=(6, 12))
        self.info_button = ttk.Button(self.workspace_panel, text=INFO_SHOW, width=7, command=self._toggle_info)
        self.info_button.pack(anchor='w', pady=(0, 10))
        self.detail = tk.StringVar(value=EMPTY)
        self.detail_label = ttk.Label(self.workspace_panel, textvariable=self.detail, style=STYLE_MUTED,
                                      wraplength=760, justify='left')
        self.detail_label.pack(anchor='w', fill='x', pady=(0, 12))
        self.metadata = tk.StringVar(value=EMPTY)
        self.metadata_label = ttk.Label(self.workspace_panel, textvariable=self.metadata, style=STYLE_MUTED,
                                        wraplength=760, justify='left')
        self.notebook = notebook = ttk.Notebook(self.workspace_panel)
        notebook.pack(fill='both', expand=True)
        self.log_panel = LogPanel(notebook, on_expand=self._toggle_log_focus)
        notebook.add(self.log_panel, text=LOG_TAB)
        self.logs = self.log_panel.text
        self.changes = self._text_tab(notebook, CHANGES_TAB, FONT)
        self.workspace_panel.bind('<Configure>', self._resize)

    def _resize(self, event):
        # 详情只按右侧工作区宽度换行，不挤压服务导航。
        if event.widget is self.workspace_panel:
            self.detail_label.configure(wraplength=max(360, event.width - 12))
            self.metadata_label.configure(wraplength=max(360, event.width - 12))

    def _toggle_log_focus(self):
        self._log_focus = not self._log_focus
        if self._log_focus:
            self.sidebar.pack_forget()
        else:
            self.sidebar.pack(before=self.workspace_panel, side='left', fill='y', padx=(0, 20))
        self.log_panel.expand_button.configure(text=LOG_RESTORE if self._log_focus else LOG_EXPAND)

    def _toggle_info(self):
        # 启动信息采用内联展开，不用弹窗打断日志阅读。
        self._info_open = not self._info_open
        if self._info_open:
            self.metadata_label.pack(before=self.notebook, fill='x', pady=(0, 10))
        else:
            self.metadata_label.pack_forget()
        self.info_button.configure(text=INFO_HIDE if self._info_open else INFO_SHOW)

    def _text_tab(self, notebook, label, font):
        # 文本区可选择复制，滚动条支持键盘与鼠标，不强制拉回底部。
        frame = ttk.Frame(notebook)
        widget = tk.Text(frame, wrap='none', height=8, font=(font, 10), borderwidth=0,
                         background=SURFACE, foreground=FOREGROUND, padx=12, pady=10,
                         selectbackground=SELECTED, selectforeground=FOREGROUND,
                         state=STATE_DISABLED)
        vertical = ttk.Scrollbar(frame, orient='vertical', command=widget.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=widget.xview)
        widget.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side='right', fill='y')
        horizontal.pack(side='bottom', fill='x')
        widget.pack(fill='both', expand=True)
        notebook.add(frame, text=label)
        return widget

    def _load(self):
        # 首次源码遍历也放在后台，较大的 dbt vendor 不阻塞首屏。
        runners = []
        try:
            for spec in load_services(self.workspace):
                runners.append(ServiceRunner(spec, self.workspace / 'tmp/local-control/logs',
                    spec_loader=lambda key=spec.key: next(item for item in load_services(self.workspace)
                                                          if item.key == key)))
            self._events.put((LOADED, runners))
        except Exception as error:
            for runner in runners:
                runner.close_logs()
            self._events.put((LOAD_FAILED, str(error)))

    def _attach(self, runners):
        for runner in runners:
            self.runners[runner.spec.key] = runner
            self.navigation.add(runner.spec)

            def monitor(service=runner):
                while not self._shutdown.is_set():
                    service.refresh()
                    self._shutdown.wait(3)

            if not self._closing:
                threading.Thread(target=monitor, daemon=True).start()
        if self.runners:
            self.navigation.select(next(iter(self.runners)))

    def _select(self, key):
        if key != self._selected_key:
            self._selected_key = key
            self._last_logs = self._last_changes = None
            self._render()

    def _open_service(self, key):
        runner = self.runners.get(key)
        if runner and runner.spec.frontend and not self._closing:
            webbrowser.open(runner.spec.open_url)

    def _replace_text(self, widget, value):
        scroll = widget.yview()
        widget.configure(state=STATE_NORMAL)
        widget.delete(START_INDEX, END)
        widget.insert(END, value)
        widget.configure(state=STATE_DISABLED)
        if scroll:
            widget.yview_moveto(scroll[0])

    def _render(self):
        views = {key: runner.view() for key, runner in self.runners.items()}
        for key, view in views.items():
            spec = self.runners[key].spec
            changed = (CHANGE_RESTART if view.restart_needed else CHANGE_HMR).format(count=len(view.changes))
            label = SCAN_FAILED if view.scan_error else changed if view.changes else CHANGE_CLEAN
            tone = (ERROR if view.status in (FAILED, EXITED, UNHEALTHY, UNHEALTHY_EXTERNAL) else
                    SUCCESS if view.status in (RUNNING, RUNNING_EXTERNAL) else MUTED)
            self.navigation.update_item(spec, view.status, label, tone)
            # 左侧各服务独立更新按钮状态；未选中的服务也可直接操作。
            controls = self.navigation.items[key]['buttons']
            for button in controls.values():
                button.configure(state=STATE_DISABLED)
            if not self._closing:
                if not view.busy and view.status != EXTERNAL:
                    controls[START].configure(state=STATE_NORMAL if view.pid is None else STATE_DISABLED)
                    controls[RESTART].configure(state=STATE_NORMAL)
                if (view.pid is not None or view.busy) and view.status != STOPPING:
                    controls[STOP].configure(state=STATE_NORMAL)
                if OPEN in controls:
                    controls[OPEN].configure(state=STATE_NORMAL)
        if views:
            counts = (sum(view.status in (RUNNING, RUNNING_EXTERNAL) for view in views.values()),
                      sum(view.external for view in views.values()),
                      sum(bool(view.changes) for view in views.values()))
            for variable, template, count in zip(self.summary_counts,
                                                 (RUNNING_COUNT, EXTERNAL_COUNT, CHANGED_COUNT), counts):
                variable.set(template.format(count=count))
            self.summary_label.pack_forget()
            self.summary_badges.pack(side='left')
        for button in self.bulk_buttons:
            button.configure(state=STATE_DISABLED if self._closing or not views else STATE_NORMAL)
        if self._selected_key not in views:
            return
        runner = self.runners[self._selected_key]
        view = views[self._selected_key]
        self.selected_name.set(runner.spec.name)
        self.context.set(SERVICE_CONTEXT.format(kind=FRONTEND_KIND if runner.spec.frontend else BACKEND_KIND,
                                                 port=runner.spec.port, pid=view.pid or NO_PID))
        self.detail.set(view.status + ('  ·  ' + view.detail if view.detail else EMPTY))
        self.detail_label.configure(foreground=ERROR if view.status in (FAILED, EXITED, UNHEALTHY, UNHEALTHY_EXTERNAL)
                                    else SUCCESS if view.status in (RUNNING, RUNNING_EXTERNAL) else MUTED)
        self.metadata.set(DETAIL_TEMPLATE.format(cwd=runner.spec.cwd, health=runner.spec.health_url))
        logs = (view.logs, view.external)
        changes = NEWLINE.join(f'{kind}  {path}' for path, kind in view.changes.items()) or CHANGES_EMPTY
        if view.scan_error:
            changes = view.scan_error + NEWLINE + changes
        if logs != self._last_logs:
            self.log_panel.update_lines(view.logs, notice=LOG_EXTERNAL if view.external else EMPTY,
                                        reset=self._last_logs is None)
            self._last_logs = logs
        if changes != self._last_changes:
            self._replace_text(self.changes, changes)
            self._last_changes = changes
    def _tick(self):
        # 所有跨线程结果在此合并，UI 定时器只做轻量快照更新。
        try:
            while True:
                event, value = self._events.get_nowait()
                if event == LOADED:
                    self._loading = False
                    self._attach(value)
                    if self._closing:
                        self._begin_close()
                elif event == LOAD_FAILED:
                    self._loading = False
                    self.summary.set(LOAD_ERROR.format(error=value))
                    if self._closing:
                        self._begin_close()
                elif event == CLOSED:
                    if value:
                        self._shutdown.set()
                        self.window.destroy()
                        return
                    self._closing = False
                    self.footer.set(FOOTER_CLOSE_FAILED)
        except queue.Empty:
            pass
        self._render()
        self._after_id = self.window.after(400, self._tick)

    def act(self, action):
        runner = self.runners.get(self._selected_key)
        if runner is None or self._closing:
            return
        if action == OPEN:
            webbrowser.open(runner.spec.open_url)
            return
        accepted = {START: runner.start, STOP: runner.stop, RESTART: runner.restart}[action]()
        self.footer.set(ACTION_ACCEPTED if accepted else ACTION_REJECTED)

    def start_all(self):
        for runner in self.runners.values():
            runner.start()
        self.footer.set(ACTION_ACCEPTED)

    def stop_all(self):
        for runner in reversed(tuple(self.runners.values())):
            if runner.view().pid is not None or runner.view().busy:
                runner.stop()
        self.footer.set(ACTION_ACCEPTED)

    def restart_changed(self):
        count = 0
        for runner in self.runners.values():
            view = runner.view()
            if view.pid and view.restart_needed and not view.busy:
                count += bool(runner.restart())
        self.footer.set(ACTION_ACCEPTED if count else RESTART_NONE)

    def close(self):
        # 不弹出确认框；先显示停止进度，全部受管进程退出后才销毁窗口。
        if self._closing:
            return
        self._closing = True
        self.footer.set(FOOTER_CLOSING)
        if not self._loading:
            self._begin_close()

    def _begin_close(self):
        def finish():
            runners = tuple(self.runners.values())
            for runner in runners:
                runner.stop(managed_only=True)
            success = True
            for runner in runners:
                success = runner.wait_idle(30) and (runner.view().pid is None or runner.view().external) and success
            if success:
                for runner in runners:
                    runner.close_logs()
            self._events.put((CLOSED, success))

        threading.Thread(target=finish, daemon=True).start()


if __name__ == '__main__':
    # 从入口文件定位工作区，无论从哪个终端或 IDE 工作目录启动均可使用。
    window = tk.Tk()
    ControlApp(window, Path(__file__).resolve().parents[2])
    window.mainloop()
