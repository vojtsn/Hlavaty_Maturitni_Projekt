# InfoBox

Projekt běží v Pythonu 3.10 a novějším.  
Knihovny viz `requirements.txt`.

## Složení projektu

Projekt se skládá ze 3 primárních Python programů:

1. `app.py`  
2. `admin_app.py`  
3. `editor_app.py`  

*(Programy mohou běžet nezávisle na sobě. Hlavní je `app.py`, zbytek není pro běžného uživatele nutný.)*

---

## Databázové tabulky

Projekt využívá následující tabulky na serveru `dbs.spskladno.cz` v databázi `/VYUKA11`:

- `users`  
- `articles`  
- `api_tokens`  
- `article_likes`  
- `comments`  
- `comment_likes`  
- `comment_replies`  
- `comment_reply_likes`  
- `user_follows`  
- `categories`  
- `article_categories`  

---

## Role uživatelů

Uživatelé mohou mít jednu ze 4 rolí:

- **USER** – může sledovat a být sledován, lajkovat články a komentáře, psát komentáře  
- **EDITOR** – nad rámec oprávnění role USER může vytvářet a měnit své články  
- **MODERATOR** – nemůže vytvářet články, ale může mazat komentáře a články editorů  
- **ADMIN** – všechna oprávnění; tuto roli lze získat pouze ručně v tabulce `users`  

---

## Popis aplikací

### `app.py`  
Webová stránka InfoBox pro běžné uživatele (jediná stránka, na kterou mají přístup).  
Adresa: `127.0.0.1:5000`

- Uživatel si může vytvořit profil, zadat informace o sobě a vybrat profilový obrázek  
- Nepřihlášený uživatel může pouze prohlížet články  
- Přihlášený uživatel viz role USER  
- Funkční vyhledávání článků nebo uživatelů (např. hledání "adm" najde uživatele "ADMINISTRÁTOR")  

### `admin_app.py`  
Webová stránka pro administrátory. Přístup přes `/admin/login`.  
Adresa: `127.0.0.1:5001`

- Slouží pro reset hesla uživatele  
- Lze vytvářet a upravovat kategorie  
- Lze měnit role uživatelů (kromě role admina)  

### `editor_app.py`  
Aplikace napsaná v PyQt5 pro editory.  

- Přihlásit se mohou jen uživatelé s rolí admin nebo editor  
- Editoři nemohou měnit články adminů, admini mohou upravovat všechny  
- Lze nahrávat obsah textových souborů `.txt`