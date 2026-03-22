import os
import sys
import textwrap
import pygame
import requests

try:
    import pyperclip
    CLIPBOARD_OK = True
except ImportError:
    CLIPBOARD_OK = False

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
            ctrl = bool(e.mod & pygame.KMOD_CTRL)
            if ctrl and e.key == pygame.K_a:
                self.cursor = len(self.text)
                return
            if ctrl and e.key == pygame.K_c:
                if CLIPBOARD_OK:
                    pyperclip.copy(self.text)
                return
            if ctrl and e.key == pygame.K_v:
                if CLIPBOARD_OK:
                    clip = pyperclip.paste()
                    if clip:
                        self.text = self.text[:self.cursor] + clip + self.text[self.cursor:]
                        self.cursor += len(clip)
                return
            if ctrl and e.key == pygame.K_x:
                if CLIPBOARD_OK:
                    pyperclip.copy(self.text)
                    self.text = ""
                    self.cursor = 0
                return
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
    """Multiline text input — správný kurzor, klikání myší, key repeat."""

    def __init__(self, rect, placeholder=""):
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.text = ""
        self.active = False
        self.cursor = 0
        self.scroll_y = 0
        self._cursor_visible = True
        self._cursor_timer = 0
        self._font = None  # nastaví se při prvním draw()
        self._undo_stack = []   # seznam (text, cursor) stavů
        self._redo_stack = []
        self._last_saved = ""   # poslední uložený stav pro detekci změn

    def _push_undo(self):
        """Uloží aktuální stav do undo zásobníku."""
        if self._undo_stack and self._undo_stack[-1][0] == self.text:
            return  # nezaznamenávej duplicitní stavy
        self._undo_stack.append((self.text, self.cursor))
        if len(self._undo_stack) > 100:  # max 100 kroků zpět
            self._undo_stack.pop(0)
        self._redo_stack.clear()  # nová změna = redo se vyprázdní

    def _undo(self):
        """Vrátí se o krok zpět."""
        if not self._undo_stack:
            return
        self._redo_stack.append((self.text, self.cursor))
        self.text, self.cursor = self._undo_stack.pop()

    def _redo(self):
        """Znovu aplikuje poslední undo."""
        if not self._redo_stack:
            return
        self._undo_stack.append((self.text, self.cursor))
        self.text, self.cursor = self._redo_stack.pop()

    # ── word wrap: vrátí seznam (vizuální_řádek, start_index_v_textu) ──
    def _lines(self, font, width):
        """Vrátí list (text_řádku, abs_start) pro word wrap."""
        raw = self.text.split("\n")
        out = []
        abs_pos = 0
        for para in raw:
            if para == "":
                out.append(("", abs_pos))
                abs_pos += 1
                continue
            words = para.split(" ")
            current = ""
            line_start = abs_pos
            for w in words:
                candidate = (current + (" " if current else "") + w)
                if font.size(candidate)[0] <= width:
                    current = candidate
                else:
                    if current:
                        out.append((current, line_start))
                        line_start += len(current) + 1
                        current = w
                    else:
                        out.append((w, line_start))
                        line_start += len(w)
                        current = ""
            if current:
                out.append((current, line_start))
            abs_pos += len(para) + 1
        return out

    def _clamp_cursor(self):
        self.cursor = max(0, min(len(self.text), self.cursor))

    def _cursor_from_mouse(self, pos, font):
        """Vypočítá pozici kurzoru v textu z pozice myši."""
        inner = self.rect.inflate(-16, -16)
        lines = self._lines(font, inner.w)
        line_h = font.get_linesize()

        rel_y = pos[1] - inner.y + self.scroll_y
        line_idx = max(0, min(len(lines) - 1, int(rel_y // line_h)))

        if not lines:
            return 0

        line_text, line_start = lines[line_idx]
        rel_x = pos[0] - inner.x

        # najdi nejbližší pozici v řádku
        best_pos = line_start
        for i in range(len(line_text) + 1):
            w = font.size(line_text[:i])[0]
            if w <= rel_x:
                best_pos = line_start + i
            else:
                break

        return min(best_pos, len(self.text))

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.rect.collidepoint(e.pos):
                self.active = True
                # přesun kurzoru na kliknuté místo
                if self._font:
                    self.cursor = self._cursor_from_mouse(e.pos, self._font)
                self._cursor_visible = True
                self._cursor_timer = pygame.time.get_ticks()
            else:
                self.active = False

        if e.type == pygame.MOUSEWHEEL:
            if self.rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_y -= e.y * 24
                self.scroll_y = max(0, self.scroll_y)

        if e.type == pygame.KEYDOWN and self.active:
            ctrl  = bool(e.mod & pygame.KMOD_CTRL)
            shift = bool(e.mod & pygame.KMOD_SHIFT)

            # Ctrl+Z — undo
            if ctrl and not shift and e.key == pygame.K_z:
                self._push_undo()
                self._undo()
                self._clamp_cursor()
                return
            # Ctrl+Y nebo Ctrl+Shift+Z — redo
            if ctrl and (e.key == pygame.K_y or (shift and e.key == pygame.K_z)):
                self._redo()
                self._clamp_cursor()
                return
            # Ctrl+A — přesuň kurzor na konec (vše)
            if ctrl and e.key == pygame.K_a:
                self.cursor = len(self.text)
                return
            # Ctrl+C — kopíruj
            if ctrl and e.key == pygame.K_c:
                if CLIPBOARD_OK:
                    pyperclip.copy(self.text)
                return
            # Ctrl+V — vlož
            if ctrl and e.key == pygame.K_v:
                if CLIPBOARD_OK:
                    clip = pyperclip.paste()
                    if clip:
                        self._push_undo()
                        self.text = self.text[:self.cursor] + clip + self.text[self.cursor:]
                        self.cursor += len(clip)
                return
            # Ctrl+X — vyjmi
            if ctrl and e.key == pygame.K_x:
                if CLIPBOARD_OK:
                    self._push_undo()
                    pyperclip.copy(self.text)
                    self.text = ""
                    self.cursor = 0
                return

            # Před každou změnou textu ulož stav do undo
            if e.key == pygame.K_BACKSPACE:
                if self.cursor > 0:
                    self._push_undo()
                    self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                    self.cursor -= 1
            elif e.key == pygame.K_DELETE:
                if self.cursor < len(self.text):
                    self._push_undo()
                    self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
            elif e.key == pygame.K_RETURN:
                self._push_undo()
                self.text = self.text[:self.cursor] + "\n" + self.text[self.cursor:]
                self.cursor += 1
            elif e.key == pygame.K_TAB:
                self._push_undo()
                self.text = self.text[:self.cursor] + "    " + self.text[self.cursor:]
                self.cursor += 4
            elif e.key == pygame.K_LEFT:
                self.cursor = max(0, self.cursor - 1)
            elif e.key == pygame.K_RIGHT:
                self.cursor = min(len(self.text), self.cursor + 1)
            elif e.key == pygame.K_UP:
                self._move_cursor_vertical(-1)
            elif e.key == pygame.K_DOWN:
                self._move_cursor_vertical(1)
            elif e.key == pygame.K_HOME:
                self.cursor = 0
            elif e.key == pygame.K_END:
                self.cursor = len(self.text)
            else:
                if e.unicode and e.unicode.isprintable():
                    self.text = self.text[:self.cursor] + e.unicode + self.text[self.cursor:]
                    self.cursor += 1

            self._clamp_cursor()
            self._cursor_visible = True
            self._cursor_timer = pygame.time.get_ticks()

    def _move_cursor_vertical(self, direction):
        """Přesune kurzor o řádek nahoru/dolů."""
        if not self._font:
            return
        font = self._font
        inner = self.rect.inflate(-16, -16)
        lines = self._lines(font, inner.w)
        if not lines:
            return

        # najdi aktuální řádek
        cur_line = 0
        for i, (line_text, line_start) in enumerate(lines):
            if line_start <= self.cursor <= line_start + len(line_text):
                cur_line = i

        target_line = cur_line + direction
        if not (0 <= target_line < len(lines)):
            return

        # zjisti x pozici kurzoru v aktuálním řádku
        line_text, line_start = lines[cur_line]
        offset = self.cursor - line_start
        cur_x = font.size(line_text[:offset])[0]

        # najdi nejbližší pozici v cílovém řádku
        t_text, t_start = lines[target_line]
        best = t_start
        for i in range(len(t_text) + 1):
            if font.size(t_text[:i])[0] <= cur_x:
                best = t_start + i
        self.cursor = min(best, len(self.text))

    def insert_at_cursor(self, s: str):
        if not s:
            return
        self.text = self.text[:self.cursor] + s + self.text[self.cursor:]
        self.cursor += len(s)
        self._clamp_cursor()

    def draw(self, screen, font, small_font):
        self._font = font  # ulož font pro použití v handle_event
        pygame.draw.rect(screen, (255, 255, 255), self.rect, border_radius=12)
        pygame.draw.rect(
            screen,
            (0, 119, 204) if self.active else (160, 160, 160),
            self.rect, 2, border_radius=12,
        )

        inner = self.rect.inflate(-16, -16)
        screen.set_clip(inner)

        if not self.text:
            ph = small_font.render(self.placeholder, True, (130, 130, 130))
            screen.blit(ph, (inner.x, inner.y))
            screen.set_clip(None)
            return

        lines = self._lines(font, inner.w)
        line_h = font.get_linesize()

        # blikání kurzoru (500ms interval)
        now = pygame.time.get_ticks()
        if now - self._cursor_timer > 500:
            self._cursor_visible = not self._cursor_visible
            self._cursor_timer = now

        # auto-scroll aby byl kurzor vidět
        cur_line = 0
        for i, (line_text, line_start) in enumerate(lines):
            if line_start <= self.cursor <= line_start + len(line_text):
                cur_line = i
                break
        cur_y_abs = cur_line * line_h
        if cur_y_abs - self.scroll_y < 0:
            self.scroll_y = max(0, cur_y_abs - line_h)
        if cur_y_abs - self.scroll_y > inner.h - line_h * 2:
            self.scroll_y = cur_y_abs - inner.h + line_h * 2

        # kreslení řádků
        y = inner.y - self.scroll_y
        for i, (line_text, line_start) in enumerate(lines):
            if y + line_h >= inner.y and y <= inner.bottom:
                surf = font.render(line_text, True, (25, 25, 25))
                screen.blit(surf, (inner.x, y))

                # kurzor
                if self.active and self._cursor_visible:
                    if line_start <= self.cursor <= line_start + len(line_text):
                        offset = self.cursor - line_start
                        cx = inner.x + font.size(line_text[:offset])[0]
                        pygame.draw.line(screen, (0, 0, 0),
                                         (cx, y + 2), (cx, y + line_h - 2), 2)
            y += line_h

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
    pygame.key.set_repeat(400, 50)
    pygame.display.set_caption("InfoBox – Redaktorský editor")

    W, H = 1280, 860
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    clock  = pygame.time.Clock()

    font  = pygame.font.SysFont("arial", 20)
    small = pygame.font.SysFont("arial", 15)
    big   = pygame.font.SysFont("arial", 24, bold=True)

    BG  = (245, 248, 252)
    PAD = 14
    HDR = 52   # výška hlavičkového pruhu

    toast = Toast()

    # ── Widgety (rect se přepočítá v rebuild_layout) ─────────────────
    login_user = InputBox((0,0,360,46), "Uživatelské jméno")
    login_pass = InputBox((0,0,360,46), "Heslo", password=True)
    btn_login  = Button((0,0,160,44), "Přihlásit")
    btn_quit   = Button((0,0,160,44), "Konec", bg=(90,90,90))

    title_box    = InputBox((0,0,100,46), "Titulek (povinné)")
    perex_area   = TextArea((0,0,100,100), "Shrnutí obsahu")
    content_area = TextArea((0,0,100,100), "Obsah článku (povinné)")

    btn_new        = Button((0,0,150,38), "Nový článek", bg=(40,160,90))
    btn_save       = Button((0,0,150,44), "Uložit", bg=(0,119,204))
    btn_delete     = Button((0,0,140,44), "Smazat", bg=(200,60,60))
    btn_upload_img = Button((0,0,170,44), "Nahrát obrázek", bg=(120,90,200))
    btn_logout     = Button((0,0,150,38), "Odhlásit", bg=(90,90,90))

    MD_LABELS   = ["H1","H2","B","I","Seznam","Odkaz","Citace","---"]
    md_snippets = ["# ","## ","**text**","*text*","- ","[text](url)","> ","\n---\n"]
    MD_WIDTHS   = [44, 44, 36, 32, 72, 68, 68, 44]
    md_btns = [Button((0,0,MD_WIDTHS[i],28), MD_LABELS[i], bg=(80,80,80))
               for i in range(len(MD_LABELS))]

    # stav
    token = None; my_role = None; my_username = None
    all_categories = []; selected_cat_ids = set(); cat_scroll = 0
    articles = []; selected_index = -1; selected_article_id = None
    list_scroll = 0
    current_stats = {"views": 0, "likes": 0, "comments": 0}
    mode = "login"

    # ── Layout přepočet ──────────────────────────────────────────────
    LIST_W = 270
    CAT_W  = 190

    LABEL_H = 18
    STATS_H = 26

    def rebuild_layout():
        # Login (vycentrované)
        lw = 360; cx_btn = W // 2
        login_user.rect = pygame.Rect(cx_btn - lw//2, H//2 - 120, lw, 46)
        login_pass.rect = pygame.Rect(cx_btn - lw//2, H//2 - 62,  lw, 46)
        btn_login.rect  = pygame.Rect(cx_btn - 170,   H//2 + 2,   160, 44)
        btn_quit.rect   = pygame.Rect(cx_btn + 10,    H//2 + 2,   160, 44)

        # Header tlačítka
        btn_new.rect    = pygame.Rect(PAD + LIST_W + PAD, (HDR-38)//2, 150, 38)
        btn_logout.rect = pygame.Rect(W - PAD - 150, (HDR-38)//2, 150, 38)

        # Formulář
        GAP = 8
        fx = PAD + LIST_W + PAD
        fw = W - fx - PAD - CAT_W - PAD

        fy = HDR + PAD + LABEL_H
        title_box.rect = pygame.Rect(fx, fy, fw, 46)

        fy += 46 + GAP + LABEL_H
        perex_area.rect = pygame.Rect(fx, fy, fw, 90)

        fy += 90 + GAP  # MD toolbar (inline, bez extra LABEL_H)
        mx = fx
        for mb in md_btns:
            mb.rect.x = mx; mb.rect.y = fy; mb.rect.height = 28
            mx += mb.rect.width + 5

        fy += 28 + GAP + LABEL_H
        # Dole: tlačítka + statistiky + okraj
        bottom = PAD + 44 + GAP + STATS_H + PAD
        content_h = H - fy - bottom
        content_area.rect = pygame.Rect(fx, fy, fw, max(content_h, 80))

        stats_y = H - PAD - STATS_H
        btn_y   = stats_y - GAP - 44
        btn_save.rect       = pygame.Rect(fx,       btn_y, 150, 44)
        btn_delete.rect     = pygame.Rect(fx+160,   btn_y, 140, 44)
        btn_upload_img.rect = pygame.Rect(fx+310,   btn_y, 170, 44)

        return fx, fw, btn_y, stats_y

    fx, fw, btn_y, stats_y = rebuild_layout()

    # ── API volání ────────────────────────────────────────────────────
    def api_headers(t): return {"Authorization": f"Bearer {t}"}
    def safe_json(r):
        try: return r.json()
        except: return {"ok": False, "error": f"HTTP {r.status_code}"}

    def api_login_call(u, p):
        try:
            r = requests.post(f"{API_BASE}/api/login", json={"username":u,"password":p}, timeout=8)
            return safe_json(r)
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def api_list_articles_call():
        try:
            r = requests.get(f"{API_BASE}/api/articles", headers=api_headers(token), timeout=10)
            return safe_json(r)
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def api_get_article_call(aid):
        try:
            r = requests.get(f"{API_BASE}/api/articles/{aid}", headers=api_headers(token), timeout=10)
            return safe_json(r)
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def api_create_article_call(title, perex, content, cat_ids=None):
        try:
            r = requests.post(f"{API_BASE}/api/articles", headers=api_headers(token),
                json={"title":title,"perex":perex,"content":content,"category_ids":cat_ids or []}, timeout=12)
            return safe_json(r)
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def api_update_article_call(aid, title, perex, content, cat_ids=None):
        try:
            r = requests.put(f"{API_BASE}/api/articles/{aid}", headers=api_headers(token),
                json={"title":title,"perex":perex,"content":content,"category_ids":cat_ids or []}, timeout=12)
            return safe_json(r)
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def api_delete_article_call(aid):
        try:
            r = requests.delete(f"{API_BASE}/api/articles/{aid}", headers=api_headers(token), timeout=12)
            return safe_json(r)
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def api_upload_image_call(filepath):
        try:
            with open(filepath, "rb") as f:
                r = requests.post(f"{API_BASE}/api/upload", headers=api_headers(token),
                    files={"file":(os.path.basename(filepath), f)}, timeout=20)
            return safe_json(r)
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def api_get_stats_call(aid):
        try:
            r = requests.get(f"{API_BASE}/api/articles/{aid}/stats", headers=api_headers(token), timeout=8)
            return safe_json(r)
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def fetch_categories():
        nonlocal all_categories
        try:
            r = requests.get(f"{API_BASE}/api/categories", timeout=6)
            d = safe_json(r)
            if d.get("ok"):
                all_categories = d.get("categories", [])
        except:
            all_categories = []

    # ── Stavové funkce ───────────────────────────────────────────────
    def refresh_articles():
        nonlocal articles, selected_index, selected_article_id, list_scroll
        d = api_list_articles_call()
        if not d.get("ok"):
            toast.show(d.get("error","Chyba načítání."))
            return
        articles = d.get("articles", [])
        selected_index = -1; selected_article_id = None; list_scroll = 0
        toast.show(f"Načteno: {len(articles)} článků")

    def clear_form():
        nonlocal selected_article_id, selected_index, selected_cat_ids, current_stats
        selected_article_id = None; selected_index = -1
        selected_cat_ids = set()
        current_stats = {"views":0,"likes":0,"comments":0}
        for w in [title_box, perex_area, content_area]:
            w.text = ""; w.cursor = 0
        perex_area.scroll_y = 0; content_area.scroll_y = 0

    def load_article_into_form(aid):
        nonlocal selected_cat_ids, current_stats
        d = api_get_article_call(aid)
        if not d.get("ok"):
            toast.show(d.get("error","Chyba načítání.")); return
        a = d.get("article", {})
        title_box.text    = a.get("title","") or ""; title_box.cursor = len(title_box.text)
        perex_area.text   = a.get("perex","") or ""; perex_area.cursor = len(perex_area.text)
        content_area.text = a.get("content","") or ""; content_area.cursor = len(content_area.text)
        perex_area.scroll_y = 0; content_area.scroll_y = 0
        selected_cat_ids = set(a.get("category_ids",[]))
        sd = api_get_stats_call(aid)
        if sd.get("ok"):
            current_stats = sd.get("stats", {"views":0,"likes":0,"comments":0})

    # ── Draw helpers ─────────────────────────────────────────────────
    def draw_list():
        lx = PAD; ly = HDR + PAD; lh = H - ly - PAD
        panel = pygame.Rect(lx, ly, LIST_W, lh)
        pygame.draw.rect(screen, (255,255,255), panel, border_radius=12)
        pygame.draw.rect(screen, (200,200,200), panel, 1, border_radius=12)
        inner = panel.inflate(-10,-10)
        screen.set_clip(inner)
        item_h = 54; y = inner.y - list_scroll
        for i, a in enumerate(articles):
            sel = (i == selected_index)
            r = pygame.Rect(inner.x, y, inner.w, item_h-6)
            col_bg  = (220,235,255) if sel else (248,248,248)
            col_brd = (0,119,204)   if sel else (220,220,220)
            pygame.draw.rect(screen, col_bg,  r, border_radius=8)
            pygame.draw.rect(screen, col_brd, r, 1, border_radius=8)
            screen.blit(font.render(clip(a.get("title",""),28), True, (15,15,15)), (r.x+8, r.y+6))
            screen.blit(small.render(clip(a.get("created_at",""),32), True, (100,100,100)), (r.x+8, r.y+28))
            y += item_h
        screen.set_clip(None)

    def list_click(pos):
        nonlocal selected_index, selected_article_id
        lx = PAD; ly = HDR+PAD; lh = H-ly-PAD
        panel = pygame.Rect(lx, ly, LIST_W, lh)
        inner = panel.inflate(-10,-10)
        if not panel.collidepoint(pos): return
        idx = int((pos[1] - inner.y + list_scroll) // 54)
        if 0 <= idx < len(articles):
            selected_index = idx
            selected_article_id = int(articles[idx]["id"])
            load_article_into_form(selected_article_id)

    def draw_categories():
        cx = W - PAD - CAT_W
        cy = HDR + PAD + LABEL_H  # pod popiskem "Kategorie" v hlavičce
        ch = H - cy - PAD
        panel = pygame.Rect(cx, cy, CAT_W, ch)
        pygame.draw.rect(screen, (255,255,255), panel, border_radius=12)
        pygame.draw.rect(screen, (200,200,200), panel, 1, border_radius=12)
        inner = pygame.Rect(cx+8, cy+8, CAT_W-16, ch-16)
        screen.set_clip(inner)
        item_h = 34; y = inner.y - cat_scroll
        for cat in all_categories:
            checked = cat["id"] in selected_cat_ids
            r = pygame.Rect(inner.x, y, inner.w, item_h-4)
            pygame.draw.rect(screen, (225,240,255) if checked else (248,248,248), r, border_radius=6)
            pygame.draw.rect(screen, (0,119,204) if checked else (220,220,220), r, 1, border_radius=6)
            cb = pygame.Rect(r.x+6, r.centery-7, 14, 14)
            pygame.draw.rect(screen, (255,255,255), cb)
            pygame.draw.rect(screen, (0,119,204) if checked else (180,180,180), cb, 2)
            if checked:
                pygame.draw.line(screen, (0,119,204), (cb.x+2,cb.centery),(cb.x+5,cb.bottom-3),2)
                pygame.draw.line(screen, (0,119,204), (cb.x+5,cb.bottom-3),(cb.right-1,cb.y+2),2)
            screen.blit(small.render(clip(cat["name"],18), True, (20,20,20)), (r.x+26, r.y+8))
            y += item_h
        screen.set_clip(None)

    def cat_click(pos):
        cx = W-PAD-CAT_W; cy = HDR+PAD+LABEL_H; ch = H-cy-PAD
        inner = pygame.Rect(cx+8, cy+8, CAT_W-16, ch-16)
        if not pygame.Rect(cx,cy,CAT_W,ch).collidepoint(pos): return
        idx = int((pos[1] - inner.y + cat_scroll) // 34)
        if 0 <= idx < len(all_categories):
            cid = all_categories[idx]["id"]
            if cid in selected_cat_ids: selected_cat_ids.discard(cid)
            else: selected_cat_ids.add(cid)

    # ── Focus ────────────────────────────────────────────────────────
    login_fields  = [login_user, login_pass]
    editor_fields = [title_box, perex_area, content_area]
    login_focus = 0; editor_focus = 0
    set_active(login_fields,  login_focus)
    set_active(editor_fields, editor_focus)

    # ── Hlavní smyčka ────────────────────────────────────────────────
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)

            if e.type == pygame.VIDEORESIZE:
                W, H = max(900, e.w), max(600, e.h)
                screen = pygame.display.set_mode((W,H), pygame.RESIZABLE)
                fx, fw, btn_y, stats_y = rebuild_layout()

            if e.type == pygame.KEYDOWN and e.key == pygame.K_TAB:
                backwards = bool(e.mod & pygame.KMOD_SHIFT)
                fields = login_fields if mode == "login" else editor_fields
                ref    = login_focus  if mode == "login" else editor_focus
                nxt    = (ref - 1) % len(fields) if backwards else (ref + 1) % len(fields)
                if mode == "login": login_focus = nxt
                else:               editor_focus = nxt
                set_active(fields, nxt)
                continue

            if mode == "login":
                login_user.handle_event(e)
                login_pass.handle_event(e)

                if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                    u = login_user.text.strip(); p = login_pass.text
                    if u and p:
                        d = api_login_call(u, p)
                        if not d.get("ok"):
                            toast.show(d.get("error","Přihlášení selhalo."))
                        elif d.get("role") not in ("admin","editor"):
                            toast.show(f"Role '{d.get('role')}' nemá přístup.")
                        else:
                            token = d["token"]; my_role = d["role"]; my_username = d["username"]
                            mode = "editor"
                            toast.show(f"Přihlášen: {my_username} ({my_role})")
                            refresh_articles(); fetch_categories()
                            editor_focus = 0; set_active(editor_fields, editor_focus)

                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    if btn_login.hit(e.pos):
                        u = login_user.text.strip(); p = login_pass.text
                        if not u or not p:
                            toast.show("Vyplň přihlašovací údaje.")
                        else:
                            d = api_login_call(u, p)
                            if not d.get("ok"):
                                toast.show(d.get("error","Přihlášení selhalo."))
                            elif d.get("role") not in ("admin","editor"):
                                toast.show(f"Role '{d.get('role')}' nemá přístup.")
                            else:
                                token = d["token"]; my_role = d["role"]; my_username = d["username"]
                                mode = "editor"
                                toast.show(f"Přihlášen: {my_username} ({my_role})")
                                refresh_articles(); fetch_categories()
                                editor_focus = 0; set_active(editor_fields, editor_focus)
                    if btn_quit.hit(e.pos):
                        pygame.quit(); sys.exit(0)

            else:  # editor mode
                title_box.handle_event(e)
                perex_area.handle_event(e)
                content_area.handle_event(e)

                if e.type == pygame.MOUSEWHEEL:
                    mp = pygame.mouse.get_pos()
                    lx = PAD; ly = HDR+PAD; lh = H-ly-PAD
                    if pygame.Rect(lx,ly,LIST_W,lh).collidepoint(mp):
                        list_scroll = max(0, list_scroll - e.y*40)
                    elif pygame.Rect(W-PAD-CAT_W, HDR+PAD+LABEL_H, CAT_W, H-HDR-PAD*2).collidepoint(mp):
                        cat_scroll = max(0, cat_scroll - e.y*34)

                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    # MD toolbar
                    for i, mb in enumerate(md_btns):
                        if mb.hit(e.pos):
                            content_area.insert_at_cursor(md_snippets[i])
                            content_area.active = True
                            editor_focus = 2; set_active(editor_fields, editor_focus)

                    if btn_new.hit(e.pos):
                        clear_form()
                        toast.show("Nový článek – vyplň a dej Uložit.")
                        editor_focus = 0; set_active(editor_fields, editor_focus)

                    elif btn_save.hit(e.pos):
                        t   = (title_box.text or "").strip()
                        per = (perex_area.text or "").strip()
                        con = (content_area.text or "").strip()
                        if not t or not con:
                            toast.show("Titulek a obsah jsou povinné.")
                        else:
                            cat_ids = list(selected_cat_ids)
                            if selected_article_id is None:
                                d = api_create_article_call(t, per, con, cat_ids)
                                if d.get("ok"): toast.show(f"Vytvořeno (id {d.get('id')})."); refresh_articles()
                                else: toast.show(d.get("error","Chyba vytvoření."))
                            else:
                                d = api_update_article_call(selected_article_id, t, per, con, cat_ids)
                                if d.get("ok"): toast.show("Uloženo."); refresh_articles()
                                else: toast.show(d.get("error","Chyba uložení."))

                    elif btn_delete.hit(e.pos):
                        if selected_article_id is None:
                            toast.show("Nejdřív vyber článek.")
                        else:
                            d = api_delete_article_call(selected_article_id)
                            if d.get("ok"): toast.show("Smazáno."); clear_form(); refresh_articles()
                            else: toast.show(d.get("error","Chyba mazání."))

                    elif btn_upload_img.hit(e.pos):
                        root = tk.Tk(); root.withdraw()
                        fp = filedialog.askopenfilename(title="Vyber obrázek",
                            filetypes=[("Images","*.png;*.jpg;*.jpeg;*.webp;*.gif"),("All","*.*")])
                        root.destroy()
                        if fp:
                            up = api_upload_image_call(fp)
                            if up.get("ok"):
                                content_area.insert_at_cursor(f'<p><img src="{up["url"]}" alt=""></p>\n')
                                toast.show("Obrázek nahrán.")
                            else:
                                toast.show(up.get("error","Upload selhal."))

                    elif btn_logout.hit(e.pos):
                        token = None; my_role = None; my_username = None
                        mode = "login"; clear_form(); articles = []
                        selected_index = -1; selected_article_id = None
                        toast.show("Odhlášeno.")
                        login_focus = 0; set_active(login_fields, login_focus)

                    else:
                        list_click(e.pos)
                        cat_click(e.pos)
                        if title_box.rect.collidepoint(e.pos):
                            editor_focus = 0; set_active(editor_fields, editor_focus)
                        elif perex_area.rect.collidepoint(e.pos):
                            editor_focus = 1; set_active(editor_fields, editor_focus)
                        elif content_area.rect.collidepoint(e.pos):
                            editor_focus = 2; set_active(editor_fields, editor_focus)

        # ── Draw ─────────────────────────────────────────────────────
        screen.fill(BG)

        if mode == "login":
            # Hlavička
            pygame.draw.rect(screen, (255,255,255), (0,0,W,HDR))
            pygame.draw.line(screen, (220,220,220), (0,HDR),(W,HDR), 1)
            screen.blit(big.render("InfoBox – Editor", True, (10,10,10)), (PAD,14))

            # Login karta
            card = pygame.Rect(W//2-200, H//2-140, 400, 280)
            pygame.draw.rect(screen, (255,255,255), card, border_radius=14)
            pygame.draw.rect(screen, (220,220,220), card, 1, border_radius=14)
            screen.blit(small.render("Přihlášení (pouze admin / editor)", True, (100,100,100)),
                        (card.x+20, card.y+16))
            login_user.draw(screen, font, small)
            login_pass.draw(screen, font, small)
            btn_login.draw(screen, font)
            btn_quit.draw(screen, font)

        else:
            # Hlavička
            pygame.draw.rect(screen, (255,255,255), (0,0,W,HDR))
            pygame.draw.line(screen, (220,220,220), (0,HDR),(W,HDR), 1)
            screen.blit(big.render("InfoBox – Editor článků", True, (10,10,10)), (PAD, 14))
            if my_username:
                who = small.render(f"{my_username}  •  {my_role}", True, (100,100,100))
                screen.blit(who, (PAD + LIST_W + PAD + 160, (HDR - who.get_height())//2))
            btn_new.draw(screen, font)
            btn_logout.draw(screen, font)

            # Popisky sloupců v hlavičce (pod čárou, nad obsahem)
            screen.blit(small.render("Články", True, (80,80,80)),
                        (PAD, HDR + 4))
            screen.blit(small.render("Kategorie", True, (80,80,80)),
                        (W - PAD - CAT_W, HDR + 4))

            # Seznam článků
            draw_list()

            # Formulář
            screen.blit(small.render("Titulek", True, (80,80,80)),
                        (fx, title_box.rect.y - LABEL_H))
            title_box.draw(screen, font, small)

            screen.blit(small.render("Shrnutí", True, (80,80,80)),
                        (fx, perex_area.rect.y - LABEL_H))
            perex_area.draw(screen, font, small)

            # MD toolbar — popisek inline vlevo, tlačítka za ním
            md_label_surf = small.render("Markdown:", True, (100,100,100))
            screen.blit(md_label_surf, (fx, md_btns[0].rect.y + 5))
            md_x = fx + md_label_surf.get_width() + 8
            for mb in md_btns:
                mb.rect.x = md_x
                md_x += mb.rect.width + 5
                mb.draw(screen, small)

            screen.blit(small.render("Obsah", True, (80,80,80)),
                        (fx, content_area.rect.y - LABEL_H))
            content_area.draw(screen, font, small)

            btn_save.draw(screen, font)
            btn_delete.draw(screen, font)
            btn_upload_img.draw(screen, font)

            # Statistiky (vždy viditelné dole, i bez vybraného článku)
            if selected_article_id is not None:
                sx = fx
                for txt, col in [
                    (f"Zobrazení: {current_stats.get('views', 0)}", (60,60,60)),
                    (f"Lajků: {current_stats.get('likes', 0)}",     (180,40,40)),
                    (f"Komentářů: {current_stats.get('comments', 0)}", (40,90,180)),
                ]:
                    s = small.render(txt, True, col)
                    screen.blit(s, (sx, stats_y + (STATS_H - s.get_height())//2))
                    sx += s.get_width() + 28
            else:
                hint = small.render("Vyber článek pro zobrazení statistik", True, (180,180,180))
                screen.blit(hint, (fx, stats_y + (STATS_H - hint.get_height())//2))

            # Kategorie panel (bez duplicitního popisku uvnitř)
            draw_categories()

        toast.draw(screen, font, W)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()