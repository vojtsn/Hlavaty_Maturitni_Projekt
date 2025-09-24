from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tajny_klic'  # změň na vlastní

# --- Uživatelská data napevno ---
USERS = {
    "admin": "admin123",
    "ctenar": "heslo"
}

# Homepage
@app.route('/')
def index():
    username = session.get('username')
    return render_template('index.html', username=username)

# Přihlášení
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS and USERS[username] == password:
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = "Špatné jméno nebo heslo."
    return render_template('login.html', error=error)

# Odhlášení
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
