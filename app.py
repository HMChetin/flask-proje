from flask_babel import Babel, _
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.utils import secure_filename
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sqlite3
import openpyxl

app = Flask(__name__)
# Uygulama kök dizinine göre upload klasörü
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')  # veya 'static/uploads' da olabilir

# Upload klasörü varsa oluştur
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'gizli_anahtar'

# Desteklenen diller
app.config['BABEL_DEFAULT_LOCALE'] = 'tr'  # varsayılan dil
app.config['BABEL_SUPPORTED_LOCALES'] = ['tr', 'en']

babel = Babel(app)

@babel.localeselector
def get_locale():
    # Önce URL parametresine bak
    lang = request.args.get('lang')

    if lang:
        session['lang'] = lang  # seçilen dili session'a yaz

    # Sonra session'dan getir
    return session.get('lang', app.config['BABEL_DEFAULT_LOCALE'])

@app.route('/set_language/<lang>')
def set_language(lang):
    session['lang'] = lang
    return redirect(request.referrer or url_for('index'))  # önceki sayfaya döner


# Veritabanını başlat
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS charts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            x_col TEXT,
            y_col TEXT,
            chart_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()


@app.route('/')
def home():
    return redirect(url_for('upload_file'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
        except sqlite3.IntegrityError:
            flash(_("Bu kullanıcı adı zaten kayıtlı!"), "danger")
            return redirect(url_for('register'))
        finally:
            conn.close()
        flash(_("Kayıt başarılı. Giriş yapabilirsiniz."), "success")
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username=? AND password=?', (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session['username'] = username
            return redirect(url_for('upload_file'))
        else:
            flash(_("Kullanıcı adı veya şifre hatalı!"), "danger")
            return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        ALLOWED_EXTENSIONS = ('.csv', '.xlsx')
        if file and file.filename.endswith(ALLOWED_EXTENSIONS):
            filename = secure_filename(file.filename)
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Dosya ve sütun bilgilerini session'a yaz
            session['uploaded_file'] = filepath

            if file.filename.endswith('.csv'):
                df = pd.read_csv(filepath)
            elif file.filename.endswith('.xlsx'):
                df = pd.read_excel(filepath, engine='openpyxl')
            else:
                flash(_("Desteklenmeyen dosya biçimi."), "danger")
                return redirect(request.url)

            session['columns'] = df.columns.tolist()

            return redirect(url_for('select'))
        else:
            flash(_("Lütfen geçerli bir CSV dosyası yükleyin."), "warning")
            return redirect(request.url)

    return render_template('upload.html')


@app.route('/select', methods=["GET", "POST"])
def select():
    filepath = session.get('uploaded_file')
    columns = session.get('columns')

    if not filepath or not os.path.exists(filepath):
        flash(_("Geçerli bir dosya yüklemeniz gerekiyor."), "warning")
        return redirect(url_for('upload_file'))

    # Veri dosyasını oku
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        elif filepath.endswith('.xlsx'):
            df = pd.read_excel(filepath, engine='openpyxl')
        else:
            flash(_("Desteklenmeyen dosya biçimi."), "danger")
            return redirect(url_for('upload_file'))
    except Exception as e:
        flash(_(f"Dosya okunurken hata oluştu: {e}"), "danger")
        return redirect(url_for('upload_file'))

    plot_generated = False

    if request.method == 'POST':
        x = request.form.get("x_column")
        y = request.form.get("y_column")
        chart = request.form.get("chart_type")
        color = request.form.get("color") or 'blue'
        title = request.form.get("title") or f'{chart.capitalize()} Chart of {y} vs {x}'
        show_grid = request.form.get("show_grid") == "on"

        if not x or not y or not chart:
            flash(_("Tüm alanları doldurmanız gerekiyor."), "warning")
        elif x not in df.columns or y not in df.columns:
            flash(_("Seçilen sütunlar veride bulunamadı."), "danger")
        else:
            try:
                # Geniş grafik alanı ve çözüm odaklı yapı
                fig, ax = plt.subplots(figsize=(10, 6))

                # Grafik türüne göre çizim
                if chart == 'line':
                    ax.plot(df[x], df[y], color=color)
                elif chart == 'bar':
                    ax.bar(df[x], df[y], color=color)
                elif chart == 'scatter':
                    ax.scatter(df[x], df[y], color=color)
                else:
                    flash(_("Geçersiz grafik türü."), "danger")
                    return redirect(url_for('select'))

                # Ekseni etiketle
                ax.set_xlabel(x)
                ax.set_ylabel(y)
                ax.set_title(title)
                ax.grid(show_grid)

                # X ekseni çok kalabalıksa etiketi döndür
                if df[x].dtype == object or df[x].nunique() > 10:
                    ax.tick_params(axis='x', labelrotation=90)

                # Otomatik alan yerleşimi
                fig.tight_layout()

                # Grafik dosyasını kaydet
                if not os.path.exists('static'):
                    os.makedirs('static')
                plot_path = os.path.join('static', 'plot.png')
                fig.savefig(plot_path)
                plt.close()

                # Grafik bilgilerini veritabanına kaydet
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('INSERT INTO charts (username, x_col, y_col, chart_type) VALUES (?, ?, ?, ?)',
                          (session['username'], x, y, chart))
                conn.commit()
                conn.close()

                plot_generated = True
                flash(_("Grafik başarıyla oluşturuldu."), "success")

            except Exception as e:
                print("Grafik çizim hatası:", e)
                flash(_(f"Grafik çizimi sırasında hata oluştu: {e}"), "danger")

    return render_template("select.html", columns=columns, plot_generated=plot_generated)



@app.route('/history')
def history():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT x_col, y_col, chart_type, timestamp FROM charts WHERE username = ? ORDER BY timestamp DESC',
              (session['username'],))
    records = c.fetchall()
    conn.close()

    return render_template('history.html', records=records)


@app.route('/download')
def download():
    path = os.path.join('static', 'plot.png')
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    flash(_("Grafik dosyası bulunamadı."), "danger")
    return redirect(url_for('select'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    uploaded_file = session.get('uploaded_file', None)

    # Grafik sayısını veritabanından al
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM charts WHERE username = ?', (username,))
    chart_count = c.fetchone()[0]
    conn.close()

    return render_template('dashboard.html', username=username, uploaded_file=uploaded_file, chart_count=chart_count)



if __name__ == '__main__':
    app.run(debug=True)
