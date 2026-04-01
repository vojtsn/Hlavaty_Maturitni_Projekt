import os       # práce se soubory a cestami (např. zjistit název souboru bez složky)
import sys      # potřeba pro spuštění Qt aplikace a ukončení programu
import requests # knihovna pro posílání HTTP requestů na server (jako prohlížeč, jen z kódu)

# PyQt5 je knihovna pro kreslení grafického okna s tlačítky, poli atd.
# importujeme jen to co opravdu používáme, ne celou knihovnu najednou
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QScrollArea, QFrame, QSplitter, QFileDialog,
    QStatusBar, QSizePolicy, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette

# adresa Flask serveru — editor sem posílá všechny requesty
# pokud editor běží na jiném počítači než server, změň 127.0.0.1 na IP adresu serveru
API_BASE = "http://127.0.0.1:5000"


# --- pomocné funkce pro API ---

def api_headers(token: str) -> dict:
    # sestaví hlavičku s přihlašovacím tokenem
    # token dostaneme po úspěšném přihlášení a pak ho přikládáme ke každému requestu
    # server podle něj pozná kdo volá a jestli má oprávnění
    return {"Authorization": f"Bearer {token}"}

def safe_json(resp: requests.Response):
    # zkusí z odpovědi serveru vytáhnout JSON data
    # pokud server vrátí místo JSONu třeba chybovou HTML stránku, funkce nespadne
    # místo pádu vrátí slovník s ok=False a popisem chyby
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "error": f"Neplatná odpověď serveru (HTTP {resp.status_code})."}


# --- vlákno pro komunikaci se serverem na pozadí ---

class ApiWorker(QThread):
    # problém: kdybychom posílali request na server přímo v hlavním vlákně,
    # okno by zamrzlo a nereagovala by žádná tlačítka, dokud server neodpoví
    # řešení: ApiWorker spustí request v samostatném vlákně vedle,
    # okno mezitím normálně funguje a výsledek přijde přes signál

    result = pyqtSignal(dict, str)
    # signál který worker vyšle po dokončení — přenese data ze serveru a tag
    # tag je řetězec jako "login" nebo "create" aby hlavní okno vědělo co se vrátilo

    def __init__(self, fn, tag=""):
        super().__init__()
        self.fn  = fn    # funkce kterou má vlákno zavolat (samotné API volání)
        self.tag = tag   # štítek pro identifikaci výsledku v _on_worker_result()

    def run(self):
        # tato metoda běží v samostatném vlákně — Qt ji spustí automaticky přes w.start()
        try:
            data = self.fn()   # zavolá předanou API funkci a počká na odpověď serveru
        except Exception as ex:
            # pokud request úplně selže (server neběží, timeout...), vrátíme chybu
            data = {"ok": False, "error": str(ex)}
        # výsledek pošleme do hlavního vlákna přes signál — přímé volání metod z jiného vlákna není bezpečné
        self.result.emit(data, self.tag)


# --- dočasná zpráva (toast) dole uprostřed okna ---

class ToastLabel(QLabel):
    # funguje jako notifikační bublina na mobilu — ukáže se, chvíli je vidět, pak zmizí
    # používáme ji místo vyskakovacích dialogů, které by uživatele otravovaly klikáním

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        # tmavé poloprůhledné pozadí s bílým textem a zakulacenými rohy
        self.setStyleSheet(
            "background: rgba(20,20,20,220); color: white; "
            "border-radius: 10px; padding: 6px 18px; font-size: 13px;"
        )
        self.hide()  # zpočátku skrytá, ukáže se až zavoláme show_msg()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)   # časovač se spustí jednou a zastaví, neopakuje se
        self._timer.timeout.connect(self.hide)  # po vypršení časovače bublinu schováme

    def show_msg(self, msg: str, ms: int = 2500):
        # zobrazí zprávu a po zadaném počtu milisekund ji schová (výchozí 2,5 sekundy)
        self.setText(msg)
        self.adjustSize()  # přizpůsobí velikost textu
        self.show()
        self._timer.start(ms)  # spustí odpočet


# --- hlavní okno aplikace ---

class EditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("InfoBox – Redaktorský editor")
        self.resize(1280, 860)       # výchozí velikost okna při spuštění
        self.setMinimumSize(900, 600)  # nejmenší povolená velikost, menší nejde udělat

        # --- proměnné pro stav aplikace ---
        self.token             = None   # přihlašovací token, přikládá se ke každému API requestu
        self.my_role           = None   # role přihlášeného uživatele: "admin" nebo "editor"
        self.my_username       = None   # uživatelské jméno přihlášeného uživatele
        self.all_categories    = []     # seznam všech kategorií načtených ze serveru
        self.selected_cat_ids  = set()  # ID kategorií zaškrtnutých pro právě editovaný článek
        self.articles          = []     # seznam článků zobrazených v levém panelu
        self.selected_article_id = None # ID článku vybraného v seznamu (None = píšeme nový)
        self._workers          = []     # seznam aktivních vláken — uchováváme je aby je Python nesmazal za běhu

        self._build_ui()    # sestaví celé grafické rozhraní
        self._show_login()  # na startu zobrazí přihlašovací stránku (ne editor)

    # --- sestavení grafického rozhraní ---

    def _build_ui(self):
        # vytvoří základní kostru okna: hlavička nahoře, pak obsah
        central = QWidget()
        self.setCentralWidget(central)
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)  # žádné okraje kolem
        self._root_layout.setSpacing(0)                    # žádné mezery mezi widgety

        # přidáme hlavičku (lištu nahoře s tlačítky)
        self._header = self._make_header()
        self._root_layout.addWidget(self._header)

        # tenká vodorovná čára jako vizuální oddělovač pod hlavičkou
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        self._root_layout.addWidget(sep)

        # dvě stránky — vždy viditelná jen jedna
        self._login_page  = self._make_login_page()   # přihlašovací formulář
        self._editor_page = self._make_editor_page()  # pracovní plocha editoru

        self._root_layout.addWidget(self._login_page,  1)  # číslo 1 = roztáhne se na zbývající místo
        self._root_layout.addWidget(self._editor_page, 1)

        # toast se vykresluje přes celý obsah okna jako průhledná vrstva nahoře
        self._toast = ToastLabel(central)
        self._toast.raise_()  # zajistí že toast je vždy nakreslený nad vším ostatním

        self.statusBar().hide()  # spodní stavový řádek nepotřebujeme, schováme ho

    def resizeEvent(self, event):
        # Qt tuto metodu zavolá automaticky pokaždé když uživatel změní velikost okna
        super().resizeEvent(event)
        # přepočítáme pozici toastu aby seděl dole uprostřed i po změně velikosti
        t = self._toast
        t.adjustSize()
        cw = self.centralWidget().width()
        ch = self.centralWidget().height()
        t.move((cw - t.width()) // 2, ch - t.height() - 20)  # vycentrovat vodorovně, 20px od spodního okraje

    # --- hlavička (lišta nahoře) ---

    def _make_header(self):
        hdr = QWidget()
        hdr.setFixedHeight(52)       # pevná výška hlavičky
        hdr.setStyleSheet("background: white;")
        layout = QHBoxLayout(hdr)
        layout.setContentsMargins(14, 6, 14, 6)

        # název aplikace vlevo
        self._hdr_title = QLabel("InfoBox – Editor")
        self._hdr_title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(self._hdr_title)

        # jméno a role přihlášeného uživatele (prázdné dokud nikdo není přihlášen)
        self._hdr_user_label = QLabel("")
        self._hdr_user_label.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(self._hdr_user_label)

        layout.addStretch()  # prázdné místo které tlačítka odstrčí doprava

        # tlačítko pro vytvoření nového článku — schované do přihlášení
        self._btn_new = QPushButton("Nový článek")
        self._btn_new.setFixedSize(150, 36)
        self._btn_new.setStyleSheet(self._btn_style("#28a045", "#1e7e34"))
        self._btn_new.clicked.connect(self._on_new_article)
        self._btn_new.hide()
        layout.addWidget(self._btn_new)

        # tlačítko pro odhlášení — taky schované do přihlášení
        self._btn_logout = QPushButton("Odhlásit")
        self._btn_logout.setFixedSize(120, 36)
        self._btn_logout.setStyleSheet(self._btn_style("#5a5a5a", "#404040"))
        self._btn_logout.clicked.connect(self._on_logout)
        self._btn_logout.hide()
        layout.addWidget(self._btn_logout)

        return hdr

    # --- přihlašovací stránka ---

    def _make_login_page(self):
        # bílá kartička vycentrovaná na modrošedém pozadí
        page = QWidget()
        page.setStyleSheet("background: #f5f8fc;")
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignCenter)  # kartička bude uprostřed stránky

        card = QFrame()
        card.setFixedWidth(400)
        card.setStyleSheet(
            "QFrame { background: white; border-radius: 14px; "
            "border: 1px solid #ddd; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 24, 30, 30)
        card_layout.setSpacing(12)

        # informační popisek nad formulářem
        hint = QLabel("Přihlášení (pouze admin / editor)")
        hint.setStyleSheet("color: #888; font-size: 12px; border: none;")
        card_layout.addWidget(hint)

        # pole pro uživatelské jméno
        self._login_user = QLineEdit()
        self._login_user.setPlaceholderText("Uživatelské jméno")
        self._login_user.setFixedHeight(44)
        self._login_user.setStyleSheet(self._input_style())
        # Enter v poli jména spustí přihlášení — uživatel nemusí klikat na tlačítko
        self._login_user.returnPressed.connect(self._on_login)
        card_layout.addWidget(self._login_user)

        # pole pro heslo — znaky se zobrazují jako hvězdičky
        self._login_pass = QLineEdit()
        self._login_pass.setPlaceholderText("Heslo")
        self._login_pass.setEchoMode(QLineEdit.Password)  # maskuje zadávané znaky
        self._login_pass.setFixedHeight(44)
        self._login_pass.setStyleSheet(self._input_style())
        self._login_pass.returnPressed.connect(self._on_login)  # Enter taky přihlásí
        card_layout.addWidget(self._login_pass)

        # řada s tlačítky Přihlásit a Konec vedle sebe
        btn_row = QHBoxLayout()
        btn_login = QPushButton("Přihlásit")
        btn_login.setFixedHeight(42)
        btn_login.setStyleSheet(self._btn_style("#0077cc", "#005fa3"))
        btn_login.clicked.connect(self._on_login)

        btn_quit = QPushButton("Konec")
        btn_quit.setFixedHeight(42)
        btn_quit.setStyleSheet(self._btn_style("#5a5a5a", "#404040"))
        btn_quit.clicked.connect(QApplication.quit)  # ukončí celý program

        btn_row.addWidget(btn_login)
        btn_row.addWidget(btn_quit)
        card_layout.addLayout(btn_row)

        outer.addWidget(card)
        return page

    # --- hlavní pracovní plocha editoru ---

    def _make_editor_page(self):
        # tři sloupce vedle sebe: seznam článků | formulář | kategorie
        page = QWidget()
        page.setStyleSheet("background: #f5f8fc;")
        main_layout = QHBoxLayout(page)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # === LEVÝ SLOUPEC: seznam článků ===
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
        # kliknutí na položku v seznamu spustí _on_article_selected()
        self._article_list.currentRowChanged.connect(self._on_article_selected)
        self._article_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # bez vodorovného scrollbaru

        left_frame = QVBoxLayout()
        lbl_articles = QLabel("Články")
        lbl_articles.setStyleSheet("color: #555; font-size: 12px; font-weight: bold;")
        left_frame.addWidget(lbl_articles)
        left_frame.addWidget(self._article_list)
        left_widget = QWidget()
        left_widget.setLayout(left_frame)
        main_layout.addWidget(left_widget)

        # === STŘEDNÍ SLOUPEC: formulář pro editaci článku ===
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        # pole pro titulek článku
        form_layout.addWidget(self._lbl("Titulek"))
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("Titulek (povinné)")
        self._title_input.setFixedHeight(44)
        self._title_input.setStyleSheet(self._input_style())
        form_layout.addWidget(self._title_input)

        # pole pro krátké shrnutí (perex)
        form_layout.addWidget(self._lbl("Shrnutí"))
        self._perex_input = QTextEdit()
        self._perex_input.setPlaceholderText("Shrnutí obsahu")
        self._perex_input.setFixedHeight(90)
        self._perex_input.setStyleSheet(self._textarea_style())
        form_layout.addWidget(self._perex_input)

        # --- Markdown nástrojová lišta ---
        # tlačítka vkládají formátovací zkratky přímo do pole obsahu
        md_row = QHBoxLayout()
        md_row.setSpacing(5)
        md_row.addWidget(QLabel("Markdown:"))
        self._md_btns = []

        # dvojice: co se zobrazí na tlačítku  →  co se vloží do textu
        md_labels   = ["H1","H2","B","I","Seznam","Odkaz","Citace","---"]
        md_snippets = ["# ","## ","**text**","*text*","- ","[text](url)","> ","\n---\n"]

        for label, snippet in zip(md_labels, md_snippets):
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._btn_style("#505050", "#333"))
            # DŮLEŽITÉ: s=snippet zachytí hodnotu proměnné hned při vytváření tlačítka
            # bez toho by všechna tlačítka vkládala stejný poslední snippet ze smyčky
            btn.clicked.connect(lambda _, s=snippet: self._insert_md(s))
            md_row.addWidget(btn)
            self._md_btns.append(btn)
        md_row.addStretch()
        form_layout.addLayout(md_row)

        # hlavní textové pole pro obsah článku — roztáhne se na veškeré zbývající místo
        form_layout.addWidget(self._lbl("Obsah"))
        self._content_input = QTextEdit()
        self._content_input.setPlaceholderText("Obsah článku (povinné)")
        self._content_input.setStyleSheet(self._textarea_style())
        form_layout.addWidget(self._content_input, 1)  # číslo 1 = zabere zbývající výšku

        # --- řada akčních tlačítek pod polem obsahu ---
        btn_row = QHBoxLayout()

        self._btn_save = QPushButton("Uložit")
        self._btn_save.setFixedHeight(42)
        self._btn_save.setStyleSheet(self._btn_style("#0077cc", "#005fa3"))
        self._btn_save.clicked.connect(self._on_save)  # uloží nebo vytvoří článek

        self._btn_delete = QPushButton("Smazat")
        self._btn_delete.setFixedHeight(42)
        self._btn_delete.setStyleSheet(self._btn_style("#c83c3c", "#a02020"))
        self._btn_delete.clicked.connect(self._on_delete)  # smaže vybraný článek

        self._btn_upload = QPushButton("Nahrát obrázek")
        self._btn_upload.setFixedHeight(42)
        self._btn_upload.setStyleSheet(self._btn_style("#785ac8", "#5a40a0"))
        self._btn_upload.clicked.connect(self._on_upload_image)  # nahraje obrázek na server

        self._btn_import_txt = QPushButton("Importovat .txt")
        self._btn_import_txt.setFixedHeight(42)
        self._btn_import_txt.setStyleSheet(self._btn_style("#3a8a6e", "#2a6a52"))
        self._btn_import_txt.clicked.connect(self._on_import_txt)  # načte obsah z .txt souboru

        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_delete)
        btn_row.addWidget(self._btn_upload)
        btn_row.addWidget(self._btn_import_txt)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        # řádek se statistikami článku (zobrazení, lajky, komentáře)
        self._stats_label = QLabel("Vyber článek pro zobrazení statistik")
        self._stats_label.setStyleSheet("color: #aaa; font-size: 12px;")
        form_layout.addWidget(self._stats_label)

        main_layout.addWidget(form_widget, 1)  # střední sloupec zabere zbytek šířky

        # === PRAVÝ SLOUPEC: checkboxy kategorií ===
        right_frame = QVBoxLayout()
        lbl_cat = QLabel("Kategorie")
        lbl_cat.setStyleSheet("color: #555; font-size: 12px; font-weight: bold;")
        right_frame.addWidget(lbl_cat)

        # scrollovatelná oblast pro checkboxy — pokud je kategorií hodně, dají se scrollovat
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
        self._cat_layout.addStretch()  # prázdné místo na konci drží checkboxy u horního okraje
        self._cat_scroll.setWidget(self._cat_container)
        right_frame.addWidget(self._cat_scroll, 1)

        right_widget = QWidget()
        right_widget.setLayout(right_frame)
        main_layout.addWidget(right_widget)

        return page

    # --- přepínání mezi přihlašovací a editorskou stránkou ---

    def _show_login(self):
        # schová editor a ukáže přihlašovací formulář
        self._hdr_title.setText("InfoBox – Editor")
        self._hdr_user_label.setText("")  # vyprázdní jméno uživatele v hlavičce
        self._btn_new.hide()
        self._btn_logout.hide()
        self._login_page.show()
        self._editor_page.hide()
        self._login_user.setFocus()  # kurzor rovnou do pole pro jméno

    def _show_editor(self):
        # schová login a ukáže pracovní plochu editoru
        self._hdr_title.setText("InfoBox – Editor článků")
        # zobrazí "jméno  •  role" v pravé části hlavičky
        self._hdr_user_label.setText(f"{self.my_username}  •  {self.my_role}")
        self._btn_new.show()
        self._btn_logout.show()
        self._login_page.hide()
        self._editor_page.show()

    # --- přihlášení a odhlášení ---

    def _on_login(self):
        # spustí se po kliknutí na Přihlásit nebo stisku Enter v poli
        u = self._login_user.text().strip()  # strip() odstraní mezery na začátku/konci
        p = self._login_pass.text()
        if not u or not p:
            self._toast.show_msg("Vyplň přihlašovací údaje.")
            return

        # odešle přihlašovací údaje na server v pozadí
        # výsledek přijde do _on_worker_result() s tagem "login"
        self._run_worker(
            lambda: self._api_login(u, p),
            tag="login"
        )

    def _on_logout(self):
        # smaže veškerý stav a vrátí uživatele na přihlašovací stránku
        self.token = None
        self.my_role = None
        self.my_username = None
        self.articles = []
        self.selected_article_id = None
        self._clear_form()
        self._show_login()
        self._toast.show_msg("Odhlášeno.")

    # --- práce s články ---

    def _on_new_article(self):
        # vyčistí formulář pro psaní nového článku
        # selected_article_id = None znamená že při uložení se vytvoří nový článek,
        # ne že by se upravoval existující
        self._clear_form()
        self._set_form_editable(True)
        self._article_list.clearSelection()  # zruší zvýraznění v levém seznamu
        self._toast.show_msg("Nový článek – vyplň a dej Uložit.")
        self._title_input.setFocus()  # kurzor rovnou do pole pro titulek

    def _on_article_selected(self, row):
        # spustí se automaticky když uživatel klikne na článek v levém seznamu
        if row < 0 or row >= len(self.articles):
            return  # nic není vybráno (např. seznam se právě aktualizoval)
        a = self.articles[row]
        self.selected_article_id = int(a["id"])
        aid = self.selected_article_id
        # načte plný detail článku ze serveru (obsah, kategorie, autor...)
        self._run_worker(
            lambda _aid=aid: self._api_get_article(_aid),
            tag="load_article"
        )

    def _on_save(self):
        # přečte co je zapsané ve formuláři
        title   = self._title_input.text().strip()
        perex   = self._perex_input.toPlainText().strip()
        content = self._content_input.toPlainText().strip()

        # titulek a obsah jsou povinné — bez nich neuložíme
        if not title or not content:
            self._toast.show_msg("Titulek a obsah jsou povinné.")
            return

        cat_ids = list(self.selected_cat_ids)  # převede set na seznam pro JSON

        if self.selected_article_id is None:
            # selected_article_id je None = vytváříme úplně nový článek
            self._run_worker(
                lambda: self._api_create_article(title, perex, content, cat_ids),
                tag="create"
            )
        else:
            # jinak upravujeme existující článek
            # proměnné zachytíme hodnotou hned (aid=aid, _t=title atd.)
            # jinak by lambda přistoupila k proměnným až při spuštění a mohly by se mezitím změnit
            aid = self.selected_article_id
            self._run_worker(
                lambda _aid=aid, _t=title, _p=perex, _c=content, _cats=cat_ids:
                    self._api_update_article(_aid, _t, _p, _c, _cats),
                tag="update"
            )

    def _on_delete(self):
        # ověří že je nějaký článek vybraný
        if self.selected_article_id is None:
            self._toast.show_msg("Nejdřív vyber článek.")
            return

        # zobrazí potvrzovací dialog — mazání je nevratné operace
        reply = QMessageBox.question(
            self, "Smazat článek",
            "Opravdu chceš smazat tento článek?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return  # uživatel kliknul Ne, nic neděláme

        aid = self.selected_article_id
        self._run_worker(
            lambda _aid=aid: self._api_delete_article(_aid),
            tag="delete"
        )

    def _on_import_txt(self):
        # otevře systémový dialog pro výběr souboru
        fp, _ = QFileDialog.getOpenFileName(
            self, "Importovat textový soubor", "",
            "Textové soubory (*.txt);;Všechny soubory (*.*)"
        )
        if not fp:
            return  # uživatel dialog zrušil

        try:
            # zkusíme nejprve UTF-8 (moderní kódování)
            with open(fp, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            # UTF-8 selhalo — soubor je pravděpodobně v starém českém kódování Windows-1250
            try:
                with open(fp, 'r', encoding='cp1250') as f:
                    text = f.read()
            except Exception as ex:
                self._toast.show_msg(f"Chyba čtení souboru: {ex}")
                return
        except Exception as ex:
            self._toast.show_msg(f"Chyba čtení souboru: {ex}")
            return

        self._content_input.setPlainText(text)  # vloží obsah souboru do pole obsahu
        self._toast.show_msg(f"Importováno z: {os.path.basename(fp)}")  # ukáže jen název souboru, ne celou cestu

    def _on_upload_image(self):
        # otevře dialog pro výběr obrázku
        fp, _ = QFileDialog.getOpenFileName(
            self, "Vyber obrázek", "",
            "Images (*.png *.jpg *.jpeg *.webp *.gif);;All files (*.*)"
        )
        if not fp:
            return  # uživatel dialog zrušil

        # nahraje obrázek na server na pozadí
        # po dokončení přijde výsledek do _on_worker_result() s tagem "upload"
        self._run_worker(
            lambda: self._api_upload_image(fp),
            tag="upload"
        )

    def _insert_md(self, snippet: str):
        # vloží Markdown zkratku na aktuální pozici kurzoru v poli obsahu
        cursor = self._content_input.textCursor()
        cursor.insertText(snippet)
        self._content_input.setFocus()  # vrátí fokus do pole aby uživatel mohl hned psát dál

    # --- zpracování výsledků z API vláken ---

    def _on_worker_result(self, data: dict, tag: str):
        # tato funkce dostane výsledek pokaždé když nějaký ApiWorker dokončí práci
        # tag říká co worker dělal, data obsahuje JSON odpověď ze serveru

        if tag == "login":
            if not data.get("ok"):
                # server vrátil chybu — špatné heslo, neexistující uživatel apod.
                self._toast.show_msg(data.get("error", "Přihlášení selhalo."))
            elif data.get("role") not in ("admin", "editor"):
                # přihlášení proběhlo, ale uživatel nemá roli admin ani editor — nemá sem přístup
                self._toast.show_msg(f"Role '{data.get('role')}' nemá přístup.")
            else:
                # přihlášení úspěšné — uložíme token a údaje o uživateli
                self.token       = data["token"]        # token pro další API requesty
                self.my_role     = data["role"]
                self.my_username = data["username"]
                self._my_user_id = data.get("user_id")  # potřebujeme pro porovnání autora článku
                self._show_editor()
                self._toast.show_msg(f"Přihlášen: {self.my_username} ({self.my_role})")
                # hned po přihlášení načteme seznam článků a kategorií
                self._run_worker(self._api_list_articles, tag="list_articles")
                self._run_worker(self._api_fetch_categories, tag="categories")

        elif tag == "list_articles":
            if not data.get("ok"):
                self._toast.show_msg(data.get("error", "Chyba načítání."))
                return
            self.articles = data.get("articles", [])

            # blockSignals zabrání tomu aby plnění seznamu spustilo _on_article_selected
            self._article_list.blockSignals(True)
            self._article_list.clear()

            for a in self.articles:
                item = QListWidgetItem()
                title  = (a.get("title") or "")[:40]   # ořízne příliš dlouhé titulky
                date   = (a.get("created_at") or "")[:19]   # jen datum a čas, bez milisekund
                author = a.get("author") or a.get("username") or "neznámý"
                item.setText(f"{title}\n{date}\n✍ {author}")
                self._article_list.addItem(item)

            self._article_list.blockSignals(False)  # zase povolíme signály
            self._toast.show_msg(f"Načteno: {len(self.articles)} článků")

        elif tag == "categories":
            if not data.get("ok"):
                return
            self.all_categories = data.get("categories", [])
            # znovu sestaví checkboxy v pravém panelu podle nových dat
            self._rebuild_categories()

        elif tag == "load_article":
            if not data.get("ok"):
                self._toast.show_msg(data.get("error", "Chyba načítání."))
                return
            a = data.get("article", {})
            # naplní formulář daty z načteného článku
            self._title_input.setText(a.get("title", "") or "")
            self._perex_input.setPlainText(a.get("perex", "") or "")
            self._content_input.setPlainText(a.get("content", "") or "")
            self.selected_cat_ids = set(a.get("category_ids", []))
            self._update_category_checkboxes()

            # editor smí editovat jen své vlastní články, admin smí editovat všechny
            is_own = (a.get("author_id") == self._get_my_user_id())
            can_edit = (self.my_role == "admin") or is_own
            self._set_form_editable(can_edit)
            if not can_edit:
                self._toast.show_msg("Tento článek patří jinému autorovi — pouze pro čtení.")

            # načteme statistiky článku (zobrazení, lajky, komentáře)
            aid = self.selected_article_id
            token = self.token
            if aid is not None:
                self._run_worker(
                    lambda _aid=aid, _tok=token: self._api_get_stats(_aid, _tok),
                    tag="stats"
                )

        elif tag == "stats":
            # zobrazí statistiky pod polem obsahu
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
                # obnoví seznam vlevo aby se nový článek zobrazil
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
                self._clear_form()  # vyprázdní formulář
                self._run_worker(self._api_list_articles, tag="list_articles")
            else:
                self._toast.show_msg(data.get("error", "Chyba mazání."))

        elif tag == "upload":
            if data.get("ok"):
                url = data.get("url", "")
                # vloží obrázek do obsahu článku jako HTML img tag
                self._insert_md(f'<p><img src="{url}" alt=""></p>\n')
                self._toast.show_msg("Obrázek nahrán.")
            else:
                self._toast.show_msg(data.get("error", "Upload selhal."))

    # --- kategorie v pravém panelu ---

    def _rebuild_categories(self):
        # smaže všechny stávající checkboxy a vytvoří je znovu podle aktuálního seznamu
        # > 1 protože na konci layoutu je stretch (prázdné místo) — to nechceme smazat
        while self._cat_layout.count() > 1:
            item = self._cat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()  # správně uvolní widget z paměti

        self._cat_checkboxes = {}  # slovník: cat_id → widget checkboxu
        for cat in self.all_categories:
            cb = QCheckBox(cat["name"])
            cb.setStyleSheet("padding: 4px 2px;")
            checked = cat["id"] in self.selected_cat_ids
            cb.setChecked(checked)
            cid = cat["id"]
            # c=cid zachytí hodnotu ID právě teď — stejný trik jako u Markdown tlačítek
            cb.stateChanged.connect(lambda state, c=cid: self._on_cat_toggled(c, state))
            self._cat_layout.insertWidget(self._cat_layout.count() - 1, cb)  # přidáme před stretch
            self._cat_checkboxes[cid] = cb

    def _update_category_checkboxes(self):
        # aktualizuje zaškrtnutí checkboxů podle self.selected_cat_ids
        for cid, cb in getattr(self, "_cat_checkboxes", {}).items():
            cb.blockSignals(True)   # vypneme signály aby zaškrtnutí programem nespustilo _on_cat_toggled
            cb.setChecked(cid in self.selected_cat_ids)
            cb.blockSignals(False)  # znovu zapneme

    def _on_cat_toggled(self, cat_id, state):
        # zavolá se když uživatel zaškrtne nebo odškrtne kategorii
        if state == Qt.Checked:
            self.selected_cat_ids.add(cat_id)      # přidá kategorii do setu
        else:
            self.selected_cat_ids.discard(cat_id)  # odebere kategorii ze setu (discard nespadne pokud tam není)

    # --- pomocné metody ---

    def _set_form_editable(self, editable: bool):
        # povolí nebo zamkne celý formulář
        # používá se když editor otevře cizí článek — vidí ho jen pro čtení
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

        # šedé pozadí jako vizuální signál že je formulář jen pro čtení
        bg = "#f0f0f0" if not editable else "white"
        for w in [self._title_input, self._perex_input, self._content_input]:
            w.setStyleSheet(w.styleSheet().split("background:")[0] +
                            f"background: {bg};" if "background:" in w.styleSheet()
                            else w.styleSheet() + f" background: {bg};")

    def _get_my_user_id(self) -> int | None:
        # vrátí ID přihlášeného uživatele — uložilo se při přihlášení
        # getattr s výchozí hodnotou None je bezpečné i kdybychom _my_user_id ještě nenastavili
        return getattr(self, "_my_user_id", None)

    def _clear_form(self):
        # vymaže celý formulář a resetuje stav na "nový článek"
        self.selected_article_id = None  # None = při uložení se vytvoří nový
        self.selected_cat_ids = set()
        self._title_input.clear()
        self._perex_input.clear()
        self._content_input.clear()
        self._stats_label.setStyleSheet("color: #aaa; font-size: 12px;")
        self._stats_label.setText("Vyber článek pro zobrazení statistik")
        self._update_category_checkboxes()  # odškrtá všechny kategorie

    def _run_worker(self, fn, tag=""):
        # vytvoří nové API vlákno, napojí ho na výsledkovou funkci a spustí ho
        w = ApiWorker(fn, tag)
        w.result.connect(self._on_worker_result)
        # po dokončení odstraníme vlákno ze seznamu aby ho mohl Python uvolnit z paměti
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(w)  # musíme ho držet v seznamu dokud běží — jinak by ho Python smazal předčasně
        w.start()  # spustí vlákno (zavolá run() v samostatném vlákně)

    # --- samotná API volání (vždy běží uvnitř ApiWorker vlákna) ---

    def _api_login(self, username, password):
        # pošle přihlašovací údaje na server
        # server vrátí token, roli a username pokud je vše v pořádku
        r = requests.post(
            f"{API_BASE}/api/login",
            json={"username": username, "password": password},
            timeout=8  # pokud server neodpoví do 8 sekund, request selže
        )
        return safe_json(r)

    def _api_list_articles(self):
        # načte seznam posledních 50 článků (jen metadata, ne obsah)
        r = requests.get(
            f"{API_BASE}/api/articles",
            headers=api_headers(self.token),
            timeout=10
        )
        return safe_json(r)

    def _api_get_article(self, aid):
        # načte plný detail jednoho článku včetně obsahu a přiřazených kategorií
        r = requests.get(
            f"{API_BASE}/api/articles/{aid}",
            headers=api_headers(self.token),
            timeout=10
        )
        return safe_json(r)

    def _api_create_article(self, title, perex, content, cat_ids):
        # vytvoří nový článek na serveru, vrátí jeho nové ID
        r = requests.post(
            f"{API_BASE}/api/articles",
            headers=api_headers(self.token),
            json={"title": title, "perex": perex, "content": content, "category_ids": cat_ids},
            timeout=12
        )
        return safe_json(r)

    def _api_update_article(self, aid, title, perex, content, cat_ids):
        # uloží změny do existujícího článku (přepíše titulek, obsah i kategorie)
        r = requests.put(
            f"{API_BASE}/api/articles/{aid}",
            headers=api_headers(self.token),
            json={"title": title, "perex": perex, "content": content, "category_ids": cat_ids},
            timeout=12
        )
        return safe_json(r)

    def _api_delete_article(self, aid):
        # smaže článek ze serveru — nevratná operace
        r = requests.delete(
            f"{API_BASE}/api/articles/{aid}",
            headers=api_headers(self.token),
            timeout=12
        )
        return safe_json(r)

    def _api_upload_image(self, filepath):
        # nahraje soubor obrázku na server přes multipart/form-data
        # server uloží obrázek a vrátí jeho URL pro vložení do článku
        with open(filepath, "rb") as f:
            r = requests.post(
                f"{API_BASE}/api/upload",
                headers=api_headers(self.token),
                files={"file": (os.path.basename(filepath), f)},  # basename = jen název souboru bez cesty
                timeout=20  # upload může trvat déle, dáme víc času
            )
        return safe_json(r)

    def _api_fetch_categories(self):
        # načte seznam kategorií — tato route je veřejná, nepotřebuje token
        r = requests.get(f"{API_BASE}/api/categories", timeout=6)
        return safe_json(r)

    def _api_get_stats(self, aid, token=None):
        # načte statistiky článku: počet zobrazení, unikátní zobrazení, lajky, komentáře
        tok = token or self.token  # pokud token není předán jako parametr, použije self.token
        r = requests.get(
            f"{API_BASE}/api/articles/{aid}/stats",
            headers=api_headers(tok),
            timeout=8
        )
        result = safe_json(r)
        return result

    # --- pomocné metody pro stylování ---

    @staticmethod
    def _btn_style(bg, hover):
        # vrátí CSS řetězec pro tlačítko s danou barvou pozadí a barvou při najetí myší
        # disabled stav je vždy šedý bez ohledu na barvu tlačítka
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
        # CSS pro jednořádkové textové pole — modrý rámeček při focusu
        return """
            QLineEdit {
                border: 1.5px solid #aaa; border-radius: 8px;
                padding: 0 10px; font-size: 14px; background: white;
            }
            QLineEdit:focus { border-color: #0077cc; }
        """

    @staticmethod
    def _textarea_style():
        # CSS pro víceřádkové textové pole — stejný styl jako input
        return """
            QTextEdit {
                border: 1.5px solid #aaa; border-radius: 8px;
                padding: 6px 10px; font-size: 14px; background: white;
            }
            QTextEdit:focus { border-color: #0077cc; }
        """

    @staticmethod
    def _lbl(text):
        # vytvoří malý šedý popisek nad polem formuláře (např. "Titulek", "Obsah")
        l = QLabel(text)
        l.setStyleSheet("color: #555; font-size: 12px;")
        return l


# --- spuštění programu ---

def main():
    app = QApplication(sys.argv)  # vytvoří Qt aplikaci (sys.argv předá příkazové argumenty)
    app.setStyle("Fusion")        # moderní vizuální styl který vypadá stejně na Windows i Linuxu
    app.setFont(QFont("Arial", 11))  # výchozí font pro celou aplikaci
    win = EditorWindow()          # vytvoří hlavní okno
    win.show()                    # zobrazí ho
    sys.exit(app.exec_())         # spustí smyčku událostí — program čeká na akce uživatele


# tento blok se spustí jen pokud spustíme soubor přímo (ne když ho importujeme jako modul)
if __name__ == "__main__":
    main()