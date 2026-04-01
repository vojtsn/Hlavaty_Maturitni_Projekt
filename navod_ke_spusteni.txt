Běží v pythonu 3.10 a novějším
Knihovny viz requirements.txt

Tento projekt se skládá ze 3 primárních python programů:
1. app.py
2. admin_app.py
3. editor_app.py
(programy mohou běžet nezávisle na sobě, hlavní je ale app.py, zbytek není pro běžného uživatele nutný)

Projekt využívá následující tabulky na serveru dbs.spskladno.cz:
/VYUKA11:
users
articles
api_tokens
article_likes
comments
comment_likes
comment_replies
comment_reply_likes
user_follows
categories
article_categories

Uživatelé mohou mít jednu ze 4 rolí:
- USER - uživatel může sledovat a být sledován na profilu, lajkovat články a komentáře a psát komentáře
- EDITOR - nad rámec oprávnění role USER může vytvářet a měnit své články
- MODERATOR - nemůže vytvářet články, ale může mazat komentáře a články editorů
- ADMIN - všechna oprávnění. Tuto roli lze získat pouze ručním nastavením role u uživatele v tabulce "users" v databázi (vyuka11)

    app.py je webová stránka InfoBox - tuto stránku využívá běžný uživatel a je to taky jediná stránka na kterou má přístup
        tato aplikace běží na adrese 127.0.0.1:5000
        - uživatel si může vytvořit profil, zadat informace o sobě a vybrat si profilový obrázek
        - nepřihlášený uživatel může pouze prohlížet články
        - přihlášený uživatel viz role USER
        - funkční vyhledávání článků nebo uživatelů (např. vyhledávání "adm" vyhledá uživatele "ADMINISTRÁTOR")

    admin_app.py je také webová stránka, ale přihlašuje se do ní pouze účet admina. defaultně se stránka nezobrazuje, pro přístup k přihlášení musí uživatel na konec url adresy zadat /admin/login
        tato aplikace běží na adrese 127.0.0.1:5001
        - slouží pro reset hesla uživatele
        - lze skrz ní vytvářet kategorie a upravovat je
        - lze zde měnit role uživatelů, kromě role admina

    editor_app.py: aplikace napsaná v PyQt5 - funguje jako prostředí pro editory, kteří zde mohou různě pracovat s články.
        - do aplikace se dá přihlásit pouze pod účtem s rolí admin nebo editor
        - editoři nemohou dělat změny v článcích napsaných uživateli s rolí admin, ale admini mohou pozměňovat všechny články.
        - lze nahrávat obsah textových souborů .txt
