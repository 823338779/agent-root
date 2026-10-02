"""服务导航：选择与焦点分离，离开导航后仍明确标记当前服务。"""

import tkinter as tk
from tkinter import ttk

FONT = 'Microsoft YaHei UI'
WHITE, INK, MUTED = '#ffffff', '#20334d', '#526478'
SELECTED, SELECTED_MUTED, HOVER = '#173e73', '#d6e5fa', '#edf2fa'
ACCENT = '#2458b5'
CURRENT, FRONTEND, BACKEND = '当前', '前端', '后端'
OPEN_CURSOR, BREAK = 'hand2', 'break'
START, STOP, RESTART, OPEN = '启动', '停止', '重启', '打开页面'
ACTION_STYLES = {START: 'Nav.Start.TButton', STOP: 'Nav.Stop.TButton',
                 RESTART: 'Nav.Restart.TButton', OPEN: 'Nav.Open.TButton'}


class ServiceList(tk.Frame):
    def __init__(self, parent, on_select, on_open, on_action):
        super().__init__(parent, background=WHITE)
        # 固定服务目录中的行与选中键，只维护视图，不管理服务进程。
        self.items = {}
        self.selected = None
        self.on_select = on_select
        self.on_open = on_open
        self.on_action = on_action
        # 导航内使用紧凑操作尺寸，前端四个按钮在最小窗口仍完整可见。
        style = ttk.Style(self)
        for action_style in ACTION_STYLES.values():
            style.configure(action_style, padding=(5, 5), font=(FONT, 9))
        # 小窗口可以滚动服务目录；导航宽度与画布同步，不裁掉末尾服务。
        self.canvas = tk.Canvas(self, background=WHITE, highlightthickness=0, width=1)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.content = tk.Frame(self.canvas, background=WHITE)
        self.content_id = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self._resize)
        self.canvas.bind('<MouseWheel>', self._wheel)

    def add(self, spec):
        row = tk.Frame(self.content, background=WHITE, padx=12, pady=9, takefocus=True,
                       highlightthickness=1, highlightbackground=WHITE, highlightcolor=ACCENT)
        row.pack(fill='x', pady=(0, 2))
        row.columnconfigure(0, weight=1)
        name = tk.Label(row, text=spec.name, font=(FONT, 11, 'bold'), anchor='w')
        marker = tk.Label(row, font=(FONT, 9), padx=5)
        status = tk.Label(row, font=(FONT, 9), anchor='w')
        port = tk.Label(row, text=f':{spec.port}', font=(FONT, 9, 'underline') if spec.frontend else (FONT, 9),
                        cursor=OPEN_CURSOR if spec.frontend else '')
        changes = tk.Label(row, font=(FONT, 9), anchor='w')
        name.grid(row=0, column=0, sticky='w')
        marker.grid(row=0, column=1, sticky='e')
        status.grid(row=1, column=0, sticky='w', pady=(6, 0))
        port.grid(row=1, column=1, sticky='e', pady=(6, 0))
        changes.grid(row=2, column=0, columnspan=2, sticky='w', pady=(3, 0))
        self.items[spec.key] = dict(row=row, name=name, marker=marker, status=status,
                                    port=port, changes=changes, spec=spec, tone=MUTED)
        # 操作始终属于所在服务项；先同步右侧上下文，再执行该服务的动作。
        actions = tk.Frame(row, background=WHITE)
        actions.grid(row=3, column=0, columnspan=2, sticky='w', pady=(8, 0))
        buttons = {}
        for action in (START, STOP, RESTART, OPEN) if spec.frontend else (START, STOP, RESTART):
            button = ttk.Button(actions, text=action, width=3 if action != OPEN else 6,
                                 style=ACTION_STYLES[action],
                                 command=lambda value=action, key=spec.key: self._action(key, value))
            button.pack(side='left', padx=(0, 4))
            button.bind('<MouseWheel>', self._wheel)
            buttons[action] = button
        self.items[spec.key].update(actions=actions, buttons=buttons)
        # 整行都可点击；端口链接先切换上下文，再在浏览器打开对应前端。
        for widget in (row, name, marker, status, port, changes):
            widget.bind('<Button-1>', lambda event, key=spec.key: self.select(key))
            widget.bind('<Enter>', lambda event, key=spec.key: self._paint(key, hover=True))
            widget.bind('<Leave>', lambda event, key=spec.key: self._paint(key))
            widget.bind('<MouseWheel>', self._wheel)
        if spec.frontend:
            port.bind('<Button-1>', lambda event, key=spec.key: self._open(key))
        row.bind('<Up>', lambda event, key=spec.key: self._move(key, -1))
        row.bind('<Down>', lambda event, key=spec.key: self._move(key, 1))
        row.bind('<Return>', lambda event, key=spec.key: self.select(key))
        row.bind('<space>', lambda event, key=spec.key: self.select(key))
        self._paint(spec.key)

    def select(self, key):
        if key not in self.items:
            return BREAK
        previous, self.selected = self.selected, key
        if previous:
            self._paint(previous)
        self._paint(key)
        self.items[key]['row'].focus_set()
        self._reveal(key)
        self.on_select(key)
        return BREAK

    def _open(self, key):
        self.select(key)
        self.on_open(key)
        return BREAK

    def _action(self, key, action):
        self.select(key)
        self.on_action(action)

    def _move(self, key, step):
        keys = tuple(self.items)
        return self.select(keys[max(0, min(len(keys) - 1, keys.index(key) + step))])

    def _wheel(self, event):
        if self.content.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return BREAK

    def _resize(self, event):
        # 缩小窗口后仍将当前服务和其操作保留在可见区域。
        self.canvas.itemconfigure(self.content_id, width=event.width)
        if self.selected:
            self.canvas.after_idle(lambda: self._reveal(self.selected))

    def _reveal(self, key):
        # 键盘切换到不可见服务时同步滚动，当前服务始终留在导航视口内。
        self.update_idletasks()
        row = self.items[key]['row']
        top = self.canvas.canvasy(0)
        bottom = row.winfo_y() + row.winfo_height()
        target = row.winfo_y() if row.winfo_y() < top else bottom - self.canvas.winfo_height()
        if row.winfo_y() < top or bottom > top + self.canvas.winfo_height():
            self.canvas.yview_moveto(max(0, target) / max(1, self.content.winfo_height()))

    def update_item(self, spec, status, changes, tone=MUTED):
        item = self.items[spec.key]
        item['spec'] = spec
        item['port'].configure(text=f':{spec.port}')
        item['tone'] = tone
        item['status'].configure(text=status)
        item['changes'].configure(text=changes)
        self._paint(spec.key)

    def _paint(self, key, hover=False):
        # 选中底色永远覆盖状态色；文字“当前”让选择不依赖颜色或键盘焦点。
        item = self.items[key]
        selected = key == self.selected
        background = SELECTED if selected else HOVER if hover else WHITE
        ink = WHITE if selected else INK
        secondary = SELECTED_MUTED if selected else MUTED
        item['row'].configure(background=background, highlightbackground=background)
        item['actions'].configure(background=background)
        for field in ('name', 'marker', 'status', 'port', 'changes'):
            item[field].configure(background=background, foreground=secondary)
        item['name'].configure(foreground=ink)
        item['status'].configure(foreground=secondary if selected else item['tone'])
        item['port'].configure(foreground=ink if selected else ACCENT)
        item['marker'].configure(text=CURRENT if selected else FRONTEND if item['spec'].frontend else BACKEND,
                                  foreground=ink if selected else MUTED)
