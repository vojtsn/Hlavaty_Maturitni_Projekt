import os
import sys
import requests
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QScrollArea, QFrame, QSplitter, QFileDialog,
    QStatusBar, QSizePolicy, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette

API_BASE = "http://127.0.0.1:5000"


# ─── API helpers ──────────────────────────────────────────────────────────────

def api_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def safe_json(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "error": f"Neplatná odpověď serveru (HTTP {resp.status_code})."}


# ─── Background worker (aby API volání neblokovala UI) ────────────────────────

class ApiWorker(QThread):
    result = pyqtSignal(dict, str)   # (data, tag)

    def __init__(self, fn, tag=""):
        super().__init__()
        self.fn  = fn
        self.tag = tag

    def run(self):
        try:
            data = self.fn()
        except Exception as ex:
            data = {"ok": False, "error": str(ex)}
        self.result.emit(data, self.tag)


# ─── Toast (stavová zpráva dole) ──────────────────────────────────────────────

class ToastLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "background: rgba(20,20,20,220); color: white; "
            "border-radius: 10px; padding: 6px 18px; font-size: 13px;"
        )
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_msg(self, msg: str, ms: int = 2500):
        self.setText(msg)
        self.adjustSize()
        self.show()
        self._timer.start(ms)


# ─── Hlavní okno ──────────────────────────────────────────────────────────────

class EditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("InfoBox – Redaktorský editor")
        self.resize(1280, 860)
        self.setMinimumSize(900, 600)

        # stav
        self.token             = None
        self.my_role           = None
        self.my_username       = None
        self.all_categories    = []
        self.selected_cat_ids  = set()
        self.articles          = []
        self.selected_article_id = None
        self._workers          = []   # udržujeme reference na živé workery

        self._build_ui()
        self._show_login()

    # ──────────────────────────────────────────────────────────────────────────
    # Stavění UI
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # ── Hlavička ──
        self._header = self._make_header()
        self._root_layout.addWidget(self._header)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        self._root_layout.addWidget(sep)

        # ── Stránky (login / editor) ──
        self._login_page  = self._make_login_page()
        self._editor_page = self._make_editor_page()

        self._root_layout.addWidget(self._login_page,  1)
        self._root_layout.addWidget(self._editor_page, 1)

        # ── Toast overlay ──
        self._toast = ToastLabel(central)
        self._toast.raise_()

        # ── Status bar ──
        self.statusBar().hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # přesuň toast do středu dole
        t = self._toast
        t.adjustSize()
        cw = self.centralWidget().width()
        ch = self.centralWidget().height()
        t.move((cw - t.width()) // 2, ch - t.height() - 20)

    # ── Hlavička ──────────────────────────────────────────────────────────────

    def _make_header(self):
        hdr = QWidget()
        hdr.setFixedHeight(52)
        hdr.setStyleSheet("background: white;")
        layout = QHBoxLayout(hdr)
        layout.setContentsMargins(14, 6, 14, 6)

        self._hdr_title = QLabel("InfoBox – Editor")
        self._hdr_title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(self._hdr_title)

        self._hdr_user_label = QLabel("")
        self._hdr_user_label.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(self._hdr_user_label)

        layout.addStretch()

        self._btn_new = QPushButton("Nový článek")
        self._btn_new.setFixedSize(150, 36)
        self._btn_new.setStyleSheet(self._btn_style("#28a045", "#1e7e34"))
        self._btn_new.clicked.connect(self._on_new_article)
        self._btn_new.hide()
        layout.addWidget(self._btn_new)

        self._btn_logout = QPushButton("Odhlásit")
        self._btn_logout.setFixedSize(120, 36)
        self._btn_logout.setStyleSheet(self._btn_style("#5a5a5a", "#404040"))
        self._btn_logout.clicked.connect(self._on_logout)
        self._btn_logout.hide()
        layout.addWidget(self._btn_logout)

        return hdr

    # ── Login stránka ─────────────────────────────────────────────────────────

    def _make_login_page(self):
        page = QWidget()
        page.setStyleSheet("background: #f5f8fc;")
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setFixedWidth(400)
        card.setStyleSheet(
            "QFrame { background: white; border-radius: 14px; "
            "border: 1px solid #ddd; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 24, 30, 30)
        card_layout.setSpacing(12)

        hint = QLabel("Přihlášení (pouze admin / editor)")
        hint.setStyleSheet("color: #888; font-size: 12px; border: none;")
        card_layout.addWidget(hint)

        self._login_user = QLineEdit()
        self._login_user.setPlaceholderText("Uživatelské jméno")
        self._login_user.setFixedHeight(44)
        self._login_user.setStyleSheet(self._input_style())
        self._login_user.returnPressed.connect(self._on_login)
        card_layout.addWidget(self._login_user)

        self._login_pass = QLineEdit()
        self._login_pass.setPlaceholderText("Heslo")
        self._login_pass.setEchoMode(QLineEdit.Password)
        self._login_pass.setFixedHeight(44)
        self._login_pass.setStyleSheet(self._input_style())
        self._login_pass.returnPressed.connect(self._on_login)
        card_layout.addWidget(self._login_pass)

        btn_row = QHBoxLayout()
        btn_login = QPushButton("Přihlásit")
        btn_login.setFixedHeight(42)
        btn_login.setStyleSheet(self._btn_style("#0077cc", "#005fa3"))
        btn_login.clicked.connect(self._on_login)

        btn_quit = QPushButton("Konec")
        btn_quit.setFixedHeight(42)
        btn_quit.setStyleSheet(self._btn_style("#5a5a5a", "#404040"))
        btn_quit.clicked.connect(QApplication.quit)

        btn_row.addWidget(btn_login)
        btn_row.addWidget(btn_quit)
        card_layout.addLayout(btn_row)

        outer.addWidget(card)
        return page

    # ── Editor stránka ────────────────────────────────────────────────────────

    def _make_editor_page(self):
        page = QWidget()
        page.setStyleSheet("background: #f5f8fc;")
        main_layout = QHBoxLayout(page)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ── Levý panel: seznam článků ──
        self._article_list = QListWidget()
        self._article_list.setFixedWidth(260)
        self._article_list.setStyleSheet("""
            QListWidget {
                background: white; border-radius: 10px;
                border: 1px solid #ccc;
            }
            QListWidget::item {
                padding: 8px 10px; border-radius: 6px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background: #dceeff; color: #111;
                border: 1px solid #0077cc;
            }
        """)
        self._article_list.currentRowChanged.connect(self._on_article_selected)
        self._article_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left_frame = QVBoxLayout()
        lbl_articles = QLabel("Články")
        lbl_articles.setStyleSheet("color: #555; font-size: 12px; font-weight: bold;")
        left_frame.addWidget(lbl_articles)
        left_frame.addWidget(self._article_list)
        left_widget = QWidget()
        left_widget.setLayout(left_frame)
        main_layout.addWidget(left_widget)

        # ── Střed: formulář ──
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        # Titulek
        form_layout.addWidget(self._lbl("Titulek"))
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("Titulek (povinné)")
        self._title_input.setFixedHeight(44)
        self._title_input.setStyleSheet(self._input_style())
        form_layout.addWidget(self._title_input)

        # Shrnutí
        form_layout.addWidget(self._lbl("Shrnutí"))
        self._perex_input = QTextEdit()
        self._perex_input.setPlaceholderText("Shrnutí obsahu")
        self._perex_input.setFixedHeight(90)
        self._perex_input.setStyleSheet(self._textarea_style())
        form_layout.addWidget(self._perex_input)

        # Markdown toolbar
        md_row = QHBoxLayout()
        md_row.setSpacing(5)
        md_row.addWidget(QLabel("Markdown:"))
        self._md_btns = []
        md_labels   = ["H1","H2","B","I","Seznam","Odkaz","Citace","---"]
        md_snippets = ["# ","## ","**text**","*text*","- ","[text](url)","> ","\n---\n"]
        for label, snippet in zip(md_labels, md_snippets):
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._btn_style("#505050", "#333"))
            btn.clicked.connect(lambda _, s=snippet: self._insert_md(s))
            md_row.addWidget(btn)
            self._md_btns.append(btn)
        md_row.addStretch()
        form_layout.addLayout(md_row)

        # Obsah
        form_layout.addWidget(self._lbl("Obsah"))
        self._content_input = QTextEdit()
        self._content_input.setPlaceholderText("Obsah článku (povinné)")
        self._content_input.setStyleSheet(self._textarea_style())
        form_layout.addWidget(self._content_input, 1)

        # Tlačítka dole
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton("Uložit")
        self._btn_save.setFixedHeight(42)
        self._btn_save.setStyleSheet(self._btn_style("#0077cc", "#005fa3"))
        self._btn_save.clicked.connect(self._on_save)

        self._btn_delete = QPushButton("Smazat")
        self._btn_delete.setFixedHeight(42)
        self._btn_delete.setStyleSheet(self._btn_style("#c83c3c", "#a02020"))
        self._btn_delete.clicked.connect(self._on_delete)

        self._btn_upload = QPushButton("Nahrát obrázek")
        self._btn_upload.setFixedHeight(42)
        self._btn_upload.setStyleSheet(self._btn_style("#785ac8", "#5a40a0"))
        self._btn_upload.clicked.connect(self._on_upload_image)

        self._btn_import_txt = QPushButton("Importovat .txt")
        self._btn_import_txt.setFixedHeight(42)
        self._btn_import_txt.setStyleSheet(self._btn_style("#3a8a6e", "#2a6a52"))
        self._btn_import_txt.clicked.connect(self._on_import_txt)

        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_delete)
        btn_row.addWidget(self._btn_upload)
        btn_row.addWidget(self._btn_import_txt)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        # Statistiky
        self._stats_label = QLabel("Vyber článek pro zobrazení statistik")
        self._stats_label.setStyleSheet("color: #aaa; font-size: 12px;")
        form_layout.addWidget(self._stats_label)

        main_layout.addWidget(form_widget, 1)

        # ── Pravý panel: kategorie ──
        right_frame = QVBoxLayout()
        lbl_cat = QLabel("Kategorie")
        lbl_cat.setStyleSheet("color: #555; font-size: 12px; font-weight: bold;")
        right_frame.addWidget(lbl_cat)

        self._cat_scroll = QScrollArea()
        self._cat_scroll.setWidgetResizable(True)
        self._cat_scroll.setFixedWidth(190)
        self._cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cat_scroll.setStyleSheet("""
            QScrollArea { background: white; border-radius: 10px; border: 1px solid #ccc; }
        """)
        self._cat_container = QWidget()
        self._cat_layout = QVBoxLayout(self._cat_container)
        self._cat_layout.setContentsMargins(8, 8, 8, 8)
        self._cat_layout.setSpacing(4)
        self._cat_layout.addStretch()
        self._cat_scroll.setWidget(self._cat_container)
        right_frame.addWidget(self._cat_scroll, 1)

        right_widget = QWidget()
        right_widget.setLayout(right_frame)
        main_layout.addWidget(right_widget)

        return page

    # ──────────────────────────────────────────────────────────────────────────
    # Přepínání stránek
    # ──────────────────────────────────────────────────────────────────────────

    def _show_login(self):
        self._hdr_title.setText("InfoBox – Editor")
        self._hdr_user_label.setText("")
        self._btn_new.hide()
        self._btn_logout.hide()
        self._login_page.show()
        self._editor_page.hide()
        self._login_user.setFocus()

    def _show_editor(self):
        self._hdr_title.setText("InfoBox – Editor článků")
        self._hdr_user_label.setText(f"{self.my_username}  •  {self.my_role}")
        self._btn_new.show()
        self._btn_logout.show()
        self._login_page.hide()
        self._editor_page.show()

    # ──────────────────────────────────────────────────────────────────────────
    # Login / logout
    # ──────────────────────────────────────────────────────────────────────────

    def _on_login(self):
        u = self._login_user.text().strip()
        p = self._login_pass.text()
        if not u or not p:
            self._toast.show_msg("Vyplň přihlašovací údaje.")
            return

        self._run_worker(
            lambda: self._api_login(u, p),
            tag="login"
        )

    def _on_logout(self):
        self.token = None
        self.my_role = None
        self.my_username = None
        self.articles = []
        self.selected_article_id = None
        self._clear_form()
        self._show_login()
        self._toast.show_msg("Odhlášeno.")

    # ──────────────────────────────────────────────────────────────────────────
    # Články
    # ──────────────────────────────────────────────────────────────────────────

    def _on_new_article(self):
        self._clear_form()
        self._set_form_editable(True)
        self._article_list.clearSelection()
        self._toast.show_msg("Nový článek – vyplň a dej Uložit.")
        self._title_input.setFocus()

    def _on_article_selected(self, row):
        if row < 0 or row >= len(self.articles):
            return
        a = self.articles[row]
        self.selected_article_id = int(a["id"])
        aid = self.selected_article_id
        self._run_worker(
            lambda _aid=aid: self._api_get_article(_aid),
            tag="load_article"
        )

    def _on_save(self):
        title   = self._title_input.text().strip()
        perex   = self._perex_input.toPlainText().strip()
        content = self._content_input.toPlainText().strip()
        if not title or not content:
            self._toast.show_msg("Titulek a obsah jsou povinné.")
            return
        cat_ids = list(self.selected_cat_ids)
        if self.selected_article_id is None:
            self._run_worker(
                lambda: self._api_create_article(title, perex, content, cat_ids),
                tag="create"
            )
        else:
            aid = self.selected_article_id
            self._run_worker(
                lambda _aid=aid, _t=title, _p=perex, _c=content, _cats=cat_ids:
                    self._api_update_article(_aid, _t, _p, _c, _cats),
                tag="update"
            )

    def _on_delete(self):
        if self.selected_article_id is None:
            self._toast.show_msg("Nejdřív vyber článek.")
            return
        reply = QMessageBox.question(
            self, "Smazat článek",
            "Opravdu chceš smazat tento článek?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        aid = self.selected_article_id
        self._run_worker(
            lambda _aid=aid: self._api_delete_article(_aid),
            tag="delete"
        )

    def _on_import_txt(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Importovat textový soubor", "",
            "Textové soubory (*.txt);;Všechny soubory (*.*)"
        )
        if not fp:
            return
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            # zkus latin-2 jako fallback pro starší české soubory
            try:
                with open(fp, 'r', encoding='cp1250') as f:
                    text = f.read()
            except Exception as ex:
                self._toast.show_msg(f"Chyba čtení souboru: {ex}")
                return
        except Exception as ex:
            self._toast.show_msg(f"Chyba čtení souboru: {ex}")
            return

        self._content_input.setPlainText(text)
        self._toast.show_msg(f"Importováno z: {os.path.basename(fp)}")

    def _on_upload_image(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Vyber obrázek", "",
            "Images (*.png *.jpg *.jpeg *.webp *.gif);;All files (*.*)"
        )
        if not fp:
            return
        self._run_worker(
            lambda: self._api_upload_image(fp),
            tag="upload"
        )

    def _insert_md(self, snippet: str):
        cursor = self._content_input.textCursor()
        cursor.insertText(snippet)
        self._content_input.setFocus()

    # ──────────────────────────────────────────────────────────────────────────
    # Worker výsledky
    # ──────────────────────────────────────────────────────────────────────────

    def _on_worker_result(self, data: dict, tag: str):
        if tag == "login":
            if not data.get("ok"):
                self._toast.show_msg(data.get("error", "Přihlášení selhalo."))
            elif data.get("role") not in ("admin", "editor"):
                self._toast.show_msg(f"Role '{data.get('role')}' nemá přístup.")
            else:
                self.token       = data["token"]
                self.my_role     = data["role"]
                self.my_username = data["username"]
                self._my_user_id = data.get("user_id")  # cachujeme pro porovnání autora
                self._show_editor()
                self._toast.show_msg(f"Přihlášen: {self.my_username} ({self.my_role})")
                self._run_worker(self._api_list_articles, tag="list_articles")
                self._run_worker(self._api_fetch_categories, tag="categories")

        elif tag == "list_articles":
            if not data.get("ok"):
                self._toast.show_msg(data.get("error", "Chyba načítání."))
                return
            self.articles = data.get("articles", [])
            self._article_list.blockSignals(True)
            self._article_list.clear()
            for a in self.articles:
                item = QListWidgetItem()
                title  = (a.get("title") or "")[:40]
                date   = (a.get("created_at") or "")[:19]
                author = a.get("author") or a.get("username") or "neznámý"
                item.setText(f"{title}\n{date}\n✍ {author}")
                self._article_list.addItem(item)
            self._article_list.blockSignals(False)
            self._toast.show_msg(f"Načteno: {len(self.articles)} článků")

        elif tag == "categories":
            if not data.get("ok"):
                return
            self.all_categories = data.get("categories", [])
            self._rebuild_categories()

        elif tag == "load_article":
            if not data.get("ok"):
                self._toast.show_msg(data.get("error", "Chyba načítání."))
                return
            a = data.get("article", {})
            self._title_input.setText(a.get("title", "") or "")
            self._perex_input.setPlainText(a.get("perex", "") or "")
            self._content_input.setPlainText(a.get("content", "") or "")
            self.selected_cat_ids = set(a.get("category_ids", []))
            self._update_category_checkboxes()

            # editor může editovat jen svoje články, admin všechny
            is_own = (a.get("author_id") == self._get_my_user_id())
            can_edit = (self.my_role == "admin") or is_own
            self._set_form_editable(can_edit)
            if not can_edit:
                self._toast.show_msg("Tento článek patří jinému autorovi — pouze pro čtení.")
            # načti statistiky — zachyť aid hodnotou hned teď (ne referencí)
            aid = self.selected_article_id
            token = self.token
            if aid is not None:
                self._run_worker(
                    lambda _aid=aid, _tok=token: self._api_get_stats(_aid, _tok),
                    tag="stats"
                )

        elif tag == "stats":
            if data.get("ok"):
                s = data.get("stats", {})
                self._stats_label.setStyleSheet("color: #444; font-size: 12px;")
                self._stats_label.setText(
                    f"Zobrazení: {s.get('views', 0)}    "
                    f"Unikátní: {s.get('unique_views', 0)}    "
                    f"Lajků: {s.get('likes', 0)}    "
                    f"Komentářů: {s.get('comments', 0)}"
                )

        elif tag == "create":
            if data.get("ok"):
                self._toast.show_msg(f"Vytvořeno (id {data.get('id')}).")
                self._run_worker(self._api_list_articles, tag="list_articles")
            else:
                self._toast.show_msg(data.get("error", "Chyba vytvoření."))

        elif tag == "update":
            if data.get("ok"):
                self._toast.show_msg("Uloženo.")
                self._run_worker(self._api_list_articles, tag="list_articles")
            else:
                self._toast.show_msg(data.get("error", "Chyba uložení."))

        elif tag == "delete":
            if data.get("ok"):
                self._toast.show_msg("Smazáno.")
                self._clear_form()
                self._run_worker(self._api_list_articles, tag="list_articles")
            else:
                self._toast.show_msg(data.get("error", "Chyba mazání."))

        elif tag == "upload":
            if data.get("ok"):
                url = data.get("url", "")
                self._insert_md(f'<p><img src="{url}" alt=""></p>\n')
                self._toast.show_msg("Obrázek nahrán.")
            else:
                self._toast.show_msg(data.get("error", "Upload selhal."))

    # ──────────────────────────────────────────────────────────────────────────
    # Kategorie
    # ──────────────────────────────────────────────────────────────────────────

    def _rebuild_categories(self):
        # smaž staré checkboxy
        while self._cat_layout.count() > 1:
            item = self._cat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._cat_checkboxes = {}
        for cat in self.all_categories:
            cb = QCheckBox(cat["name"])
            cb.setStyleSheet("padding: 4px 2px;")
            checked = cat["id"] in self.selected_cat_ids
            cb.setChecked(checked)
            cid = cat["id"]
            cb.stateChanged.connect(lambda state, c=cid: self._on_cat_toggled(c, state))
            self._cat_layout.insertWidget(self._cat_layout.count() - 1, cb)
            self._cat_checkboxes[cid] = cb

    def _update_category_checkboxes(self):
        for cid, cb in getattr(self, "_cat_checkboxes", {}).items():
            cb.blockSignals(True)
            cb.setChecked(cid in self.selected_cat_ids)
            cb.blockSignals(False)

    def _on_cat_toggled(self, cat_id, state):
        if state == Qt.Checked:
            self.selected_cat_ids.add(cat_id)
        else:
            self.selected_cat_ids.discard(cat_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Pomocné
    # ──────────────────────────────────────────────────────────────────────────

    def _set_form_editable(self, editable: bool):
        """Povolí nebo zakáže editaci formuláře."""
        self._title_input.setReadOnly(not editable)
        self._perex_input.setReadOnly(not editable)
        self._content_input.setReadOnly(not editable)
        self._btn_save.setEnabled(editable)
        self._btn_delete.setEnabled(editable)
        self._btn_upload.setEnabled(editable)
        self._btn_import_txt.setEnabled(editable)
        for cb in getattr(self, "_cat_checkboxes", {}).values():
            cb.setEnabled(editable)
        for mb in self._md_btns:
            mb.setEnabled(editable)
        # vizuální signál — šedé pozadí pro read-only
        bg = "#f0f0f0" if not editable else "white"
        for w in [self._title_input, self._perex_input, self._content_input]:
            w.setStyleSheet(w.styleSheet().split("background:")[0] +
                            f"background: {bg};" if "background:" in w.styleSheet()
                            else w.styleSheet() + f" background: {bg};")

    def _get_my_user_id(self) -> int | None:
        """Vrátí user_id přihlášeného uživatele z tokenu (cachováno)."""
        return getattr(self, "_my_user_id", None)

    def _clear_form(self):
        self.selected_article_id = None
        self.selected_cat_ids = set()
        self._title_input.clear()
        self._perex_input.clear()
        self._content_input.clear()
        self._stats_label.setStyleSheet("color: #aaa; font-size: 12px;")
        self._stats_label.setText("Vyber článek pro zobrazení statistik")
        self._update_category_checkboxes()

    def _run_worker(self, fn, tag=""):
        w = ApiWorker(fn, tag)
        w.result.connect(self._on_worker_result)
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)
        w.start()

    # ──────────────────────────────────────────────────────────────────────────
    # API volání
    # ──────────────────────────────────────────────────────────────────────────

    def _api_login(self, username, password):
        r = requests.post(
            f"{API_BASE}/api/login",
            json={"username": username, "password": password},
            timeout=8
        )
        return safe_json(r)

    def _api_list_articles(self):
        r = requests.get(
            f"{API_BASE}/api/articles",
            headers=api_headers(self.token),
            timeout=10
        )
        return safe_json(r)

    def _api_get_article(self, aid):
        r = requests.get(
            f"{API_BASE}/api/articles/{aid}",
            headers=api_headers(self.token),
            timeout=10
        )
        return safe_json(r)

    def _api_create_article(self, title, perex, content, cat_ids):
        r = requests.post(
            f"{API_BASE}/api/articles",
            headers=api_headers(self.token),
            json={"title": title, "perex": perex, "content": content, "category_ids": cat_ids},
            timeout=12
        )
        return safe_json(r)

    def _api_update_article(self, aid, title, perex, content, cat_ids):
        r = requests.put(
            f"{API_BASE}/api/articles/{aid}",
            headers=api_headers(self.token),
            json={"title": title, "perex": perex, "content": content, "category_ids": cat_ids},
            timeout=12
        )
        return safe_json(r)

    def _api_delete_article(self, aid):
        r = requests.delete(
            f"{API_BASE}/api/articles/{aid}",
            headers=api_headers(self.token),
            timeout=12
        )
        return safe_json(r)

    def _api_upload_image(self, filepath):
        with open(filepath, "rb") as f:
            r = requests.post(
                f"{API_BASE}/api/upload",
                headers=api_headers(self.token),
                files={"file": (os.path.basename(filepath), f)},
                timeout=20
            )
        return safe_json(r)

    def _api_fetch_categories(self):
        r = requests.get(f"{API_BASE}/api/categories", timeout=6)
        return safe_json(r)

    def _api_get_stats(self, aid, token=None):
        tok = token or self.token
        r = requests.get(
            f"{API_BASE}/api/articles/{aid}/stats",
            headers=api_headers(tok),
            timeout=8
        )
        result = safe_json(r)
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Style helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _btn_style(bg, hover):
        return f"""
            QPushButton {{
                background: {bg}; color: white;
                border-radius: 8px; font-size: 13px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:disabled {{ background: #aaa; }}
        """

    @staticmethod
    def _input_style():
        return """
            QLineEdit {
                border: 1.5px solid #aaa; border-radius: 8px;
                padding: 0 10px; font-size: 14px; background: white;
            }
            QLineEdit:focus { border-color: #0077cc; }
        """

    @staticmethod
    def _textarea_style():
        return """
            QTextEdit {
                border: 1.5px solid #aaa; border-radius: 8px;
                padding: 6px 10px; font-size: 14px; background: white;
            }
            QTextEdit:focus { border-color: #0077cc; }
        """

    @staticmethod
    def _lbl(text):
        l = QLabel(text)
        l.setStyleSheet("color: #555; font-size: 12px;")
        return l


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Arial", 11))
    win = EditorWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()