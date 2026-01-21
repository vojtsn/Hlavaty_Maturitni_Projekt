import os
import sys
import textwrap
import pygame
import requests

# File dialog for image upload
import tkinter as tk
from tkinter import filedialog

API_BASE = "http://127.0.0.1:5000"


# -----------------------------
# Helpers
# -----------------------------
def api_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def safe_json(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "error": f"Neplatná odpověď serveru (HTTP {resp.status_code})."}

def clip(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


# -----------------------------
# Simple UI components
# -----------------------------
class Button:
    def __init__(self, rect, text, bg=(0, 119, 204), fg=(255, 255, 255)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.bg = bg
        self.fg = fg
        self.enabled = True

    def draw(self, screen, font):
        color = self.bg if self.enabled else (170, 170, 170)
        pygame.draw.rect(screen, color, self.rect, border_radius=10)
        pygame.draw.rect(screen, (60, 60, 60), self.rect, 2, border_radius=10)
        t = font.render(self.text, True, self.fg)
        screen.blit(t, t.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


class InputBox:
    """Single-line input."""
    def __init__(self, rect, placeholder="", password=False):
        self.rect = pygame.Rect(rect)
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.cursor = 0
        self.scroll_x = 0
        self.password = password

    def _display_text(self) -> str:
        if not self.text:
            return ""
        if self.password:
            return "*" * len(self.text)
        return self.text

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(e.pos)
            if self.active:
                self.cursor = len(self.text)

        if e.type == pygame.KEYDOWN and self.active:
            if e.key == pygame.K_BACKSPACE:
                if self.cursor > 0:
                    self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
                    self.cursor -= 1
            elif e.key == pygame.K_DELETE:
                if self.cursor < len(self.text):
                    self.text = self.text[: self.cursor] + self.text[self.cursor + 1 :]
            elif e.key == pygame.K_LEFT:
                self.cursor = max(0, self.cursor - 1)
            elif e.key == pygame.K_RIGHT:
                self.cursor = min(len(self.text), self.cursor + 1)
            elif e.key == pygame.K_HOME:
                self.cursor = 0
            elif e.key == pygame.K_END:
                self.cursor = len(self.text)
            elif e.key == pygame.K_RETURN:
                pass
            else:
                if e.unicode and e.unicode.isprintable():
                    self.text = self.text[: self.cursor] + e.unicode + self.text[self.cursor :]
                    self.cursor += 1

    def draw(self, screen, font, small_font):
        pygame.draw.rect(screen, (255, 255, 255), self.rect, border_radius=10)
        pygame.draw.rect(
            screen,
            (0, 119, 204) if self.active else (160, 160, 160),
            self.rect,
            2,
            border_radius=10,
        )

        inner = self.rect.inflate(-16, -10)

        # placeholder vs display text
        if not self.text:
            text_to_render = self.placeholder
            color = (130, 130, 130)
            display = ""
        else:
            text_to_render = self._display_text()
            color = (30, 30, 30)
            display = text_to_render

        # horizontal scroll so cursor stays visible (based on REAL text cursor pos)
        prefix_real = (self.text or "")[: self.cursor]
        cur_px = font.size(("*" * len(prefix_real)) if self.password else prefix_real)[0]

        if cur_px - self.scroll_x > inner.w - 10:
            self.scroll_x = cur_px - (inner.w - 10)
        if cur_px - self.scroll_x < 0:
            self.scroll_x = max(0, cur_px - 5)

        surf = font.render(text_to_render, True, color)
        screen.blit(surf, (inner.x - self.scroll_x, inner.y))

        if self.active:
            cx = inner.x + cur_px - self.scroll_x
            pygame.draw.line(screen, (0, 0, 0), (cx, inner.y), (cx, inner.y + inner.h), 2)


class TextArea:
    """Multiline text input with vertical scrolling + basic cursor."""
    def __init__(self, rect, placeholder=""):
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.text = ""
        self.active = False
        self.cursor = 0
        self.scroll_y = 0

    def _lines(self, font, width):
        raw = self.text.split("\n")
        out = []
        abs_i = 0
        for p_i, para in enumerate(raw):
            if para == "":
                out.append("")
                abs_i += 1
                continue

            words = para.split(" ")
            current = ""
            local_pos = 0
            for w in words:
                candidate = (current + (" " if current else "") + w)
                if font.size(candidate)[0] <= width:
                    current = candidate
                else:
                    if current:
                        out.append(current)
                        local_pos += len(current) + 1
                        current = w
                    else:
                        # long word -> char wrap fallback
                        for chunk in textwrap.wrap(w, width=max(1, int(width / max(8, font.size("W")[0])))):
                            out.append(chunk)
                            local_pos += len(chunk)
                        current = ""
            if current != "":
                out.append(current)

            abs_i += len(para)
            if p_i < len(raw) - 1:
                abs_i += 1
        return out

    def _clamp_cursor(self):
        self.cursor = max(0, min(len(self.text), self.cursor))

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(e.pos)
            if self.active:
                self.cursor = len(self.text)

        if e.type == pygame.MOUSEWHEEL:
            if self.rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_y -= e.y * 24
                self.scroll_y = max(0, self.scroll_y)

        if e.type == pygame.KEYDOWN and self.active:
            if e.key == pygame.K_BACKSPACE:
                if self.cursor > 0:
                    self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
                    self.cursor -= 1
            elif e.key == pygame.K_DELETE:
                if self.cursor < len(self.text):
                    self.text = self.text[: self.cursor] + self.text[self.cursor + 1 :]
            elif e.key == pygame.K_RETURN:
                self.text = self.text[: self.cursor] + "\n" + self.text[self.cursor :]
                self.cursor += 1
            elif e.key == pygame.K_TAB:
                # TextArea: Tab inserts spaces (focus switching řešíme globálně, ale tady to necháme když je aktivní)
                self.text = self.text[: self.cursor] + "    " + self.text[self.cursor :]
                self.cursor += 4
            elif e.key == pygame.K_LEFT:
                self.cursor -= 1
            elif e.key == pygame.K_RIGHT:
                self.cursor += 1
            elif e.key == pygame.K_HOME:
                self.cursor = 0
            elif e.key == pygame.K_END:
                self.cursor = len(self.text)
            else:
                if e.unicode and e.unicode.isprintable():
                    self.text = self.text[: self.cursor] + e.unicode + self.text[self.cursor :]
                    self.cursor += 1

            self._clamp_cursor()

    def insert_at_cursor(self, s: str):
        if not s:
            return
        self.text = self.text[: self.cursor] + s + self.text[self.cursor :]
        self.cursor += len(s)
        self._clamp_cursor()

    def draw(self, screen, font, small_font):
        pygame.draw.rect(screen, (255, 255, 255), self.rect, border_radius=12)
        pygame.draw.rect(
            screen,
            (0, 119, 204) if self.active else (160, 160, 160),
            self.rect,
            2,
            border_radius=12,
        )

        inner = self.rect.inflate(-16, -16)
        clip_rect = inner.copy()
        screen.set_clip(clip_rect)

        if not self.text:
            ph = small_font.render(self.placeholder, True, (130, 130, 130))
            screen.blit(ph, (inner.x, inner.y))
            screen.set_clip(None)
            return

        lines = self._lines(font, inner.w)
        line_h = font.get_linesize()
        y = inner.y - self.scroll_y

        for line in lines:
            surf = font.render(line, True, (25, 25, 25))
            screen.blit(surf, (inner.x, y))
            y += line_h

        if self.active:
            pygame.draw.line(
                screen,
                (0, 0, 0),
                (inner.x, inner.bottom - 4),
                (inner.x + 10, inner.bottom - 4),
                2,
            )

        screen.set_clip(None)


class Toast:
    def __init__(self):
        self.msg = ""
        self.until = 0

    def show(self, msg, ms=2500):
        self.msg = msg
        self.until = pygame.time.get_ticks() + ms

    def draw(self, screen, font, W):
        if not self.msg:
            return
        if pygame.time.get_ticks() > self.until:
            self.msg = ""
            return
        pad = 12
        surf = font.render(self.msg, True, (255, 255, 255))
        rect = surf.get_rect()
        bg = pygame.Rect(0, 0, rect.w + pad * 2, rect.h + pad * 2)
        bg.midbottom = (W // 2, 980)
        pygame.draw.rect(screen, (20, 20, 20), bg, border_radius=14)
        screen.blit(surf, surf.get_rect(center=bg.center))


# -----------------------------
# Focus helpers (TAB navigation)
# -----------------------------
def focus_next(widgets, current_idx, backwards=False):
    if not widgets:
        return 0
    step = -1 if backwards else 1
    n = len(widgets)
    i = current_idx
    for _ in range(n):
        i = (i + step) % n
        return i
    return current_idx

def set_active(widgets, idx):
    for i, w in enumerate(widgets):
        if hasattr(w, "active"):
            w.active = (i == idx)


# -----------------------------
# App
# -----------------------------
def main():
    pygame.init()
    pygame.display.set_caption("InfoBox – Redaktorský editor (Pygame)")

    # (2) Wider window
    W, H = 1400, 1000
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("arial", 22)
    small = pygame.font.SysFont("arial", 16)
    big = pygame.font.SysFont("arial", 28, bold=True)

    BG = (245, 248, 252)

    toast = Toast()

    # --- Login UI
    login_user = InputBox((480, 340, 440, 52), "Uživatelské jméno")
    # (4) password masked
    login_pass = InputBox((480, 410, 440, 52), "Heslo", password=True)
    btn_login = Button((480, 480, 200, 50), "Přihlásit")
    btn_quit = Button((720, 480, 200, 50), "Konec", bg=(90, 90, 90))

    token = None
    my_role = None
    my_username = None

    # --- Editor UI layout
    LIST_X, LIST_Y, LIST_W, LIST_H = 40, 120, 380, 820
    FORM_X = 450

    title_box = InputBox((FORM_X, 120, 900, 52), "Titulek (povinné)")
    perex_area = TextArea((FORM_X, 200, 900, 160), "Shrnutí obsahu")
    content_area = TextArea((FORM_X, 390, 900, 430), "Obsah článku (povinné)")

    btn_refresh = Button((40, 60, 150, 44), "Načíst")
    btn_new = Button((200, 60, 220, 44), "Nový článek", bg=(40, 160, 90))
    btn_save = Button((FORM_X, 840, 240, 54), "Uložit", bg=(0, 119, 204))
    btn_delete = Button((FORM_X + 260, 840, 220, 54), "Smazat", bg=(200, 60, 60))
    btn_upload_img = Button((FORM_X + 500, 840, 260, 54), "Nahrát obrázek", bg=(120, 90, 200))
    # (2) now always visible thanks to wider width, plus repositioned
    btn_logout = Button((FORM_X + 580, 60, 320, 44), "Odhlásit", bg=(90, 90, 90))

    # list state
    articles = []
    selected_index = -1
    selected_article_id = None
    list_scroll = 0

    def api_login_call(username, password):
        try:
            r = requests.post(f"{API_BASE}/api/login", json={"username": username, "password": password}, timeout=8)
        except Exception as ex:
            return {"ok": False, "error": f"Nelze se připojit na server: {ex}"}
        data = safe_json(r)
        if r.status_code != 200:
            return data
        return data

    def api_list_articles_call():
        nonlocal token
        try:
            r = requests.get(f"{API_BASE}/api/articles", headers=api_headers(token), timeout=10)
        except Exception as ex:
            return {"ok": False, "error": f"Chyba spojení: {ex}"}
        return safe_json(r)

    def api_get_article_call(aid: int):
        nonlocal token
        try:
            r = requests.get(f"{API_BASE}/api/articles/{aid}", headers=api_headers(token), timeout=10)
        except Exception as ex:
            return {"ok": False, "error": f"Chyba spojení: {ex}"}
        return safe_json(r)

    def api_create_article_call(title, perex, content):
        nonlocal token
        try:
            r = requests.post(
                f"{API_BASE}/api/articles",
                headers=api_headers(token),
                json={"title": title, "perex": perex, "content": content},
                timeout=12,
            )
        except Exception as ex:
            return {"ok": False, "error": f"Chyba spojení: {ex}"}
        return safe_json(r)

    def api_update_article_call(aid, title, perex, content):
        nonlocal token
        try:
            r = requests.put(
                f"{API_BASE}/api/articles/{aid}",
                headers=api_headers(token),
                json={"title": title, "perex": perex, "content": content},
                timeout=12,
            )
        except Exception as ex:
            return {"ok": False, "error": f"Chyba spojení: {ex}"}
        return safe_json(r)

    def api_delete_article_call(aid):
        nonlocal token
        try:
            r = requests.delete(f"{API_BASE}/api/articles/{aid}", headers=api_headers(token), timeout=12)
        except Exception as ex:
            return {"ok": False, "error": f"Chyba spojení: {ex}"}
        return safe_json(r)

    def api_upload_image_call(filepath: str):
        nonlocal token
        try:
            with open(filepath, "rb") as f:
                files = {"file": (os.path.basename(filepath), f)}
                r = requests.post(f"{API_BASE}/api/upload", headers=api_headers(token), files=files, timeout=20)
        except Exception as ex:
            return {"ok": False, "error": f"Chyba uploadu: {ex}"}
        return safe_json(r)

    def refresh_articles():
        nonlocal articles, selected_index, selected_article_id, list_scroll
        data = api_list_articles_call()
        if not data.get("ok"):
            toast.show(data.get("error", "Nepovedlo se načíst články."))
            return
        articles = data.get("articles", [])
        selected_index = -1
        selected_article_id = None
        list_scroll = 0
        toast.show(f"Načteno: {len(articles)} článků")

    def clear_form():
        nonlocal selected_article_id, selected_index
        selected_article_id = None
        selected_index = -1
        title_box.text = ""
        title_box.cursor = 0
        perex_area.text = ""
        perex_area.cursor = 0
        perex_area.scroll_y = 0
        content_area.text = ""
        content_area.cursor = 0
        content_area.scroll_y = 0

    def load_article_into_form(aid: int):
        data = api_get_article_call(aid)
        if not data.get("ok"):
            toast.show(data.get("error", "Nepovedlo se načíst článek."))
            return
        a = data.get("article", {})
        title_box.text = a.get("title", "") or ""
        title_box.cursor = len(title_box.text)
        perex_area.text = a.get("perex", "") or ""
        perex_area.cursor = len(perex_area.text)
        perex_area.scroll_y = 0
        content_area.text = a.get("content", "") or ""
        content_area.cursor = len(content_area.text)
        content_area.scroll_y = 0

    def draw_articles_list():
        panel = pygame.Rect(LIST_X, LIST_Y, LIST_W, LIST_H)
        pygame.draw.rect(screen, (255, 255, 255), panel, border_radius=14)
        pygame.draw.rect(screen, (200, 200, 200), panel, 2, border_radius=14)

        inner = panel.inflate(-14, -14)
        screen.set_clip(inner)

        item_h = 58
        y = inner.y - list_scroll

        for i, a in enumerate(articles):
            is_sel = (i == selected_index)
            r = pygame.Rect(inner.x, y, inner.w, item_h - 8)
            if is_sel:
                pygame.draw.rect(screen, (225, 240, 255), r, border_radius=12)
                pygame.draw.rect(screen, (0, 119, 204), r, 2, border_radius=12)
            else:
                pygame.draw.rect(screen, (248, 248, 248), r, border_radius=12)
                pygame.draw.rect(screen, (220, 220, 220), r, 1, border_radius=12)

            title = a.get("title", "")
            created = a.get("created_at", "")
            line1 = font.render(clip(title, 30), True, (15, 15, 15))
            line2 = small.render(clip(created, 36), True, (90, 90, 90))
            screen.blit(line1, (r.x + 10, r.y + 8))
            screen.blit(line2, (r.x + 10, r.y + 32))
            y += item_h

        screen.set_clip(None)

        if len(articles) * 58 > inner.h:
            hint = small.render("Kolečko myši = scroll", True, (120, 120, 120))
            screen.blit(hint, (panel.x + 10, panel.bottom - 24))

    def list_click(pos):
        nonlocal selected_index, selected_article_id
        panel = pygame.Rect(LIST_X, LIST_Y, LIST_W, LIST_H)
        inner = panel.inflate(-14, -14)
        if not panel.collidepoint(pos):
            return
        rel_y = pos[1] - inner.y + list_scroll
        item_h = 58
        idx = int(rel_y // item_h)
        if 0 <= idx < len(articles):
            selected_index = idx
            selected_article_id = int(articles[idx]["id"])
            load_article_into_form(selected_article_id)

    # (1) Focus lists
    login_fields = [login_user, login_pass]
    login_focus = 0
    set_active(login_fields, login_focus)

    editor_fields = [title_box, perex_area, content_area]
    editor_focus = 0
    set_active(editor_fields, editor_focus)

    mode = "login"

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

            # (1) TAB navigation (global)
            if e.type == pygame.KEYDOWN and e.key == pygame.K_TAB:
                backwards = bool(e.mod & pygame.KMOD_SHIFT)
                if mode == "login":
                    login_focus = (login_focus - 1) % len(login_fields) if backwards else (login_focus + 1) % len(login_fields)
                    set_active(login_fields, login_focus)
                    # prevent tab from being typed into fields (especially in password)
                    continue
                else:
                    editor_focus = (editor_focus - 1) % len(editor_fields) if backwards else (editor_focus + 1) % len(editor_fields)
                    set_active(editor_fields, editor_focus)
                    continue

            if mode == "login":
                login_user.handle_event(e)
                login_pass.handle_event(e)

                if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                    # Enter = login
                    if login_user.text.strip() and login_pass.text:
                        epos = pygame.mouse.get_pos()

                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    if btn_login.hit(e.pos):
                        u = login_user.text.strip()
                        p = login_pass.text
                        if not u or not p:
                            toast.show("Vyplň uživatelské jméno a heslo.")
                        else:
                            data = api_login_call(u, p)
                            if not data.get("ok"):
                                toast.show(data.get("error", "Přihlášení selhalo."))
                            else:
                                role = data.get("role")
                                if role not in ("admin", "editor"):
                                    toast.show(f"Role '{role}' nemá přístup (povoleno jen admin/editor).")
                                else:
                                    token = data.get("token")
                                    my_role = role
                                    my_username = data.get("username")
                                    mode = "editor"
                                    toast.show(f"Přihlášen: {my_username} ({my_role})")
                                    refresh_articles()
                                    editor_focus = 0
                                    set_active(editor_fields, editor_focus)

                    if btn_quit.hit(e.pos):
                        pygame.quit()
                        sys.exit(0)

            else:
                # editor mode
                title_box.handle_event(e)
                perex_area.handle_event(e)
                content_area.handle_event(e)

                if e.type == pygame.MOUSEWHEEL:
                    panel = pygame.Rect(LIST_X, LIST_Y, LIST_W, LIST_H)
                    if panel.collidepoint(pygame.mouse.get_pos()):
                        list_scroll -= e.y * 40
                        list_scroll = max(0, list_scroll)

                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    if btn_refresh.hit(e.pos):
                        refresh_articles()

                    elif btn_new.hit(e.pos):
                        clear_form()
                        toast.show("Nový článek – vyplň a dej Uložit.")
                        editor_focus = 0
                        set_active(editor_fields, editor_focus)

                    elif btn_save.hit(e.pos):
                        t = (title_box.text or "").strip()
                        per = (perex_area.text or "").strip()
                        cont = (content_area.text or "").strip()

                        if not t or not cont:
                            toast.show("Titulek a obsah jsou povinné.")
                        else:
                            if selected_article_id is None:
                                data = api_create_article_call(t, per, cont)
                                if data.get("ok"):
                                    toast.show(f"Vytvořeno (id {data.get('id')}).")
                                    refresh_articles()
                                else:
                                    toast.show(data.get("error", "Nepovedlo se vytvořit."))
                            else:
                                data = api_update_article_call(selected_article_id, t, per, cont)
                                if data.get("ok"):
                                    toast.show("Uloženo.")
                                    refresh_articles()
                                else:
                                    toast.show(data.get("error", "Nepovedlo se uložit."))

                    elif btn_delete.hit(e.pos):
                        if selected_article_id is None:
                            toast.show("Nejdřív vyber článek.")
                        else:
                            data = api_delete_article_call(selected_article_id)
                            if data.get("ok"):
                                toast.show("Smazáno.")
                                clear_form()
                                refresh_articles()
                            else:
                                toast.show(data.get("error", "Nepovedlo se smazat."))

                    elif btn_upload_img.hit(e.pos):
                        root = tk.Tk()
                        root.withdraw()
                        filepath = filedialog.askopenfilename(
                            title="Vyber obrázek",
                            filetypes=[
                                ("Images", "*.png;*.jpg;*.jpeg;*.webp;*.gif"),
                                ("All files", "*.*"),
                            ],
                        )
                        root.destroy()

                        if filepath:
                            up = api_upload_image_call(filepath)
                            if up.get("ok"):
                                url = up.get("url", "")
                                snippet = f'<p><img src="{url}" alt=""></p>\n'
                                content_area.insert_at_cursor(snippet)
                                toast.show("Obrázek nahrán a vložen do obsahu.")
                            else:
                                toast.show(up.get("error", "Upload selhal."))

                    elif btn_logout.hit(e.pos):
                        token = None
                        my_role = None
                        my_username = None
                        mode = "login"
                        clear_form()
                        articles = []
                        selected_index = -1
                        selected_article_id = None
                        toast.show("Odhlášeno.")
                        login_focus = 0
                        set_active(login_fields, login_focus)

                    else:
                        list_click(e.pos)

                        # click into fields should update focus index too
                        if title_box.rect.collidepoint(e.pos):
                            editor_focus = 0
                            set_active(editor_fields, editor_focus)
                        elif perex_area.rect.collidepoint(e.pos):
                            editor_focus = 1
                            set_active(editor_fields, editor_focus)
                        elif content_area.rect.collidepoint(e.pos):
                            editor_focus = 2
                            set_active(editor_fields, editor_focus)

        # -----------------------------
        # Draw
        # -----------------------------
        screen.fill(BG)

        if mode == "login":
            title = big.render("InfoBox – Redaktorský editor", True, (10, 10, 10))
            subtitle = small.render("Přihlášení vyžaduje roli admin/editor", True, (80, 80, 80))
            screen.blit(title, (480, 250))
            screen.blit(subtitle, (480, 286))

            login_user.draw(screen, font, small)
            login_pass.draw(screen, font, small)
            btn_login.draw(screen, font)
            btn_quit.draw(screen, font)

            # (3) Tip removed

        else:
            header = big.render("InfoBox – Editor článků", True, (10, 10, 10))
            who = small.render(f"Přihlášen: {my_username}  |  role: {my_role}", True, (70, 70, 70))
            screen.blit(header, (40, 18))
            screen.blit(who, (40, 52))

            btn_refresh.draw(screen, font)
            btn_new.draw(screen, font)
            btn_logout.draw(screen, font)

            l1 = small.render("Články (klikni pro načtení)", True, (60, 60, 60))
            screen.blit(l1, (LIST_X, LIST_Y - 24))
            draw_articles_list()

            f1 = small.render("Titulek", True, (60, 60, 60))
            screen.blit(f1, (FORM_X, 96))
            title_box.draw(screen, font, small)

            f2 = small.render("Shrnutí", True, (60, 60, 60))
            screen.blit(f2, (FORM_X, 176))
            perex_area.draw(screen, font, small)

            f3 = small.render("Obsah", True, (60, 60, 60))
            screen.blit(f3, (FORM_X, 366))
            content_area.draw(screen, font, small)

            btn_save.draw(screen, font)
            btn_delete.draw(screen, font)
            btn_upload_img.draw(screen, font)

            help1 = small.render("Pozn.: oprávnění (kdo může co editovat) vynucuje server.", True, (90, 90, 90))
            screen.blit(help1, (FORM_X, 910))

        toast.draw(screen, font, W)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
