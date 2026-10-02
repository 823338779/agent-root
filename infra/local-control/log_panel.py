"""原生 Tk 日志阅读区：分级着色、增量更新与阅读位置保护。"""

import re
import tkinter as tk
from tkinter import ttk

# 颜色延续中控的浅色工作区；严重级别同时保留原始文字。
SURFACE, TOOLBAR, TEXT = '#ffffff', '#eaf2fc', '#19283b'
MUTED, BORDER, ACCENT = '#526478', '#d5dde8', '#2458b5'
ERROR, ERROR_BG = '#a52a37', '#fff1f2'
WARNING, WARNING_BG = '#875200', '#fff8e8'
SUCCESS, SELECTION = '#236848', '#e7effc'
FONT, MONO = 'Microsoft YaHei UI', 'Consolas'
BUTTON_STYLE, CHECK_STYLE = 'Log.TButton', 'Log.TCheckbutton'
SUMMARY = '最近 {count} 行  ·  {warnings} 警告  ·  {errors} 错误'
WRAP, COPY, LATEST = '自动换行', '复制日志', '回到底部'
EXPAND = '专注日志'
EMPTY = '尚无日志；服务启动后，构建与运行输出会显示在这里。'
NORMAL, DISABLED, END, BEGIN = 'normal', 'disabled', 'end', '1.0'
NEWLINE, SELECT = '\n', 'sel'
STAMP, LEVEL, TRACE = 'timestamp', 'level', 'trace'
INFO, WARN, FAIL, OK = 'info', 'warning', 'error', 'success'
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')
TIMESTAMP = re.compile(r'^\d{2}:\d{2}:\d{2}\s+')
SEVERITY = re.compile(r'(?<!\w)(TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)(?!\w)')
LEVEL_TAGS = {'TRACE': TRACE, 'DEBUG': TRACE, 'INFO': INFO,
              'WARN': WARN, 'WARNING': WARN, 'ERROR': FAIL, 'FATAL': FAIL}
SUCCESS_MARKERS = ('BUILD SUCCESS', '健康检查通过')
TRACE_MARKERS = ('at ', 'Caused by:', '... ', 'Traceback (')


