import pygame
import requests

API_BASE = "http://127.0.0.1:5000"

pygame.init()
screen = pygame.display.set_mode((900, 650))
pygame.display.set_caption("InfoBox – Editor")
font = pygame.font.SysFont("arial", 20)
small = pygame.font.SysFont("arial", 16)
clock = pygame.time.Clock()

# ---------- UI prvky ----------

class InputBox:
    def __init__(self, x, y, w, h, label="", multiline=False, password=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.multiline = multiline
        self.password = password
        self.text = ""
        self.active = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)

        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN and self.multiline:
                self.text += "\n"
            else:
                if event.unicode and ord(event.unicode) >= 32:
                    self.text += event.unicode

    def draw(self, surf):
        if self.label:
            surf.blit(small.render(self.label, True, (30,30,30)),
                      (self.rect.x, self.rect.y - 18))

        pygame.draw.rect(surf, (255,255,255), self.rect, border_radius=6)
        pygame.draw.rect(
            surf,
            (0,119,204) if self.active else (150,150,150),
            self.rect,
            2,
            border_radius=6
        )

        shown = "*" * len(self.text) if self.password else self.text
        y = self.rect.y + 8

        if self.multiline:
            for line in shown.split("\n")[-8:]:
                surf.blit(small.render(line, True, (0,0,0)),
                          (self.rect.x + 8, y))
                y += 18
        else:
            surf.blit(small.render(shown[-50:], True, (0,0,0)),
                      (self.rect.x + 8, self.rect.y + 10))


class Button:
    def __init__(self, x, y, w, h, text):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text

    def draw(self, surf):
        pygame.draw.rect(surf, (0,119,204), self.rect, border_radius=8)
        surf.blit(font.render(self.text, True, (255,255,255)),
                  (self.rect.x + 12, self.rect.y + 10))

    def clicked(self, event):
        return event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos)


# ---------- API funkce ----------

def api_login(username, password):
    r = requests.post(
        f"{API_BASE}/api/login",
        json={"username": username, "password": password},
        timeout=10
    )
    return r.json(), r.status_code


def api_add_article(token, title, perex, content):
    r = requests.post(
        f"{API_BASE}/api/articles",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": title, "perex": perex, "content": content},
        timeout=10
    )
    return r.json(), r.status_code


# ---------- UI ----------

login_user = InputBox(40, 60, 300, 40, "Uživatelské jméno")
login_pass = InputBox(40, 130, 300, 40, "Heslo", password=True)
btn_login = Button(40, 190, 160, 44, "Přihlásit")

title_box = InputBox(40, 300, 820, 40, "Nadpis")
perex_box = InputBox(40, 370, 820, 60, "Perex", multiline=True)
content_box = InputBox(40, 460, 820, 140, "Obsah článku", multiline=True)
btn_send = Button(40, 610, 220, 44, "Odeslat článek")

token = None
status = "Nepřihlášen."

# ---------- Hlavní smyčka ----------

running = True
while running:
    screen.fill((245,248,252))
    screen.blit(font.render("InfoBox – Redakční aplikace", True, (0,0,0)), (40, 20))
    screen.blit(small.render("Stav: " + status, True, (0,0,0)), (40, 250))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        login_user.handle_event(event)
        login_pass.handle_event(event)
        title_box.handle_event(event)
        perex_box.handle_event(event)
        content_box.handle_event(event)

        if btn_login.clicked(event):
            data, code = api_login(login_user.text, login_pass.text)
            if code == 200:
                token = data["token"]
                status = f"Přihlášen jako {data['username']} ({data['role']})"
            else:
                status = data.get("error", "Chyba přihlášení")

        if btn_send.clicked(event):
            if not token:
                status = "Nejprve se přihlas"
            else:
                data, code = api_add_article(
                    token,
                    title_box.text,
                    perex_box.text,
                    content_box.text
                )
                if code == 200:
                    status = "Článek uložen ✔"
                    title_box.text = perex_box.text = content_box.text = ""
                else:
                    status = data.get("error", "Chyba")

    login_user.draw(screen)
    login_pass.draw(screen)
    btn_login.draw(screen)

    title_box.draw(screen)
    perex_box.draw(screen)
    content_box.draw(screen)
    btn_send.draw(screen)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
