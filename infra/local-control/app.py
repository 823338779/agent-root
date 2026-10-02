"""一体化桌面入口：Tk 主线程绘制，后台线程管理本地服务。"""

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
import webbrowser

from config import load_services
from runtime import ServiceRunner, RUNNING, EXTERNAL, FAILED, EXITED, UNHEALTHY, STOPPING

# 文案和设计值集中定义，业务状态始终直接来自运行控制器。
TITLE = '本地服务中控'
SUBTITLE = '统一管理工作区服务 · 源码变更仅在此处提示'
FONT = 'Microsoft YaHei UI'
MONO = 'Consolas'
BACKGROUND, SURFACE, FOREGROUND = '#f3f5f8', '#ffffff', '#19283b'
MUTED, ACCENT, SELECTED = '#526478', '#2458b5', '#e7effc'
SUCCESS, WARNING, ERROR = '#236848', '#875200', '#a52a37'
BORDER = '#d5dde8'
EMPTY = ''
APP_GEOMETRY = '1180x780'
SUMMARY_LOADING = '正在读取启动配置和源码…'
SUMMARY_TEMPLATE = '{running} 个运行中    {external} 个外部占用    {changed} 个代码已变更'
FOOTER = '每 3 秒检测一次 · 关闭客户端将停止由它启动的服务 · 外部进程由原 IDE 管理'
FOOTER_CLOSING = '正在停止受管服务并释放日志，请稍候…'
FOOTER_CLOSE_FAILED = '部分服务未能停止。请查看服务详情，处理后再次关闭窗口。'
DETAIL_EMPTY = '选择服务，查看日志和源码变更'
LOG_EMPTY = '尚无运行日志。点击“启动”后，构建与运行输出会显示在这里。'
CHANGES_EMPTY = '未发现源码变更。服务成功重启后，将更新检测基线。'
CHANGE_RESTART = '代码已变更 · 建议重启 ({count})'
CHANGE_HMR = '代码已变更 · Vite 热更新 ({count})'
CHANGE_CLEAN = '无变更'
SCAN_FAILED = '源码检测失败'
DETAIL_TEMPLATE = '{name}   |   {detail}\n工作目录：{cwd}\n健康检查：{health}'
LOG_TAB, CHANGES_TAB = '运行日志', '变更文件'
START, STOP, RESTART, OPEN = '启动', '停止', '重启', '打开页面'
START_ALL, STOP_ALL, RESTART_CHANGED = '启动全部', '停止全部', '重启已变更'
ACTION_REJECTED = '服务正在操作或由外部启动，请查看运行状态。'
RESTART_NONE = '当前没有需要重启的受管服务。'
ACTION_ACCEPTED = '操作已提交；进度与结果会显示在服务列表和日志中。'
LOAD_ERROR = '无法加载配置：{error}'
KEY_CLOSE = 'WM_DELETE_WINDOW'
KEY_SELECTED = '<<TreeviewSelect>>'
KEY_CLICK = '<ButtonRelease-1>'
KEY_MOTION = '<Motion>'
PORT_COLUMN = '#3'
LINK_CURSOR = 'hand2'
COLUMNS = ('name', 'status', 'port', 'pid', 'changes')
HEADINGS = ('服务', '运行状态', '端口', '进程 PID', '源码状态')
WIDTHS = (220, 180, 80, 90, 280)
TAG_WARNING, TAG_ERROR, TAG_SUCCESS = 'warning', 'error', 'success'
STYLE_FRAME, STYLE_LABEL, STYLE_TITLE = 'TFrame', 'TLabel', 'Title.TLabel'
STYLE_MUTED, STYLE_BUTTON, STYLE_PRIMARY = 'Muted.TLabel', 'TButton', 'Primary.TButton'
STYLE_TREE, STYLE_HEADING = 'Treeview', 'Treeview.Heading'
LOADED, LOAD_FAILED, CLOSED = 'loaded', 'load-failed', 'closed'
STATE_NORMAL, STATE_DISABLED = 'normal', 'disabled'
END, START_INDEX = 'end', '1.0'
NEWLINE = '\n'


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
        self._build_window()
        if runners is None:
            threading.Thread(target=self._load, daemon=True).start()
        else:
            self._attach(runners)
        self._tick()

    def _build_window(self):
        # 表格承载服务状态；详情区固定在下方，操作无需弹出窗口。
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
        style.configure(STYLE_TITLE, font=(FONT, 21, 'bold'))
        style.configure(STYLE_MUTED, foreground=MUTED)
        style.configure(STYLE_BUTTON, padding=(14, 8), foreground=FOREGROUND)
        style.configure(STYLE_PRIMARY, background=ACCENT, foreground=SURFACE)
        style.map(STYLE_PRIMARY, background=[('active', '#1c4692'), ('disabled', BORDER)],
                  foreground=[('disabled', MUTED)])
        style.configure(STYLE_TREE, font=(FONT, 10), rowheight=44, borderwidth=0,
                        background=SURFACE, fieldbackground=SURFACE, foreground=FOREGROUND)
        style.configure(STYLE_HEADING, font=(FONT, 10, 'bold'), padding=(8, 10),
                        background=BACKGROUND, foreground=MUTED)
        style.map(STYLE_TREE, background=[('selected', SELECTED)],
                  foreground=[('selected', FOREGROUND)])
        style.configure('TNotebook.Tab', padding=(14, 7))
        shell = ttk.Frame(self.window, padding=24)
        shell.pack(fill='both', expand=True)
        header = ttk.Frame(shell)
        header.pack(fill='x')
        ttk.Label(header, text=TITLE, style=STYLE_TITLE).pack(side='left')
        self.summary = tk.StringVar(value=SUMMARY_LOADING)
        ttk.Label(header, textvariable=self.summary, style=STYLE_MUTED).pack(side='right')
        ttk.Label(shell, text=SUBTITLE, style=STYLE_MUTED).pack(anchor='w', pady=(6, 18))
        toolbar = ttk.Frame(shell)
        toolbar.pack(fill='x', pady=(0, 12))
        self.bulk_buttons = []
        for label, action, button_style in (
            (START_ALL, self.start_all, STYLE_PRIMARY),
            (STOP_ALL, self.stop_all, STYLE_BUTTON),
            (RESTART_CHANGED, self.restart_changed, STYLE_BUTTON),
        ):
            button = ttk.Button(toolbar, text=label, command=action, style=button_style)
            button.pack(side='left', padx=(0, 8))
            self.bulk_buttons.append(button)
        self.tree = ttk.Treeview(shell, columns=COLUMNS, show='headings', height=5,
                                 selectmode='browse')
        for column, heading, width in zip(COLUMNS, HEADINGS, WIDTHS):
            self.tree.heading(column, text=heading, anchor='w')
            self.tree.column(column, width=width, minwidth=width, stretch=column in ('name', 'changes'))
        self.tree.tag_configure(TAG_WARNING, foreground=WARNING)
        self.tree.tag_configure(TAG_ERROR, foreground=ERROR)
        self.tree.tag_configure(TAG_SUCCESS, foreground=SUCCESS)
        self.tree.pack(fill='x')
        self.tree.bind(KEY_SELECTED, self._select)
        self.tree.bind(KEY_CLICK, self._port_click)
        self.tree.bind(KEY_MOTION, self._port_hover)
        self.detail = tk.StringVar(value=DETAIL_EMPTY)
        ttk.Label(shell, textvariable=self.detail, wraplength=1040, justify='left').pack(
            anchor='w', fill='x', pady=(16, 10))
        controls = ttk.Frame(shell)
        controls.pack(fill='x', pady=(0, 12))
        self.buttons = {}
        for label in (START, STOP, RESTART, OPEN):
            button = ttk.Button(controls, text=label, command=lambda action=label: self.act(action))
            button.pack(side='left', padx=(0, 8))
            self.buttons[label] = button
        notebook = ttk.Notebook(shell)
        notebook.pack(fill='both', expand=True)
        self.logs = self._text_tab(notebook, LOG_TAB, MONO)
        self.changes = self._text_tab(notebook, CHANGES_TAB, FONT)
        self.footer = tk.StringVar(value=FOOTER)
        # 先为底部状态留空间，再让日志区占用剩余高度，小窗口也能看见退出提示。
        self.footer_label = ttk.Label(shell, textvariable=self.footer, style=STYLE_MUTED, wraplength=880)
        self.footer_label.pack(before=notebook, side='bottom', anchor='w', fill='x', pady=(12, 0))

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
            self.tree.insert(EMPTY, END, iid=runner.spec.key)

            def monitor(service=runner):
                while not self._shutdown.is_set():
                    service.refresh()
                    self._shutdown.wait(3)

            if not self._closing:
                threading.Thread(target=monitor, daemon=True).start()
        if self.runners:
            self.tree.selection_set(next(iter(self.runners)))

    def _select(self, _event=None):
        selected = self.tree.selection()
        self._selected_key = selected[0] if selected else None
        self._last_logs = self._last_changes = None

    def _linked_runner(self, event):
        # 前端端口单元格直接打开实际配置的 URL，无需先选中再点击按钮。
        key = self.tree.identify_row(event.y)
        runner = self.runners.get(key)
        if (self.tree.identify_column(event.x) == PORT_COLUMN and runner
                and runner.spec.frontend and not self._closing):
            return runner
        return None

    def _port_click(self, event):
        runner = self._linked_runner(event)
        if runner:
            webbrowser.open(runner.spec.open_url)

    def _port_hover(self, event):
        self.tree.configure(cursor=LINK_CURSOR if self._linked_runner(event) else EMPTY)

    def _replace_text(self, widget, value, follow=False):
        scroll = widget.yview()
        widget.configure(state=STATE_NORMAL)
        widget.delete(START_INDEX, END)
        widget.insert(END, value)
        widget.configure(state=STATE_DISABLED)
        if follow and (not scroll or scroll[1] >= 0.99):
            widget.see(END)
        elif scroll:
            widget.yview_moveto(scroll[0])

    def _render(self):
        views = {key: runner.view() for key, runner in self.runners.items()}
        for key, view in views.items():
            spec = self.runners[key].spec
            changed = (CHANGE_RESTART if view.restart_needed else CHANGE_HMR).format(count=len(view.changes))
            label = SCAN_FAILED if view.scan_error else changed if view.changes else CHANGE_CLEAN
            tag = (TAG_ERROR if view.status in (FAILED, EXITED, UNHEALTHY) else
                   TAG_WARNING if view.changes or view.scan_error else
                   TAG_SUCCESS if view.status == RUNNING else EMPTY)
            port_label = f'{spec.port} ↗' if spec.frontend else str(spec.port)
            self.tree.item(key, values=(spec.name, view.status, port_label, view.pid or '—', label), tags=(tag,))
        if views:
            self.summary.set(SUMMARY_TEMPLATE.format(
                running=sum(view.status == RUNNING for view in views.values()),
                external=sum(view.status == EXTERNAL for view in views.values()),
                changed=sum(bool(view.changes) for view in views.values())))
        for button in self.bulk_buttons:
            button.configure(state=STATE_DISABLED if self._closing or not views else STATE_NORMAL)
        for button in self.buttons.values():
            button.configure(state=STATE_DISABLED)
        if self._selected_key not in views:
            return
        runner = self.runners[self._selected_key]
        view = views[self._selected_key]
        self.detail.set(DETAIL_TEMPLATE.format(name=runner.spec.name, detail=view.detail or view.status,
                                               cwd=runner.spec.cwd, health=runner.spec.health_url))
        logs = NEWLINE.join(view.logs) or LOG_EMPTY
        changes = NEWLINE.join(f'{kind}  {path}' for path, kind in view.changes.items()) or CHANGES_EMPTY
        if view.scan_error:
            changes = view.scan_error + NEWLINE + changes
        if logs != self._last_logs:
            self._replace_text(self.logs, logs, follow=True)
            self._last_logs = logs
        if changes != self._last_changes:
            self._replace_text(self.changes, changes)
            self._last_changes = changes
        if not self._closing:
            if not view.busy and view.status != EXTERNAL:
                self.buttons[START].configure(state=STATE_NORMAL if view.pid is None else STATE_DISABLED)
                self.buttons[RESTART].configure(state=STATE_NORMAL)
            if (view.pid is not None or view.busy) and view.status != STOPPING:
                self.buttons[STOP].configure(state=STATE_NORMAL)
            self.buttons[OPEN].configure(state=STATE_NORMAL)

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
                runner.stop()
            success = True
            for runner in runners:
                success = runner.wait_idle(30) and runner.view().pid is None and success
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