class LogPanel(tk.Frame):
    def __init__(self, parent, on_expand=None):
        super().__init__(parent, background=SURFACE)
        # 保存已呈现的有界日志，以增量插入保留选择和滚动位置。
        self._lines = ()
        self.summary = tk.StringVar(value=SUMMARY.format(count=0, warnings=0, errors=0))
        self.notice = tk.StringVar(value=EMPTY)
        self.wrap = tk.BooleanVar(value=False)
        style = ttk.Style(self)
        style.configure(BUTTON_STYLE, padding=(10, 5), font=(FONT, 9))
        style.configure(CHECK_STYLE, background=TOOLBAR, font=(FONT, 9))
        toolbar = tk.Frame(self, background=TOOLBAR, padx=12, pady=7)
        toolbar.pack(fill='x')
        heading = tk.Frame(toolbar, background=TOOLBAR)
        heading.pack(fill='x')
        tk.Label(heading, textvariable=self.summary, background=TOOLBAR,
                 foreground=MUTED, font=(FONT, 9)).pack(side='left')
        if on_expand:
            self.expand_button = ttk.Button(heading, text=EXPAND, style=BUTTON_STYLE, command=on_expand)
            self.expand_button.pack(side='right', padx=(8, 0))
        actions = tk.Frame(toolbar, background=TOOLBAR)
        actions.pack(fill='x', pady=(6, 0))
        self.latest_button = ttk.Button(actions, text=LATEST, style=BUTTON_STYLE, command=self.latest,
                                         state=DISABLED)
        self.latest_button.pack(side='right')
        self.copy_button = ttk.Button(actions, text=COPY, style=BUTTON_STYLE, command=self.copy,
                                       state=DISABLED)
        self.copy_button.pack(side='right', padx=8)
        self.wrap_button = ttk.Checkbutton(actions, text=WRAP, variable=self.wrap,
                                          style=CHECK_STYLE, command=self._toggle_wrap)
        self.wrap_button.pack(side='right', padx=(12, 4))
        tk.Frame(self, height=1, background=BORDER).pack(fill='x')
        self.notice_label = tk.Label(self, textvariable=self.notice, background=SURFACE,
                                     foreground=MUTED, font=(FONT, 10), anchor='w', justify='left',
                                     padx=16, pady=10)
        self.notice_label.pack(fill='x')
        self.bind('<Configure>', lambda event: self.notice_label.configure(wraplength=max(100, event.width - 32)))
        body = tk.Frame(self, background=SURFACE)
        body.pack(fill='both', expand=True)
        self.body = body
        self.text = tk.Text(body, wrap='none', height=8, font=(MONO, 11), borderwidth=0,
                            background=SURFACE, foreground=TEXT, padx=16, pady=12,
                            spacing1=2, spacing3=2, selectbackground=SELECTION,
                            selectforeground=TEXT, highlightthickness=1,
                            highlightbackground=SURFACE, highlightcolor=ACCENT,
                            state=DISABLED, takefocus=True)
        vertical = ttk.Scrollbar(body, orient='vertical', command=self.text.yview)
        self.horizontal = ttk.Scrollbar(body, orient='horizontal', command=self.text.xview)
        self.text.configure(yscrollcommand=vertical.set, xscrollcommand=self.horizontal.set)
        vertical.pack(side='right', fill='y')
        self.horizontal.pack(side='bottom', fill='x')
        self.text.pack(fill='both', expand=True)
        # 普通正文保持中性，仅级别和异常行使用语义色；时间独立弱化。
        self.text.tag_configure(WARN, foreground=WARNING, background=WARNING_BG)
        self.text.tag_configure(FAIL, foreground=ERROR, background=ERROR_BG)
        self.text.tag_configure(OK, foreground=SUCCESS)
        self.text.tag_configure(TRACE, foreground=MUTED)
        self.text.tag_configure(INFO, foreground=ACCENT)
        self.text.tag_configure(LEVEL, font=(MONO, 11, 'bold'))
        self.text.tag_configure(STAMP, foreground=MUTED)
        self.text.tag_raise(SELECT)

    def _toggle_wrap(self):
        # 换行时隐藏不再需要的横向滚动条；恢复时仍可查看完整长行。
        self.text.configure(wrap='word' if self.wrap.get() else 'none')
        if self.wrap.get():
            self.horizontal.pack_forget()
        else:
            self.horizontal.pack(before=self.text, side='bottom', fill='x')

    def latest(self):
        self.text.see(END)

    def copy(self):
        # 有选区时只复制所选片段，否则复制当前服务日志；提示文案不混入剪贴板。
        value = (self.text.get('sel.first', 'sel.last') if self.text.tag_ranges(SELECT)
                 else NEWLINE.join(self._lines))
        if value:
            self.clipboard_clear()
            self.clipboard_append(value)

    def update_lines(self, lines, notice='', reset=False):
        # 异常信息可能一条含多行，按物理行维护缓冲，避免淘汰时残留旧文本。
        cleaned = tuple(part for line in lines for part in ANSI.sub('', line).split(NEWLINE))
        self.notice.set(notice or (EMPTY if not cleaned else ''))
        if self.notice.get():
            self.notice_label.pack(before=self.body, fill='x')
        else:
            self.notice_label.pack_forget()
        self.copy_button.configure(state=NORMAL if cleaned else DISABLED)
        self.latest_button.configure(state=NORMAL if cleaned else DISABLED)
        if cleaned == self._lines and not reset:
            return
        # 只删除环形缓冲淘汰的前缀、追加新行，不重写正在选择的文本。
        follow = reset or self.text.yview()[1] >= 0.99
        overlap, removed = 0, len(self._lines)
        if not reset:
            for index in range(len(self._lines)):
                suffix = self._lines[index:]
                if suffix == cleaned[:len(suffix)]:
                    overlap, removed = len(suffix), index
                    break
        self.text.configure(state=NORMAL)
        if not overlap:
            self.text.delete(BEGIN, END)
        elif removed:
            self.text.delete(BEGIN, f'{removed + 1}.0')
        for line in cleaned[overlap:]:
            row = self.text.index('end-1c')
            self.text.insert(END, line + NEWLINE)
            match = SEVERITY.search(line)
            tag = LEVEL_TAGS.get(match.group(), '') if match else ''
            if tag in (WARN, FAIL, TRACE):
                self.text.tag_add(tag, row, f'{row}+{len(line) + 1}c')
            elif any(marker in line for marker in SUCCESS_MARKERS):
                self.text.tag_add(OK, row, f'{row}+{len(line)}c')
            elif line.lstrip().startswith(TRACE_MARKERS):
                self.text.tag_add(TRACE, row, f'{row}+{len(line)}c')
            if match:
                self.text.tag_add(LEVEL, f'{row}+{match.start()}c', f'{row}+{match.end()}c')
                if tag == INFO:
                    self.text.tag_add(INFO, f'{row}+{match.start()}c', f'{row}+{match.end()}c')
            stamp = TIMESTAMP.match(line)
            if stamp:
                self.text.tag_add(STAMP, row, f'{row}+{stamp.end()}c')
        self.text.configure(state=DISABLED)
        self._lines = cleaned
        levels = [match.group() for line in cleaned if (match := SEVERITY.search(line))]
        self.summary.set(SUMMARY.format(count=len(cleaned), warnings=sum(level in ('WARN', 'WARNING') for level in levels),
                                        errors=sum(level in ('ERROR', 'FATAL') for level in levels)))
        if follow:
            self.latest()
