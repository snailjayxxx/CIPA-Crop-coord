"""Folder-first FindsBlur GUI with live Chinese/Japanese switching.

Switching the language changes only presentation. It never alters input paths,
settings, calculation parameters, or the official Japanese failure line in TXT.
"""
from __future__ import annotations
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .core import CalculationError, collect_images, proposed_output, calculate
from .i18n import LANGUAGE_CHOICES, tr, localize_error


class Window:
    def __init__(self, root: tk.Tk, decoder: Path):
        self.root, self.decoder = root, decoder
        self.language_choice = tk.StringVar(value='中文')
        self.source_mode = tk.StringVar(value='folder')
        self.source_path = tk.StringVar(value='')
        self.output_path = tk.StringVar(value='')
        self.workers = tk.StringVar(value='2')
        self.calcdebug_enabled = tk.BooleanVar(value=False)
        self.calcdebug_folder = tk.StringVar(value='')
        self.status = tk.StringVar()
        self.details = tk.StringVar()
        self.previous_mode = 'folder'
        self.saved = {'folder': '', 'single': ''}
        self.last_suggestion = ''
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.busy = False
        self._status_record = ('ready', {})
        self._details_record = ('folder_help', {})
        self._log_records: list[tuple[str, dict]] = []

        root.geometry('850x720')
        root.minsize(730, 610)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill='both', expand=True)
        heading_row = ttk.Frame(frame)
        heading_row.pack(fill='x')
        self.heading = ttk.Label(heading_row, font=('Microsoft YaHei UI', 16, 'bold'))
        self.heading.pack(side='left', anchor='w')
        self.language_label = ttk.Label(heading_row)
        self.language_label.pack(side='right', padx=(8, 3))
        self.language_combo = ttk.Combobox(heading_row, textvariable=self.language_choice,
                                            values=tuple(LANGUAGE_CHOICES), width=9, state='readonly')
        self.language_combo.pack(side='right')
        self.language_combo.bind('<<ComboboxSelected>>', self.change_language)
        self.subtitle = ttk.Label(frame, foreground='#666666')
        self.subtitle.pack(anchor='w', pady=(3, 14))

        self.source_frame = ttk.LabelFrame(frame, padding=11)
        self.source_frame.pack(fill='x', pady=(0, 10))
        choices = ttk.Frame(self.source_frame)
        choices.pack(anchor='w')
        self.folder = ttk.Radiobutton(choices, variable=self.source_mode,
                                      value='folder', command=self.change_mode)
        self.folder.pack(side='left', padx=(0, 24))
        self.single = ttk.Radiobutton(choices, variable=self.source_mode,
                                      value='single', command=self.change_mode)
        self.single.pack(side='left')
        src_row = ttk.Frame(self.source_frame)
        src_row.pack(fill='x', pady=(9, 0))
        self.src_entry = ttk.Entry(src_row, textvariable=self.source_path)
        self.src_entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.src_entry.bind('<Return>', self.preview)
        self.browse_src = ttk.Button(src_row, command=self.choose_input)
        self.browse_src.pack(side='left')
        self.details_label = ttk.Label(self.source_frame, textvariable=self.details,
                                       wraplength=745, foreground='#666666')
        self.details_label.pack(anchor='w', pady=(8, 0))

        self.destination_frame = ttk.LabelFrame(frame, padding=11)
        self.destination_frame.pack(fill='x', pady=(0, 10))
        dest_row = ttk.Frame(self.destination_frame)
        dest_row.pack(fill='x')
        self.dest_entry = ttk.Entry(dest_row, textvariable=self.output_path)
        self.dest_entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.browse_dest = ttk.Button(dest_row, command=self.choose_output)
        self.browse_dest.pack(side='left')

        self.run_frame = ttk.LabelFrame(frame, padding=11)
        self.run_frame.pack(fill='x', pady=(0, 10))
        controls = ttk.Frame(self.run_frame)
        controls.pack(fill='x')
        self.start_btn = ttk.Button(controls, command=self.start)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(controls, command=self.stop, state='disabled')
        self.stop_btn.pack(side='left', padx=(9, 20))
        self.workers_label = ttk.Label(controls)
        self.workers_label.pack(side='left')
        self.jobs = ttk.Combobox(controls, textvariable=self.workers, values=('1', '2', '3', '4'),
                                 state='readonly', width=4)
        self.jobs.pack(side='left')
        ttk.Label(controls, textvariable=self.status).pack(side='right')
        self.progress = ttk.Progressbar(self.run_frame, orient='horizontal', mode='determinate')
        self.progress.pack(fill='x', pady=(9, 0))

        self.calcdebug_frame = ttk.LabelFrame(frame, padding=11)
        self.calcdebug_frame.pack(fill='x', pady=(0, 10))
        self.calcdebug_check = ttk.Checkbutton(self.calcdebug_frame,
             variable=self.calcdebug_enabled, command=self.toggle_calcdebug)
        self.calcdebug_check.pack(anchor='w')
        debug_row = ttk.Frame(self.calcdebug_frame)
        debug_row.pack(fill='x', pady=(6, 0))
        self.calcdebug_entry = ttk.Entry(debug_row, textvariable=self.calcdebug_folder)
        self.calcdebug_entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.calcdebug_browse = ttk.Button(debug_row, command=self.choose_calcdebug_dir)
        self.calcdebug_browse.pack(side='left')
        self.calcdebug_help = ttk.Label(self.calcdebug_frame, foreground='#666666')
        self.calcdebug_help.pack(anchor='w', pady=(5, 0))
        self.toggle_calcdebug()

        self.log_label = ttk.Label(frame)
        self.log_label.pack(anchor='w', pady=(0, 4))
        self.log_widget = scrolledtext.ScrolledText(frame, height=9, state='disabled',
                                                     wrap='word', font=('Consolas', 9))
        self.log_widget.pack(fill='both', expand=True)
        self.log_event('intro_log')
        self.apply_language()
        root.after(100, self.poll)

    @property
    def lang(self) -> str:
        return LANGUAGE_CHOICES.get(self.language_choice.get(), 'zh')

    def text(self, key: str, **params) -> str:
        return tr(self.lang, key, **params)

    def set_status(self, key: str, **params):
        self._status_record = (key, params)
        self.status.set(self.text(key, **params))

    def set_details(self, key: str, **params):
        self._details_record = (key, params)
        self.details.set(self._translate_details(key, params))

    def _translate_details(self, key, params):
        if key == '_core_error':
            return localize_error(params['message'], self.lang).replace('\n', ' ')
        if key == 'found':
            params = dict(params)
            params['more'] = self.text('more') if params.pop('has_more', False) else ''
        return self.text(key, **params)

    def log_event(self, key: str, **params):
        self._log_records.append((key, params))
        self._append_log(self._translate_log(key, params))

    def _translate_log(self, key, params):
        if key == '_raw_error':
            return localize_error(params['message'], self.lang)
        if key in ('progress_fail', 'fatal_log'):
            params = dict(params)
            params['reason'] = localize_error(params['reason'], self.lang)
        return self.text(key, **params)

    def _append_log(self, message):
        self.log_widget.configure(state='normal')
        self.log_widget.insert('end', str(message) + '\n')
        self.log_widget.see('end')
        self.log_widget.configure(state='disabled')

    def change_language(self, _event=None):
        self.apply_language()

    def apply_language(self):
        """Live translation: does not modify any source, output or job variable."""
        self.root.title(self.text('title'))
        widgets = (
            (self.heading, 'headline'), (self.subtitle, 'subtitle'),
            (self.language_label, 'language'), (self.source_frame, 'source_section'),
            (self.folder, 'folder_mode'), (self.single, 'single_mode'),
            (self.browse_src, 'browse'), (self.destination_frame, 'output_section'),
            (self.browse_dest, 'browse'), (self.run_frame, 'run_section'),
            (self.start_btn, 'start'), (self.stop_btn, 'stop'),
            (self.workers_label, 'workers'), (self.log_label, 'log_heading'),
            (self.calcdebug_frame, 'calcdebug_section'),
            (self.calcdebug_check, 'calcdebug_enable'),
            (self.calcdebug_browse, 'browse'),
            (self.calcdebug_help, 'calcdebug_help'),
        )
        for widget, key in widgets:
            widget.configure(text=self.text(key))
        key, params = self._status_record
        self.status.set(self.text(key, **params))
        key, params = self._details_record
        self.details.set(self._translate_details(key, params))
        # Existing log lines are re-rendered too, not left in the old language.
        self.log_widget.configure(state='normal')
        self.log_widget.delete('1.0', 'end')
        for key, params in self._log_records:
            self.log_widget.insert('end', self._translate_log(key, params) + '\n')
        self.log_widget.see('end')
        self.log_widget.configure(state='disabled')

    def change_mode(self):
        self.saved[self.previous_mode] = self.source_path.get()
        self.previous_mode = self.source_mode.get()
        self.source_path.set(self.saved[self.previous_mode])
        self.set_details('folder_help' if self.previous_mode == 'folder' else 'single_help')

    def choose_input(self):
        source = self.source_path.get().strip().strip('"')
        path = Path(source) if source else None
        if self.source_mode.get() == 'folder':
            opts = {'title': self.text('folder_dialog')}
            if path and path.is_dir():
                opts['initialdir'] = str(path)
            selected = filedialog.askdirectory(**opts)
        else:
            opts = {'title': self.text('image_dialog'), 'filetypes': [
                (self.text('image_type'), '*.jpg *.jpeg *.bmp'),
                (self.text('all_files'), '*.*'),
            ]}
            if path and path.exists():
                opts['initialdir'] = str(path if path.is_dir() else path.parent)
            selected = filedialog.askopenfilename(**opts)
        if selected:
            self.source_path.set(selected)
            self.preview()

    def suggest(self):
        suggestion = proposed_output(self.source_mode.get(), self.source_path.get())
        if suggestion is not None:
            old = self.output_path.get().strip()
            if not old or old == self.last_suggestion:
                self.output_path.set(str(suggestion))
                self.last_suggestion = str(suggestion)

    def preview(self, _event=None):
        try:
            paths = collect_images(self.source_mode.get(), self.source_path.get())
        except Exception as exc:
            self.set_details('_core_error', message=str(exc))
            return
        self.saved[self.source_mode.get()] = self.source_path.get()
        self.set_details('found', count=len(paths), filename=paths[0].name,
                          has_more=(len(paths) > 1))
        self.suggest()

    def choose_output(self):
        old = self.output_path.get().strip()
        opts = {'title': self.text('save_dialog'), 'defaultextension': '.txt',
                'filetypes': [('TXT', '*.txt')]}
        if old:
            path = Path(old)
            opts.update(initialdir=str(path.parent), initialfile=path.name)
        selected = filedialog.asksaveasfilename(**opts)
        if selected:
            self.output_path.set(selected)

    def toggle_calcdebug(self):
        active = self.calcdebug_enabled.get() and not self.busy
        self.calcdebug_entry.configure(state='normal' if active else 'disabled')
        self.calcdebug_browse.configure(state='normal' if active else 'disabled')

    def choose_calcdebug_dir(self):
        current = self.calcdebug_folder.get().strip().strip('"')
        opts = {'title': self.text('calcdebug_select_dir')}
        if current and Path(current).is_dir():
            opts['initialdir'] = current
        dest = filedialog.askdirectory(**opts)
        if dest:
            self.calcdebug_folder.set(dest)

    def set_running(self, running):
        self.busy = running
        for widget in (self.src_entry, self.dest_entry, self.browse_src, self.browse_dest,
                       self.folder, self.single, self.start_btn,
                       self.calcdebug_check):
            widget.configure(state='disabled' if running else 'normal')
        self.jobs.configure(state='disabled' if running else 'readonly')
        self.toggle_calcdebug()
        self.stop_btn.configure(state='normal' if running else 'disabled')
        # The language selector remains enabled while calculating.

    def start(self):
        if self.busy:
            return
        try:
            images = collect_images(self.source_mode.get(), self.source_path.get())
            self.suggest()
            destination = Path(self.output_path.get().strip().strip('"'))
            if destination.suffix.lower() != '.txt':
                raise CalculationError(self.text('choose_txt'))
            debug_root = None
            if self.calcdebug_enabled.get():
                text = self.calcdebug_folder.get().strip().strip('"')
                debug_root = Path(text).expanduser() if text else destination.parent/'CalcDebug'
                if debug_root.is_file():
                    raise CalculationError(self.text('calcdebug_bad_path',path=str(debug_root)))
        except Exception as exc:
            messagebox.showwarning(self.text('input_error_title'),
                                   localize_error(str(exc), self.lang))
            return
        if destination.exists() and not messagebox.askyesno(
                self.text('confirm_title'), self.text('confirm_overwrite', path=str(destination))):
            return
        self.stop_event.clear()
        self.set_running(True)
        self.progress.configure(value=0, maximum=len(images))
        self.set_status('running', done=0, total=len(images))
        self.log_event('started', count=len(images), source=self.source_path.get())
        self.log_event('output_log', path=str(destination))
        if debug_root is not None:
            self.log_event('calcdebug_started', path=str(debug_root))
        thread = threading.Thread(target=self.worker,
                                  args=(images, destination, int(self.workers.get()), self.lang, debug_root),
                                  daemon=True)
        thread.start()

    def stop(self):
        self.stop_event.set()
        self.stop_btn.configure(state='disabled')
        self.log_event('stop_requested')

    def worker(self, images, target, workers, language, debug_root=None):
        try:
            extra = {'calcdebug_root':debug_root} if debug_root is not None else {}
            result = calculate(images, target, self.decoder, workers=workers,
                               language=language, cancel=self.stop_event.is_set,
                               progress=lambda i, n, p, ok, detail:
                                   self.events.put(('progress', i, n, p.name, ok, detail)),
                               **extra)
            self.events.put(('finished', result))
        except Exception as exc:
            self.events.put(('fatal', f'{type(exc).__name__}: {exc}'))

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'progress':
                    _, index, total, filename, ok, detail = event
                    self.progress.configure(value=index)
                    self.set_status('running', done=index, total=total)
                    if ok:
                        self.log_event('progress_ok', done=index, total=total, filename=filename)
                    else:
                        self.log_event('progress_fail', done=index, total=total,
                                       filename=filename, reason=detail)
                elif event[0] == 'finished':
                    result = event[1]
                    self.set_running(False)
                    failed = len(result.failures)
                    if result.cancelled:
                        self.set_status('cancelled_status', success=result.successful,
                                        failed=failed, completed=result.completed, total=result.total)
                    else:
                        self.set_status('finished_status', success=result.successful,
                                        failed=failed, total=result.total)
                    self.log_event('finished_log', path=str(result.output), seconds=result.seconds)
                    if result.errors_path:
                        self.log_event('errors_log', path=str(result.errors_path))
                    if result.calcdebug_path:
                        self.log_event('calcdebug_saved', path=str(result.calcdebug_path))
                    if result.cancelled:
                        messagebox.showwarning(self.text('cancelled_title'), self.text(
                            'cancelled_body', completed=result.completed, total=result.total,
                            path=str(result.output)))
                    elif failed:
                        messagebox.showwarning(self.text('partial_title'), self.text(
                            'partial_body', success=result.successful, failed=failed, path=str(result.output)))
                    else:
                        messagebox.showinfo(self.text('done_title'), self.text(
                            'done_body', success=result.successful, path=str(result.output)))
                elif event[0] == 'fatal':
                    self.set_running(False)
                    self.set_status('fatal_status')
                    self.log_event('fatal_log', reason=event[1])
                    messagebox.showerror(self.text('fatal_title'), localize_error(event[1], self.lang))
        except queue.Empty:
            pass
        self.root.after(120, self.poll)


def launch(decoder: Path):
    root = tk.Tk()
    Window(root, decoder)
    root.mainloop()
