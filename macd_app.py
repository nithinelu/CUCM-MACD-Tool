"""CUCM MACD Tool - Move/Add/Change/Delete on Cisco Unified CM through AXL,
without opening the CUCM Administration web pages.

English / Arabic interface (Language selector, bottom right). Arabic mirrors
the layout right-to-left.

Run:  pythonw macd_app.py   (or run_app.bat)
"""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from tkinter.scrolledtext import ScrolledText

from axl_client import AXL_VERSIONS, AXLClient, AXLError, text_of
from macd_ops import BACKUP_DIR, JABBER_PRODUCTS, LOG_DIR, MACD
import bulk
import i18n
from i18n import _, en

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def title():
    return _("CUCM MACD Tool")


class App(tk.Tk):
    # search kind -> (column field, heading)
    SEARCH_COLS = {
        "Phones": [("name", "Device name"), ("description", "Description"), ("product", "Model"),
                   ("protocol", "Protocol"), ("devicePoolName", "Device pool"),
                   ("callingSearchSpaceName", "Device CSS"), ("ownerUserName", "Owner")],
        "Lines / DNs": [("pattern", "DN"), ("routePartitionName", "Partition"),
                        ("description", "Description"), ("alertingName", "Alerting name"),
                        ("shareLineAppearanceCssName", "Line CSS")],
        "Where is DN used": [("device", "Device name"), ("description", "Description"),
                             ("partition", "Partition"), ("lineindex", "Line #")],
        "Users": [("userid", "User ID"), ("firstName", "First name"), ("lastName", "Last name"),
                  ("telephoneNumber", "Telephone"), ("department", "Department"), ("mailid", "Email")],
    }
    SEARCH_COLS["Phones (by description)"] = SEARCH_COLS["Phones"]
    SEARCH_KINDS = ["Phones", "Phones (by description)", "Lines / DNs", "Where is DN used", "Users"]

    def __init__(self):
        super().__init__()
        self.geometry("1180x820")
        self.minsize(980, 680)
        ico = os.path.join(HERE, "app.ico")
        if os.path.exists(ico):
            try:
                self.iconbitmap(ico)
            except tk.TclError:
                pass
        self.cfg = load_config()
        i18n.set_language(self.cfg.get("language", "en"))
        self.axl = None
        self.macd = None
        self.lists = {}
        self.conn_info = None      # (host, cucm, ver, user) once connected
        self.ui_queue = queue.Queue()
        self.busy = False
        self._base_font_sizes = {n: tkfont.nametofont(n).cget("size")
                                 for n in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont")}
        self._build_ui()
        self.after(100, self._drain)

    # ------------------------------------------------------------------
    # layout helpers (mirror for right-to-left)
    # ------------------------------------------------------------------
    @property
    def rtl(self):
        return i18n.is_rtl()

    @property
    def S(self):              # pack side where a row starts
        return "right" if self.rtl else "left"

    @property
    def E(self):              # pack side where a row ends
        return "left" if self.rtl else "right"

    @property
    def W(self):              # sticky / anchor at the start of a row
        return "e" if self.rtl else "w"

    @property
    def J(self):              # text justification
        return "right" if self.rtl else "left"

    def col(self, n, last=2):
        """Grid column n counted from the start of the row."""
        return last - n if self.rtl else n

    def form(self, parent, rows, start_row=0):
        """rows: [(label, widget)] -> label in column 0, widget in column 1
        (mirrored in Arabic). Column 2 is free for an extra button."""
        r = start_row
        for label, w in rows:
            ttk.Label(parent, text=_(label)).grid(row=r, column=self.col(0), sticky=self.W,
                                                  padx=(4, 6), pady=2)
            w.grid(row=r, column=self.col(1), sticky="we", pady=2)
            r += 1
        parent.columnconfigure(1, weight=1)
        return r

    def tab(self, key):
        f = ttk.Frame(self.nb, padding=10)
        self.tabs[key] = f
        self.nb.add(f, text=f"  {_(key)}  ")
        return f

    # ------------------------------------------------------------------
    # build / rebuild the whole window (used for language switch)
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.title(title())
        self.combos = {}
        self.tabs = {}
        for name, size in self._base_font_sizes.items():
            # Arabic is hard to read at the default 9 pt
            tkfont.nametofont(name).configure(size=(abs(size) + 1) * (1 if size > 0 else -1)
                                              if self.rtl else size)

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        fam = tkfont.nametofont("TkDefaultFont").cget("family")
        style.configure("Status.TLabel", foreground="#555")
        style.configure("Ok.TLabel", foreground="#1a7f37")
        style.configure("Bad.TLabel", foreground="#b42318")
        style.configure("Head.TLabel", font=(fam, 11 if self.rtl else 10, "bold"))
        style.configure("Danger.TButton", foreground="#b42318")

        bar = ttk.Frame(self)
        bar.pack(fill="x", side="bottom")
        self.status = tk.StringVar(value=_("Not connected"))
        self.status_lbl = ttk.Label(bar, textvariable=self.status, style="Bad.TLabel")
        self.status_lbl.pack(side=self.S, padx=8, pady=2)
        self.lang_cb = ttk.Combobox(bar, values=list(i18n.LANGUAGES.values()), state="readonly", width=10)
        self.lang_cb.set(i18n.LANGUAGES[i18n.language()])
        self.lang_cb.bind("<<ComboboxSelected>>", self._language_picked)
        self.lang_cb.pack(side=self.E, padx=(4, 8))
        ttk.Label(bar, text="Language / اللغة").pack(side=self.E)
        self.prog = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.prog.pack(side=self.E, padx=8)

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=6, pady=6)
        self.nb = ttk.Notebook(paned)
        paned.add(self.nb, weight=4)
        logf = ttk.Frame(paned)
        paned.add(logf, weight=1)
        ttk.Label(logf, text=_("Activity log")).pack(anchor=self.W)
        self.logbox = ScrolledText(logf, height=8, font=("Consolas", 9), state="disabled")
        self.logbox.pack(fill="both", expand=True)

        self._build_connect()
        self._build_search()
        self._build_add()
        self._build_change()
        self._build_delete()
        self._build_bulk()
        if self.rtl:   # tabs read right-to-left: first tab on the right
            for key in list(self.tabs)[1:]:
                self.nb.insert(0, self.tabs[key])
        self.nb.select(self.tabs["Connection"])

        if self.conn_info:
            self._show_connected()
        self.refresh_combos()

    def _language_picked(self, _e=None):
        code = next(k for k, v in i18n.LANGUAGES.items() if v == self.lang_cb.get())
        if code == i18n.language():
            return
        if self.busy:
            self.lang_cb.set(i18n.LANGUAGES[i18n.language()])
            messagebox.showinfo(title(), _("Please wait for the current operation to finish."))
            return
        # keep what the user typed on the Connection tab and the log
        keep = {"host": self.c_host.get(), "port": self.c_port.get(), "user": self.c_user.get(),
                "pw": self.c_pass.get(), "ver": self.c_ver.get()}
        log_text = self.logbox.get("1.0", "end-1c").rstrip()
        i18n.set_language(code)
        self.cfg["language"] = code
        save_config(self.cfg)
        for w in self.winfo_children():
            w.destroy()
        self._build_ui()
        for w, k in ((self.c_host, "host"), (self.c_port, "port"), (self.c_user, "user"),
                     (self.c_pass, "pw")):
            self._set(w, keep[k])
        self.c_ver.set(keep["ver"])
        if log_text:
            self.logbox.configure(state="normal")
            self.logbox.insert("end", log_text + "\n")
            self.logbox.configure(state="disabled")
        self.log(en("Language changed to Arabic.") if code == "ar" else "Language changed to English.")

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------
    def log(self, msg):
        self.ui_queue.put(("log", msg))

    def _drain(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", payload + "\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "call":
                    payload()
        except queue.Empty:
            pass
        except tk.TclError:
            pass
        self.after(100, self._drain)

    def run_bg(self, fn, done=None, label="Working..."):
        """Run fn() in a thread; done(result) on the UI thread. Errors -> dialog.
        `label` is an English key, translated here."""
        if self.busy:
            messagebox.showinfo(title(), _("Please wait for the current operation to finish."))
            return
        self.busy = True
        self.prog.start(12)
        old = self.status.get()
        self.status.set(_(label))

        def work():
            try:
                res, err = fn(), None
            except AXLError as e:
                res, err = None, str(e)
            except Exception as e:  # noqa: BLE001 - surface anything to the user
                res, err = None, f"{type(e).__name__}: {e}"

            def finish():
                self.busy = False
                self.prog.stop()
                self.status.set(old)
                if err:
                    self.log(en("ERROR: {err}", err=err))
                    messagebox.showerror(title(), err)
                elif done:
                    done(res)
            self.ui_queue.put(("call", finish))
        threading.Thread(target=work, daemon=True).start()

    def need_conn(self):
        if not self.macd:
            messagebox.showwarning(title(), _("Connect to CUCM first (Connection tab)."))
            return False
        return True

    def ask(self, text):
        return messagebox.askyesno(title(), text)

    def info(self, text):
        messagebox.showinfo(title(), text)

    def combo(self, parent, key=None, width=38, values=None):
        cb = ttk.Combobox(parent, width=width, values=values or self.lists.get(key, []))
        if key:
            self.combos.setdefault(key, []).append(cb)
            cb.bind("<KeyRelease>", lambda e, c=cb, k=key: self._filter_combo(c, k, e))
        return cb

    def _filter_combo(self, cb, key, event):
        if event.keysym in ("Up", "Down", "Return", "Tab", "Escape"):
            return
        text = cb.get().lower()
        full = self.lists.get(key, [])
        cb["values"] = [v for v in full if text in v.lower()] if text else full

    def refresh_combos(self):
        for key, boxes in self.combos.items():
            for cb in boxes:
                cb["values"] = self.lists.get(key, [])

    def mirror(self, tree):
        """Arabic: show table columns right-to-left."""
        cols = list(tree["columns"])
        tree["displaycolumns"] = cols[::-1] if self.rtl else cols

    @staticmethod
    def _set(widget, value):
        widget.delete(0, "end")
        widget.insert(0, value or "")

    @staticmethod
    def _changes_text(changes, before):
        return "\n".join(f"{_(k)}: '{before.get(k, '')}' → '{v}'" for k, v in changes.items())

    # ------------------------------------------------------------------
    # Connection tab
    # ------------------------------------------------------------------
    def _build_connect(self):
        f = self.tab("Connection")
        f.configure(padding=14)
        ttk.Label(f, text=_("Connect to CUCM over AXL (no CCMAdmin login needed)"),
                  style="Head.TLabel").grid(row=0, column=0, columnspan=3, sticky=self.W, pady=(0, 10))
        self.c_host = ttk.Entry(f, width=40)
        self.c_host.insert(0, self.cfg.get("host", ""))
        self.c_port = ttk.Entry(f, width=8)
        self.c_port.insert(0, str(self.cfg.get("port", 8443)))
        self.c_user = ttk.Entry(f, width=40)
        self.c_user.insert(0, self.cfg.get("username", ""))
        self.c_pass = ttk.Entry(f, width=40, show="•")
        self.c_ver = ttk.Combobox(f, width=10, values=AXL_VERSIONS)
        self.c_ver.set(self.cfg.get("version", "14.0"))
        self.c_verify = tk.BooleanVar(value=self.cfg.get("verify_tls", False))
        r = self.form(f, [("CUCM publisher (IP / FQDN)", self.c_host), ("AXL port", self.c_port),
                          ("AXL username", self.c_user), ("Password", self.c_pass),
                          ("AXL version", self.c_ver)], start_row=1)
        ttk.Checkbutton(f, text=_("Verify TLS certificate"), variable=self.c_verify).grid(
            row=r, column=self.col(1), sticky=self.W, pady=4)
        btns = ttk.Frame(f)
        btns.grid(row=r + 1, column=self.col(1), sticky=self.W, pady=8)
        ttk.Button(btns, text=_("Connect"), command=self.connect).pack(side=self.S)
        ttk.Button(btns, text=_("Detect version + connect"),
                   command=lambda: self.connect(detect=True)).pack(side=self.S, padx=6)
        ttk.Button(btns, text=_("Reload drop-down lists"), command=self.load_lists).pack(side=self.S)
        self.c_info = ttk.Label(f, text="", style="Status.TLabel", justify=self.J)
        self.c_info.grid(row=r + 2, column=0, columnspan=3, sticky=self.W, pady=6)
        self.c_pass.bind("<Return>", lambda e: self.connect())

        note = _("The AXL user needs the 'Standard AXL API Access' role (an application user is best).\n"
                 "The password is never saved; host, user and version are remembered in config.json.\n"
                 "Every change is logged to {log}\\audit_<month>.csv and the object is snapshotted\n"
                 "to {backup} before it is changed or deleted.", log=LOG_DIR, backup=BACKUP_DIR)
        ttk.Label(f, text=note, style="Status.TLabel", justify=self.J).grid(
            row=r + 3, column=0, columnspan=3, sticky=self.W, pady=(18, 0))

    def connect(self, detect=False):
        host, user, pw = self.c_host.get().strip(), self.c_user.get().strip(), self.c_pass.get()
        if not (host and user and pw):
            messagebox.showwarning(title(), _("Host, username and password are required."))
            return
        try:
            port = int(self.c_port.get() or 8443)
        except ValueError:
            messagebox.showwarning(title(), _("Port must be a number."))
            return
        client = AXLClient(host, user, pw, self.c_ver.get().strip() or "14.0", port,
                           self.c_verify.get())

        def work():
            if detect:
                ver, cucm = client.detect_version()
            else:
                ver, cucm = client.version, client.get_version()
            macd = MACD(client, log=self.log, operator=user)
            return ver, cucm, macd, macd.dropdowns()

        def done(res):
            ver, cucm, macd, lists = res
            self.axl, self.macd, self.lists = client, macd, lists
            self.conn_info = (host, cucm, ver, user)
            self.c_ver.set(ver)
            self.cfg.update(host=host, port=port, username=user, version=ver,
                            verify_tls=self.c_verify.get())
            save_config(self.cfg)
            self.refresh_combos()
            self._show_connected()
            self.log(en("Connected to {host} - CUCM {cucm}, AXL {ver}", host=host, cucm=cucm, ver=ver))
            self.nb.select(self.tabs["Search"])
        self.run_bg(work, done, "Connecting...")

    def _show_connected(self):
        host, cucm, ver, user = self.conn_info
        self.status.set(_("Connected: {host}  |  CUCM {cucm}  |  AXL {ver}  |  {user}",
                          host=host, cucm=cucm, ver=ver, user=user))
        self.status_lbl.configure(style="Ok.TLabel")
        counts = ", ".join(f"{_(k)} {len(v)}" for k, v in self.lists.items())
        self.c_info.configure(text=_("Connected to CUCM {cucm} (AXL schema {ver}).\nLoaded: {counts}",
                                     cucm=cucm, ver=ver, counts=counts), style="Ok.TLabel")

    def load_lists(self):
        if not self.need_conn():
            return

        def done(lists):
            self.lists = lists
            self.refresh_combos()
            self.log(en("Drop-down lists reloaded"))
        self.run_bg(self.macd.dropdowns, done, "Loading lists...")

    # ------------------------------------------------------------------
    # Search tab
    # ------------------------------------------------------------------
    def _build_search(self):
        f = self.tab("Search")
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.s_type = ttk.Combobox(top, values=[_(k) for k in self.SEARCH_KINDS], state="readonly",
                                   width=26)
        self.s_type.current(0)
        self.s_text = ttk.Entry(top, width=40)
        ttk.Label(top, text=_("Find")).pack(side=self.S)
        self.s_type.pack(side=self.S, padx=6)
        ttk.Label(top, text=_("containing")).pack(side=self.S)
        self.s_text.pack(side=self.S, padx=6)
        ttk.Button(top, text=_("Search"), command=self.search).pack(side=self.S)
        ttk.Button(top, text=_("Export to Excel"), command=self.export_search).pack(side=self.S, padx=6)
        self.s_count = ttk.Label(top, text="", style="Status.TLabel")
        self.s_count.pack(side=self.S, padx=6)
        self.s_text.bind("<Return>", lambda e: self.search())

        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True, pady=8)
        self.s_tree = ttk.Treeview(tf, show="headings", selectmode="browse")
        ys = ttk.Scrollbar(tf, orient="vertical", command=self.s_tree.yview)
        xs = ttk.Scrollbar(tf, orient="horizontal", command=self.s_tree.xview)
        self.s_tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.s_tree.grid(row=0, column=self.col(0, 1), sticky="nsew")
        ys.grid(row=0, column=self.col(1, 1), sticky="ns")
        xs.grid(row=1, column=self.col(0, 1), sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(self.col(0, 1), weight=1)
        self.s_tree.bind("<Double-1>", lambda e: self.open_selected())

        bot = ttk.Frame(f)
        bot.pack(fill="x")
        ttk.Button(bot, text=_("Open in Change / Move"), command=self.open_selected).pack(side=self.S)
        ttk.Button(bot, text=_("Open in Delete"), command=lambda: self.open_selected("delete")).pack(
            side=self.S, padx=6)
        ttk.Label(bot, text=_("Tip: double-click a phone or DN to edit it. '%' wildcards work."),
                  style="Status.TLabel").pack(side=self.S, padx=10)
        self.s_rows = []
        self.s_kind = None

    def search(self):
        if not self.need_conn():
            return
        kind = self.SEARCH_KINDS[self.s_type.current()]
        text = self.s_text.get().strip()
        fn = {
            "Phones": lambda: self.macd.search_phones(text),
            "Phones (by description)": lambda: self.macd.search_phones(text, "description"),
            "Lines / DNs": lambda: self.macd.search_lines(text),
            "Where is DN used": lambda: self.macd.where_is_line(text),
            "Users": lambda: self.macd.search_users(text),
        }[kind]

        def done(rows):
            cols = self.SEARCH_COLS[kind]
            self.s_tree.delete(*self.s_tree.get_children())
            self.s_tree["columns"] = [c for c, _h in cols]
            for c, head in cols:
                self.s_tree.heading(c, text=_(head), command=lambda c=c: self._sort(c))
                self.s_tree.column(c, width=220 if c == "description" else 140, stretch=True)
            self.mirror(self.s_tree)
            self.s_rows, self.s_kind = rows, kind
            for r in rows:
                self.s_tree.insert("", "end", values=[r.get(c, "") for c, _h in cols])
            self.s_count.configure(text=_("{n} result(s)", n=len(rows)))
        self.run_bg(fn, done, "Searching...")

    def _sort(self, col):
        items = [(self.s_tree.set(i, col), i) for i in self.s_tree.get_children("")]
        rev = getattr(self, "_sort_rev", False)
        items.sort(key=lambda t: t[0].lower(), reverse=rev)
        for n, (_v, i) in enumerate(items):
            self.s_tree.move(i, "", n)
        self._sort_rev = not rev

    def export_search(self):
        if not self.s_rows:
            self.info(_("Nothing to export - run a search first."))
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                            initialfile=f"cucm_{self.s_kind.split()[0].lower()}.xlsx")
        if not path:
            return
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        if self.rtl:
            ws.sheet_view.rightToLeft = True
        cols = self.SEARCH_COLS[self.s_kind]
        ws.append([_(h) for _c, h in cols])
        for r in self.s_rows:
            ws.append([r.get(c, "") for c, _h in cols])
        wb.save(path)
        self.log(en("Exported {n} rows to {path}", n=len(self.s_rows), path=path))

    def open_selected(self, where="change"):
        sel = self.s_tree.selection()
        if not sel:
            return
        vals = dict(zip(self.s_tree["columns"], self.s_tree.item(sel[0], "values")))
        if "name" in vals or "device" in vals:
            dev = vals.get("name") or vals.get("device")
            if where == "delete":
                self._set(self.d_name, dev)
                self.nb.select(self.tabs["Delete"])
                self.delete_lookup()
            else:
                self._set(self.ch_name, dev)
                self.nb.select(self.tabs["Change / Move"])
                self.load_phone()
        elif "pattern" in vals:
            self._set(self.ln_dn, vals["pattern"])
            self._set(self.ln_pt, vals.get("routePartitionName", ""))
            if where == "delete":
                self._set(self.dl_dn, vals["pattern"])
                self._set(self.dl_pt, vals.get("routePartitionName", ""))
                self.nb.select(self.tabs["Delete"])
            else:
                self.nb.select(self.tabs["Change / Move"])
                self.load_line()

    # ------------------------------------------------------------------
    # Add tab
    # ------------------------------------------------------------------
    def _build_add(self):
        f = self.tab("Add")
        dev = ttk.LabelFrame(f, text=_("Device"), padding=8, labelanchor="n" + self.W)
        dev.grid(row=0, column=self.col(0, 1), sticky="nsew", padx=6)
        line = ttk.LabelFrame(f, text=_("Line (DN)"), padding=8, labelanchor="n" + self.W)
        line.grid(row=0, column=self.col(1, 1), sticky="nsew", padx=6)
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

        self.a_product = self.combo(dev, "products")
        self.a_product.bind("<<ComboboxSelected>>", lambda e: self._product_defaults())
        self.a_name = ttk.Entry(dev, width=40)
        self.a_protocol = ttk.Combobox(dev, values=["SIP", "SCCP"], width=10, state="readonly")
        self.a_protocol.set("SIP")
        self.a_desc = ttk.Entry(dev, width=40)
        self.a_owner = ttk.Entry(dev, width=40)
        self.a_dp = self.combo(dev, "devicePools")
        self.a_css = self.combo(dev, "css")
        self.a_loc = self.combo(dev, "locations")
        self.a_tpl = self.combo(dev, "buttonTemplates")
        self.a_sec = self.combo(dev, "securityProfiles")
        self.a_sip = self.combo(dev, "sipProfiles")
        self.form(dev, [("Product / model *", self.a_product),
                        ("Device name * (SEPmac / CSFuser)", self.a_name),
                        ("Protocol", self.a_protocol), ("Description", self.a_desc),
                        ("Owner user ID", self.a_owner), ("Device pool *", self.a_dp),
                        ("Device CSS", self.a_css), ("Location", self.a_loc),
                        ("Phone button template", self.a_tpl),
                        ("Device security profile", self.a_sec), ("SIP profile", self.a_sip)])
        ttk.Button(dev, text=_("Fill from user"), command=self._fill_from_user).grid(
            row=4, column=self.col(2), padx=4)

        self.a_dn = ttk.Entry(line, width=30)
        self.a_pt = self.combo(line, "partitions")
        self.a_alert = ttk.Entry(line, width=30)
        self.a_ldesc = ttk.Entry(line, width=30)
        self.a_lcss = self.combo(line, "css")
        self.a_vm = self.combo(line, "voicemailProfiles")
        self.a_e164 = ttk.Entry(line, width=30)
        self.a_cfa = ttk.Entry(line, width=30)
        self.a_cfacss = self.combo(line, "css")
        self.form(line, [("Directory number", self.a_dn), ("Partition", self.a_pt),
                         ("Alerting / display name", self.a_alert),
                         ("Line description", self.a_ldesc), ("Line CSS", self.a_lcss),
                         ("Voicemail profile", self.a_vm), ("External mask (E.164)", self.a_e164),
                         ("Call forward all to", self.a_cfa), ("CFA CSS", self.a_cfacss)])
        ttk.Button(line, text=_("Check DN"), command=self._check_dn).grid(
            row=0, column=self.col(2), padx=4)
        ttk.Label(line, text=_("An existing DN is reused (shared line);\na new DN is created."),
                  style="Status.TLabel", justify=self.J).grid(
            row=10, column=0, columnspan=3, sticky=self.W, pady=8)

        b = ttk.Frame(f)
        b.grid(row=1, column=0, columnspan=2, sticky=self.W, pady=10, padx=6)
        ttk.Button(b, text=_("Add device"), command=self.add_device).pack(side=self.S)
        ttk.Button(b, text=_("Clear"), command=self._clear_add).pack(side=self.S, padx=6)
        self.a_last = ttk.Label(b, text="", style="Ok.TLabel")
        self.a_last.pack(side=self.S, padx=10)

    def _product_defaults(self):
        prod = self.a_product.get()
        prefix = JABBER_PRODUCTS.get(prod)
        name = self.a_name.get().strip()
        if prefix and not name:
            self.a_name.insert(0, prefix)
        elif not prefix and not name:
            self.a_name.insert(0, "SEP")
        model = prod.replace("Cisco ", "").strip()
        tpls = self.lists.get("buttonTemplates", [])
        if model and not self.a_tpl.get():
            want = f"Standard {model} {self.a_protocol.get()}"
            cand = [t for t in tpls if t.lower() == want.lower()] or \
                   [t for t in tpls if model.lower() in t.lower()]
            if cand:
                self.a_tpl.set(cand[0])
        if not self.a_sec.get():
            secs = self.lists.get("securityProfiles", [])
            want = f"{prod} - Standard {self.a_protocol.get()} Non-Secure Profile"
            cand = [s for s in secs if s.lower() == want.lower()] or \
                   [s for s in secs if s.lower().startswith(prod.lower() + " -")
                    and "non-secure" in s.lower()]
            if cand:
                self.a_sec.set(cand[0])
        if not self.a_sip.get() and "Standard SIP Profile" in self.lists.get("sipProfiles", []):
            self.a_sip.set("Standard SIP Profile")

    def _fill_from_user(self):
        uid = self.a_owner.get().strip()
        if not uid or not self.need_conn():
            return

        def done(u):
            full = " ".join(x for x in (text_of(u.get("firstName")), text_of(u.get("lastName"))) if x)
            if full and not self.a_alert.get():
                self.a_alert.insert(0, full)
            if full and not self.a_desc.get():
                self.a_desc.insert(0, f"{full} - {self.a_product.get().replace('Cisco ', '')}")
            if full and not self.a_ldesc.get():
                self.a_ldesc.insert(0, full)
            tel = text_of(u.get("telephoneNumber"))
            if tel and not self.a_dn.get():
                self.a_dn.insert(0, "".join(c for c in tel if c.isdigit() or c == "+")[-4:])
            if JABBER_PRODUCTS.get(self.a_product.get()) and \
                    self.a_name.get().strip() in JABBER_PRODUCTS.values():
                self.a_name.insert("end", uid.upper().replace(".", "")[:12])
            self.log(en("User {uid}: {full} tel={tel}", uid=uid, full=full or "(no name)",
                       tel=tel or "-"))
        self.run_bg(lambda: self.macd.get_user(uid), done, "Reading user...")

    def _check_dn(self):
        dn = self.a_dn.get().strip()
        if not dn or not self.need_conn():
            return

        def done(rows):
            if rows:
                where = ", ".join(f"{r.get('device')} ({r.get('partition') or '<None>'})" for r in rows)
                self.info(_("DN {dn} is already used on:\n{where}", dn=dn, where=where))
            else:
                self.info(_("DN {dn} is not assigned to any device.", dn=dn))
        self.run_bg(lambda: self.macd.where_is_line(dn), done, "Checking DN...")

    def _clear_add(self):
        for w in (self.a_name, self.a_desc, self.a_owner, self.a_dn, self.a_alert, self.a_ldesc,
                  self.a_e164, self.a_cfa):
            w.delete(0, "end")
        self.a_last.configure(text="")

    def add_device(self):
        if not self.need_conn():
            return
        spec = {
            "name": self.a_name.get().strip(), "product": self.a_product.get().strip(),
            "protocol": self.a_protocol.get(), "description": self.a_desc.get().strip(),
            "owner": self.a_owner.get().strip(), "devicePool": self.a_dp.get().strip(),
            "css": self.a_css.get().strip(), "location": self.a_loc.get().strip(),
            "buttonTemplate": self.a_tpl.get().strip(), "securityProfile": self.a_sec.get().strip(),
            "sipProfile": self.a_sip.get().strip(), "dn": self.a_dn.get().strip(),
            "partition": self.a_pt.get().strip(), "alerting": self.a_alert.get().strip(),
            "lineDescription": self.a_ldesc.get().strip(), "lineCss": self.a_lcss.get().strip(),
            "vmProfile": self.a_vm.get().strip(), "e164Mask": self.a_e164.get().strip(),
            "cfaDest": self.a_cfa.get().strip(), "cfaCss": self.a_cfacss.get().strip(),
        }
        if not all(spec[k] for k in ("name", "product", "devicePool")):
            messagebox.showwarning(title(), _("Required: product, device name and device pool."))
            return
        if spec["name"].upper().startswith("SEP") and len(spec["name"]) != 15:
            if not self.ask(_("'{name}' is not SEP + 12 hex digits. Continue?", name=spec["name"])):
                return
        summary = _("Add {product} {name}\nDevice pool: {dp}\nDN: {dn} / {pt}\nOwner: {owner}",
                    product=spec["product"], name=spec["name"], dp=spec["devicePool"],
                    dn=spec["dn"] or "-", pt=spec["partition"] or "<None>", owner=spec["owner"] or "-")
        if not self.ask(summary + "\n\n" + _("Proceed?")):
            return

        def done(name):
            self.a_last.configure(text=_("Added {name}", name=name))
            self.info(_("{name} added.", name=name))
        self.run_bg(lambda: self.macd.add_phone(spec), done, "Adding device...")

    # ------------------------------------------------------------------
    # Change / Move tab
    # ------------------------------------------------------------------
    def _build_change(self):
        f = self.tab("Change / Move")
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

        # -- device panel
        pf = ttk.LabelFrame(f, text=_("Device"), padding=8, labelanchor="n" + self.W)
        pf.grid(row=0, column=self.col(0, 1), sticky="nsew", padx=6)
        top = ttk.Frame(pf)
        top.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 6))
        ttk.Label(top, text=_("Device name")).pack(side=self.S)
        self.ch_name = ttk.Entry(top, width=24)
        self.ch_name.pack(side=self.S, padx=6)
        self.ch_name.bind("<Return>", lambda e: self.load_phone())
        ttk.Button(top, text=_("Load"), command=self.load_phone).pack(side=self.S)
        self.ch_info = ttk.Label(pf, text="", style="Status.TLabel")
        self.ch_info.grid(row=1, column=0, columnspan=3, sticky=self.W)
        self.ch_desc = ttk.Entry(pf, width=38)
        self.ch_dp = self.combo(pf, "devicePools")
        self.ch_css = self.combo(pf, "css")
        self.ch_loc = self.combo(pf, "locations")
        self.ch_tpl = self.combo(pf, "buttonTemplates")
        self.ch_owner = ttk.Entry(pf, width=38)
        self.ch_newname = ttk.Entry(pf, width=38)
        self.form(pf, [("Description", self.ch_desc), ("Device pool", self.ch_dp),
                       ("Device CSS", self.ch_css), ("Location", self.ch_loc),
                       ("Button template", self.ch_tpl), ("Owner user ID", self.ch_owner),
                       ("New device name (MAC swap)", self.ch_newname)], start_row=2)
        pb = ttk.Frame(pf)
        pb.grid(row=9, column=0, columnspan=3, sticky=self.W, pady=8)
        ttk.Button(pb, text=_("Save device changes"), command=self.save_phone).pack(side=self.S)
        ttk.Button(pb, text=_("Restart"), command=lambda: self._device_action("restart")).pack(
            side=self.S, padx=6)
        ttk.Button(pb, text=_("Reset"), command=lambda: self._device_action("reset")).pack(side=self.S)
        ttk.Label(pf, text=_("Only fields you change are sent. Apply Config is pushed automatically."),
                  style="Status.TLabel", wraplength=430, justify=self.J).grid(
            row=10, column=0, columnspan=3, sticky=self.W)

        lf = ttk.Frame(pf)
        lf.grid(row=11, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        self.ch_lines = ttk.Treeview(lf, columns=("idx", "dn", "pt", "label"), show="headings", height=5)
        for c, t, w in (("idx", "#", 30), ("dn", "DN", 90), ("pt", "Partition", 130), ("label", "Label", 160)):
            self.ch_lines.heading(c, text=_(t) if t != "#" else t)
            self.ch_lines.column(c, width=w, stretch=(c == "label"))
        self.mirror(self.ch_lines)
        self.ch_lines.pack(fill="both", expand=True)
        self.ch_lines.bind("<<TreeviewSelect>>", self._line_picked)
        pf.rowconfigure(11, weight=1)
        self.ch_loaded = {}

        # -- line panel
        right = ttk.Frame(f)
        right.grid(row=0, column=self.col(1, 1), sticky="nsew", padx=6)
        lf2 = ttk.LabelFrame(right, text=_("Line (DN)"), padding=8, labelanchor="n" + self.W)
        lf2.pack(fill="x")
        top2 = ttk.Frame(lf2)
        top2.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 6))
        ttk.Label(top2, text=_("DN")).pack(side=self.S)
        self.ln_dn = ttk.Entry(top2, width=14)
        self.ln_dn.pack(side=self.S, padx=4)
        ttk.Label(top2, text=_("Partition")).pack(side=self.S)
        self.ln_pt = self.combo(top2, "partitions", width=18)
        self.ln_pt.pack(side=self.S, padx=4)
        ttk.Button(top2, text=_("Load"), command=self.load_line).pack(side=self.S)
        self.ln_alert = ttk.Entry(lf2, width=34)
        self.ln_desc = ttk.Entry(lf2, width=34)
        self.ln_css = self.combo(lf2, "css")
        self.ln_vm = self.combo(lf2, "voicemailProfiles")
        self.ln_cfa = ttk.Entry(lf2, width=34)
        self.ln_cfacss = self.combo(lf2, "css")
        self.ln_newdn = ttk.Entry(lf2, width=34)
        self.ln_newpt = self.combo(lf2, "partitions")
        self.form(lf2, [("Alerting name", self.ln_alert), ("Description", self.ln_desc),
                        ("Line CSS", self.ln_css), ("Voicemail profile", self.ln_vm),
                        ("Call forward all to", self.ln_cfa), ("CFA CSS", self.ln_cfacss),
                        ("Change DN to", self.ln_newdn), ("Move to partition", self.ln_newpt)],
                  start_row=1)
        ttk.Button(lf2, text=_("Save line changes"), command=self.save_line).grid(
            row=9, column=self.col(1), sticky=self.W, pady=8)
        ttk.Label(lf2, text=_("Clear 'Call forward all to' and save to cancel CFA."),
                  style="Status.TLabel").grid(row=10, column=0, columnspan=3, sticky=self.W)
        self.ln_loaded = {}

        mv = ttk.LabelFrame(right, text=_("Move / share this DN to another device"), padding=8,
                            labelanchor="n" + self.W)
        mv.pack(fill="x", pady=(10, 0))
        ttk.Label(mv, text=_("Target device")).grid(row=0, column=self.col(0), sticky=self.W)
        self.mv_target = ttk.Entry(mv, width=26)
        self.mv_target.grid(row=0, column=self.col(1), sticky="we", padx=6)
        self.mv_keep = tk.BooleanVar(value=False)
        ttk.Checkbutton(mv, text=_("Keep on current device (shared line)"), variable=self.mv_keep).grid(
            row=1, column=self.col(1), sticky=self.W, pady=4)
        mb = ttk.Frame(mv)
        mb.grid(row=2, column=self.col(1), sticky=self.W)
        ttk.Button(mb, text=_("Move / share DN"), command=self.move_dn).pack(side=self.S)
        ttk.Button(mb, text=_("Remove DN from device"), command=self.remove_dn).pack(side=self.S, padx=6)
        ttk.Label(mv, text=_("Source device = the device loaded on the left."),
                  style="Status.TLabel").grid(row=3, column=0, columnspan=3, sticky=self.W, pady=(6, 0))
        mv.columnconfigure(1, weight=1)

    def load_phone(self):
        name = self.ch_name.get().strip()
        if not name or not self.need_conn():
            return

        def done(p):
            self.ch_loaded = {
                "name": text_of(p.get("name")), "description": text_of(p.get("description")),
                "devicePoolName": text_of(p.get("devicePoolName")),
                "callingSearchSpaceName": text_of(p.get("callingSearchSpaceName")),
                "locationName": text_of(p.get("locationName")),
                "phoneTemplateName": text_of(p.get("phoneTemplateName")),
                "ownerUserName": text_of(p.get("ownerUserName")),
            }
            for w, k in ((self.ch_desc, "description"), (self.ch_dp, "devicePoolName"),
                         (self.ch_css, "callingSearchSpaceName"), (self.ch_loc, "locationName"),
                         (self.ch_tpl, "phoneTemplateName"), (self.ch_owner, "ownerUserName")):
                self._set(w, self.ch_loaded[k])
            self.ch_newname.delete(0, "end")
            self.ch_info.configure(text=f"{text_of(p.get('product'))} / {text_of(p.get('protocol'))}")
            self.ch_lines.delete(*self.ch_lines.get_children())
            for idx, dn, pt, ln in self.macd.phone_lines(p):
                self.ch_lines.insert("", "end", values=(idx, dn, pt, text_of(ln.get("label"))))
            self.log(en("Loaded {name}", name=name))
        self.run_bg(lambda: self.macd.get_phone(name), done, "Loading device...")

    def _line_picked(self, _e=None):
        sel = self.ch_lines.selection()
        if sel:
            _i, dn, pt, _l = self.ch_lines.item(sel[0], "values")
            self._set(self.ln_dn, dn)
            self._set(self.ln_pt, pt)
            self.load_line()

    def save_phone(self):
        if not self.ch_loaded or not self.need_conn():
            self.info(_("Load a device first."))
            return
        name = self.ch_loaded["name"]
        changes = {}
        for w, k in ((self.ch_desc, "description"), (self.ch_dp, "devicePoolName"),
                     (self.ch_css, "callingSearchSpaceName"), (self.ch_loc, "locationName"),
                     (self.ch_tpl, "phoneTemplateName"), (self.ch_owner, "ownerUserName")):
            v = w.get().strip()
            if v != self.ch_loaded[k]:
                changes[k] = v
        new = self.ch_newname.get().strip()
        if new and new != name:
            changes["newName"] = new.upper() if new.upper().startswith("SEP") else new
        if not changes:
            self.info(_("No changes."))
            return
        before = dict(self.ch_loaded, newName=name)
        if not self.ask(_("Update {name}:\n\n{changes}\n\nProceed?", name=name,
                          changes=self._changes_text(changes, before))):
            return

        def work():
            new_name = self.macd.update_phone(name, changes)
            owner_new = changes.get("ownerUserName")
            if owner_new:
                try:
                    self.macd.associate_device_to_user(owner_new, new_name)
                except AXLError as e:
                    self.log(en("Warning: could not associate {dev} to {user}: {err}",
                               dev=new_name, user=owner_new, err=e))
            return new_name

        def done(new_name):
            self._set(self.ch_name, new_name)
            self.load_phone()
        self.run_bg(work, done, "Updating device...")

    def _device_action(self, what):
        name = self.ch_name.get().strip()
        if not name or not self.need_conn():
            return
        q = "Restart {name}? Calls in progress will drop." if what == "restart" else \
            "Reset {name}? Calls in progress will drop."
        if not self.ask(_(q, name=name)):
            return
        fn = self.macd.restart_phone if what == "restart" else self.macd.reset_phone
        self.run_bg(lambda: fn(name), None, "Restarting..." if what == "restart" else "Resetting...")

    def load_line(self):
        dn, pt = self.ln_dn.get().strip(), self.ln_pt.get().strip()
        if not dn or not self.need_conn():
            return

        def done(ln):
            cfa = ln.get("callForwardAll") or {}
            cfa = cfa if isinstance(cfa, dict) else {}
            self.ln_loaded = {
                "dn": dn, "pt": pt,
                "alertingName": text_of(ln.get("alertingName")),
                "description": text_of(ln.get("description")),
                "shareLineAppearanceCssName": text_of(ln.get("shareLineAppearanceCssName")),
                "voiceMailProfileName": text_of(ln.get("voiceMailProfileName")),
                "cfaDest": text_of(cfa.get("destination")),
                "cfaCss": text_of(cfa.get("callingSearchSpaceName")),
            }
            for w, k in ((self.ln_alert, "alertingName"), (self.ln_desc, "description"),
                         (self.ln_css, "shareLineAppearanceCssName"),
                         (self.ln_vm, "voiceMailProfileName"), (self.ln_cfa, "cfaDest"),
                         (self.ln_cfacss, "cfaCss")):
                self._set(w, self.ln_loaded[k])
            self.ln_newdn.delete(0, "end")
            self.ln_newpt.set("")
            self.log(en("Loaded line {dn}/{pt}", dn=dn, pt=pt or "<None>"))
        self.run_bg(lambda: self.macd.get_line(dn, pt), done, "Loading line...")

    def save_line(self):
        if not self.ln_loaded or not self.need_conn():
            self.info(_("Load a line first."))
            return
        L = self.ln_loaded
        changes = {}
        for w, k in ((self.ln_alert, "alertingName"), (self.ln_desc, "description"),
                     (self.ln_css, "shareLineAppearanceCssName"),
                     (self.ln_vm, "voiceMailProfileName"), (self.ln_cfa, "cfaDest"),
                     (self.ln_cfacss, "cfaCss")):
            v = w.get().strip()
            if v != L[k]:
                changes[k] = v
        if self.ln_newdn.get().strip() and self.ln_newdn.get().strip() != L["dn"]:
            changes["newPattern"] = self.ln_newdn.get().strip()
        if self.ln_newpt.get().strip() and self.ln_newpt.get().strip() != L["pt"]:
            changes["newPartition"] = self.ln_newpt.get().strip()
        if not changes:
            self.info(_("No changes."))
            return
        before = dict(L, newPattern=L["dn"], newPartition=L["pt"])
        if not self.ask(_("Update line {dn}/{pt}:\n\n{changes}\n\nProceed?", dn=L["dn"],
                          pt=L["pt"] or "<None>", changes=self._changes_text(changes, before))):
            return

        def done(_r):
            if changes.get("newPattern"):
                self._set(self.ln_dn, changes["newPattern"])
            if changes.get("newPartition"):
                self._set(self.ln_pt, changes["newPartition"])
            self.load_line()
        self.run_bg(lambda: self.macd.update_line(L["dn"], L["pt"], changes), done, "Updating line...")

    def move_dn(self):
        dn, pt = self.ln_dn.get().strip(), self.ln_pt.get().strip()
        target = self.mv_target.get().strip()
        src = self.ch_loaded.get("name", "")
        if not (dn and target) or not self.need_conn():
            self.info(_("Enter the DN (right) and a target device."))
            return
        keep = self.mv_keep.get()
        share = keep or not src
        q = "Share {dn}/{pt}\nfrom: {src}\nto: {target}?" if share else \
            "Move {dn}/{pt}\nfrom: {src}\nto: {target}?"
        if not self.ask(_(q, dn=dn, pt=pt or "<None>", src=src or "-", target=target)):
            return

        def done(_r):
            if src:
                self.load_phone()
        self.run_bg(lambda: self.macd.move_line(dn, pt, src, target, keep_shared=keep), done,
                    "Sharing line..." if share else "Moving line...")

    def remove_dn(self):
        dn, pt = self.ln_dn.get().strip(), self.ln_pt.get().strip()
        src = self.ch_loaded.get("name", "")
        if not (dn and src) or not self.need_conn():
            self.info(_("Load a device and select one of its lines."))
            return
        if not self.ask(_("Remove {dn}/{pt} from {src}?\n(The DN itself is kept.)",
                          dn=dn, pt=pt or "<None>", src=src)):
            return

        def work():
            self.macd.remove_line_from_phone(src, dn, pt)
            self.macd.apply_phone(src)
        self.run_bg(work, lambda _r: self.load_phone(), "Removing line...")

    # ------------------------------------------------------------------
    # Delete tab
    # ------------------------------------------------------------------
    def _build_delete(self):
        f = self.tab("Delete")
        df = ttk.LabelFrame(f, text=_("Delete device"), padding=10, labelanchor="n" + self.W)
        df.pack(fill="x")
        ttk.Label(df, text=_("Device name")).grid(row=0, column=self.col(0), sticky=self.W)
        self.d_name = ttk.Entry(df, width=28)
        self.d_name.grid(row=0, column=self.col(1), sticky=self.W, padx=6)
        ttk.Button(df, text=_("Look up"), command=self.delete_lookup).grid(
            row=0, column=self.col(2), sticky=self.W)
        df.columnconfigure(self.col(2), weight=1)
        self.d_info = ttk.Label(df, text="", justify=self.J)
        self.d_info.grid(row=1, column=0, columnspan=3, sticky=self.W, pady=6)
        self.d_orphans = tk.BooleanVar(value=True)
        self.d_dissoc = tk.BooleanVar(value=True)
        ttk.Checkbutton(df, text=_("Also delete its DNs that are not used on any other device"),
                        variable=self.d_orphans).grid(row=2, column=0, columnspan=3, sticky=self.W)
        ttk.Checkbutton(df, text=_("Remove the device from its owner's associated devices"),
                        variable=self.d_dissoc).grid(row=3, column=0, columnspan=3, sticky=self.W)
        ttk.Button(df, text=_("Delete device"), style="Danger.TButton",
                   command=self.delete_device).grid(row=4, column=0, columnspan=3, sticky=self.W, pady=8)

        lf = ttk.LabelFrame(f, text=_("Delete directory number"), padding=10, labelanchor="n" + self.W)
        lf.pack(fill="x", pady=(12, 0))
        ttk.Label(lf, text=_("DN")).grid(row=0, column=self.col(0, 5), sticky=self.W)
        self.dl_dn = ttk.Entry(lf, width=16)
        self.dl_dn.grid(row=0, column=self.col(1, 5), sticky=self.W, padx=6)
        ttk.Label(lf, text=_("Partition")).grid(row=0, column=self.col(2, 5), sticky=self.W)
        self.dl_pt = self.combo(lf, "partitions", width=24)
        self.dl_pt.grid(row=0, column=self.col(3, 5), sticky=self.W, padx=6)
        ttk.Button(lf, text=_("Delete DN"), style="Danger.TButton",
                   command=self.delete_dn).grid(row=0, column=self.col(4, 5), padx=6)
        lf.columnconfigure(self.col(5, 5), weight=1)
        ttk.Label(lf, text=_("Refused if the DN is still on any device."),
                  style="Status.TLabel").grid(row=1, column=0, columnspan=6, sticky=self.W, pady=4)
        ttk.Label(f, text=_("A JSON snapshot of anything deleted is saved in {path}", path=BACKUP_DIR),
                  style="Status.TLabel").pack(anchor=self.W, pady=12)

    def delete_lookup(self):
        name = self.d_name.get().strip()
        if not name or not self.need_conn():
            return

        def done(p):
            lines = ", ".join(f"{dn}/{pt or '<None>'}" for _i, dn, pt, _l in self.macd.phone_lines(p))
            self.d_info.configure(text=_(
                "{name}  -  {product}\nDescription: {desc}\nDevice pool: {dp}   Owner: {owner}\nLines: {lines}",
                name=text_of(p.get("name")), product=text_of(p.get("product")),
                desc=text_of(p.get("description")), dp=text_of(p.get("devicePoolName")),
                owner=text_of(p.get("ownerUserName")) or "-", lines=lines or "-"))
        self.run_bg(lambda: self.macd.get_phone(name), done, "Looking up...")

    def delete_device(self):
        name = self.d_name.get().strip()
        if not name or not self.need_conn():
            return
        if not self._confirm_typed(_("Permanently delete device {name} from CUCM?", name=name), name):
            return
        orph, diss = self.d_orphans.get(), self.d_dissoc.get()

        def done(gone):
            extra = _(" DNs deleted: {dns}", dns=", ".join(gone)) if gone else ""
            self.d_info.configure(text=_("{name} deleted.", name=name) + extra)
            self.info(_("{name} deleted.", name=name))
        self.run_bg(lambda: self.macd.delete_phone(name, orph, diss), done, "Deleting...")

    def delete_dn(self):
        dn, pt = self.dl_dn.get().strip(), self.dl_pt.get().strip()
        if not dn or not self.need_conn():
            return
        if not self._confirm_typed(_("Permanently delete DN {dn} in partition {pt}?",
                                     dn=dn, pt=pt or "<None>"), dn):
            return
        self.run_bg(lambda: self.macd.delete_line(dn, pt),
                    lambda _r: self.info(_("DN {dn} deleted.", dn=dn)), "Deleting DN...")

    def _confirm_typed(self, question, expected):
        dlg = tk.Toplevel(self)
        dlg.title(_("Confirm delete"))
        dlg.transient(self)
        dlg.grab_set()
        ttk.Label(dlg, text=question, padding=10, justify=self.J).pack()
        ttk.Label(dlg, text=_("Type {expected} to confirm:", expected=expected)).pack()
        e = ttk.Entry(dlg, width=30)
        e.pack(pady=6)
        e.focus_set()
        ok = {"v": False}

        def go():
            if e.get().strip().upper() == expected.upper():
                ok["v"] = True
                dlg.destroy()
            else:
                messagebox.showwarning(title(), _("Text does not match."), parent=dlg)
        b = ttk.Frame(dlg, padding=8)
        b.pack()
        ttk.Button(b, text=_("Delete"), style="Danger.TButton", command=go).pack(side=self.S)
        ttk.Button(b, text=_("Cancel"), command=dlg.destroy).pack(side=self.S, padx=6)
        e.bind("<Return>", lambda _e: go())
        self.wait_window(dlg)
        return ok["v"]

    # ------------------------------------------------------------------
    # Bulk tab
    # ------------------------------------------------------------------
    def _build_bulk(self):
        f = self.tab("Bulk (Excel / CSV)")
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Button(top, text=_("Save blank template..."), command=self.save_template).pack(side=self.S)
        ttk.Button(top, text=_("Open sheet..."), command=self.open_sheet).pack(side=self.S, padx=6)
        ttk.Button(top, text=_("Validate (read-only)"), command=lambda: self.bulk_run(False)).pack(side=self.S)
        ttk.Button(top, text=_("Run changes"), command=lambda: self.bulk_run(True)).pack(side=self.S, padx=6)
        ttk.Button(top, text=_("Save results..."), command=self.save_results).pack(side=self.S)
        self.b_stop = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text=_("Stop on first error"), variable=self.b_stop).pack(side=self.S, padx=10)
        self.b_file = ttk.Label(f, text=_("No sheet loaded"), style="Status.TLabel")
        self.b_file.pack(anchor=self.W, pady=6)
        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True)
        cols = (("row", "Row", 50), ("action", "Action", 120), ("device", "Device name", 160),
                ("dn", "DN", 90), ("status", "Status", 80), ("message", "Message", 520))
        self.b_tree = ttk.Treeview(tf, columns=[c for c, *_x in cols], show="headings")
        for c, head, w in cols:
            self.b_tree.heading(c, text=_(head))
            self.b_tree.column(c, width=w, stretch=(c == "message"))
        self.mirror(self.b_tree)
        self.b_tree.tag_configure("ok", background="#e6f4ea")
        self.b_tree.tag_configure("bad", background="#fde7e7")
        ys = ttk.Scrollbar(tf, orient="vertical", command=self.b_tree.yview)
        self.b_tree.configure(yscrollcommand=ys.set)
        ys.pack(side=self.E, fill="y")
        self.b_tree.pack(side=self.S, fill="both", expand=True)
        self.b_rows = []

    def save_template(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                            initialfile="CUCM_MACD_template.xlsx")
        if path:
            bulk.write_template(path, lang=i18n.language())
            self.log(en("Template saved: {path}", path=path))
            os.startfile(path)

    def open_sheet(self):
        path = filedialog.askopenfilename(filetypes=[("Excel / CSV", "*.xlsx *.csv")])
        if not path:
            return
        try:
            self.b_rows = bulk.read_rows(path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(title(), _("Cannot read {path}:\n{err}", path=path, err=e))
            return
        self.b_file.configure(text=_("{path}  -  {n} row(s)", path=path, n=len(self.b_rows)))
        self._bulk_show()

    def _bulk_show(self):
        self.b_tree.delete(*self.b_tree.get_children())
        for r in self.b_rows:
            st = r.get("_status", "")
            tag = "ok" if st in ("OK", "DONE") else ("bad" if st else "")
            self.b_tree.insert("", "end", values=(r["_row"], r["Action"], r.get("DeviceName", ""),
                                                  r.get("DN", ""), st, r.get("_message", "")),
                               tags=(tag,))

    def bulk_run(self, execute):
        if not self.b_rows:
            self.info(_("Open a sheet first."))
            return
        if not self.need_conn():
            return
        if execute:
            counts = {}
            for r in self.b_rows:
                counts[r["Action"]] = counts.get(r["Action"], 0) + 1
            summary = "\n".join(f"  {k}: {v}" for k, v in counts.items())
            if not self.ask(_("Apply {n} change(s) to {host}?\n\n{summary}\n\nRun 'Validate' first if you haven't.",
                              n=len(self.b_rows), host=self.axl.host, summary=summary)):
                return
        stop = self.b_stop.get()

        def work():
            ok = bad = 0
            for r in self.b_rows:
                r.pop("_status", None)
                r.pop("_message", None)
            for r in self.b_rows:
                try:
                    if execute:
                        r["_message"] = bulk.run_row(self.macd, r)
                        r["_status"] = "DONE"
                    else:
                        r["_message"] = bulk.validate_row(self.macd, r)
                        r["_status"] = "OK"
                    ok += 1
                except AXLError as e:
                    r["_status"], r["_message"] = "ERROR", str(e)
                    bad += 1
                    self.log(en("Row {row} {action}: {err}", row=r["_row"], action=r["Action"], err=e))
                    if stop and execute:
                        break
                self.ui_queue.put(("call", self._bulk_show))
            return ok, bad

        def done(res):
            ok, bad = res
            self._bulk_show()
            if execute:
                self.log(en("Bulk run: {ok} applied, {bad} error(s)", ok=ok, bad=bad))
                self.info(_("{ok} row(s) applied, {bad} error(s).", ok=ok, bad=bad))
            else:
                self.log(en("Bulk validation: {ok} valid, {bad} error(s)", ok=ok, bad=bad))
                self.info(_("{ok} row(s) valid, {bad} error(s).", ok=ok, bad=bad))
        self.run_bg(work, done, "Running bulk..." if execute else "Validating...")

    def save_results(self):
        if not self.b_rows:
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                            initialfile="CUCM_MACD_results.xlsx")
        if path:
            bulk.write_results(path, self.b_rows)
            self.log(en("Results saved: {path}", path=path))


if __name__ == "__main__":
    App().mainloop()
