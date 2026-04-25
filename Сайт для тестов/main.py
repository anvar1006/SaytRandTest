import os
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from fpdf import FPDF
import threading
import webbrowser

app = Flask(__name__)
# Секретный ключ для сессий (в реальном проекте должен быть защищен)
app.config['SECRET_KEY'] = 'super-secret-key-change-it'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test_system.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Пожалуйста, войдите для доступа к этой странице."

# Защита от подбора пароля (Brute-force protection)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

# --- МОДЕЛИ БАЗЫ ДАННЫХ ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(255), nullable=False)
    wrong_answer_1 = db.Column(db.String(255), nullable=False)
    wrong_answer_2 = db.Column(db.String(255), nullable=False)
    wrong_answer_3 = db.Column(db.String(255), nullable=False)
    fix_a = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def init_db():
    """Инициализация базы данных и создание администратора по умолчанию"""
    with app.app_context():
        db.create_all()
        # Если пользователя admin нет, создаем его
        if not User.query.filter_by(username='admin').first():
            hashed_password = generate_password_hash('password123', method='pbkdf2:sha256')
            admin_user = User(username='admin', password_hash=hashed_password)
            db.session.add(admin_user)
            db.session.commit()
            print("Создан пользователь по умолчанию: логин 'admin', пароль 'password123'")

# Вызываем инициализацию базы данных при запуске приложения
init_db()

# --- МАРШРУТЫ (ROUTES) ---

@app.route('/')
def index():
    """Перенаправление на панель управления или вход"""
    return redirect(url_for('admin'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute") # Ограничение: 5 попыток в минуту (защита от брутфорса)
def login():
    """Страница входа для учителя"""
    if current_user.is_authenticated:
        return redirect(url_for('admin'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Успешный вход!', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Неверное имя пользователя или пароль.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Выход из аккаунта"""
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    """Панель управления (список вопросов)"""
    questions = Question.query.all()
    return render_template('admin.html', questions=questions)

@app.route('/admin/add', methods=['GET', 'POST'])
@login_required
def add_question():
    """Добавление нового вопроса"""
    if request.method == 'POST':
        text = request.form.get('text')
        ans1 = request.form.get('answer_1')
        ans2 = request.form.get('answer_2')
        ans3 = request.form.get('answer_3')
        ans4 = request.form.get('answer_4')
        correct_idx = int(request.form.get('correct_option', 1))
        
        answers = [ans1, ans2, ans3, ans4]
        correct = answers[correct_idx - 1]
        wrong = [a for i, a in enumerate(answers) if i != (correct_idx - 1)]
        
        new_q = Question(text=text, correct_answer=correct, 
                         wrong_answer_1=wrong[0], wrong_answer_2=wrong[1], wrong_answer_3=wrong[2])
        db.session.add(new_q)
        db.session.commit()
        flash('Вопрос добавлен!', 'success')
        return redirect(url_for('admin'))
        
    return render_template('question_form.html', action='Добавить')

@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_question(id):
    """Редактирование существующего вопроса"""
    q = Question.query.get_or_404(id)
    if request.method == 'POST':
        q.text = request.form.get('text')
        ans1 = request.form.get('answer_1')
        ans2 = request.form.get('answer_2')
        ans3 = request.form.get('answer_3')
        ans4 = request.form.get('answer_4')
        correct_idx = int(request.form.get('correct_option', 1))
        
        answers = [ans1, ans2, ans3, ans4]
        q.correct_answer = answers[correct_idx - 1]
        wrong = [a for i, a in enumerate(answers) if i != (correct_idx - 1)]
        q.wrong_answer_1 = wrong[0]
        q.wrong_answer_2 = wrong[1]
        q.wrong_answer_3 = wrong[2]
        
        db.session.commit()
        flash('Вопрос обновлен!', 'success')
        return redirect(url_for('admin'))
        
    return render_template('question_form.html', action='Редактировать', q=q)

@app.route('/admin/delete/<int:id>', methods=['POST'])
@login_required
def delete_question(id):
    """Удаление вопроса"""
    q = Question.query.get_or_404(id)
    db.session.delete(q)
    db.session.commit()
    flash('Вопрос удален!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/export', methods=['GET', 'POST'])
@login_required
def export_pdf():
    """Экспорт варианта теста в PDF"""
    pdf_title = request.form.get('pdf_title', "Вариант теста") if request.method == 'POST' else "Вариант теста"
    try:
        num_variants = int(request.form.get('num_variants', 1))
    except ValueError:
        num_variants = 1
        
    questions = Question.query.all()
    if not questions:
        flash('Нет вопросов для экспорта', 'warning')
        return redirect(url_for('admin'))

    pdf = FPDF()
    
    # Пути к шрифтам (теперь берем из папки fonts внутри проекта для совместимости с Mac/Linux)
    base_dir = os.path.dirname(__file__)
    font_path = os.path.join(base_dir, "fonts", "arial.ttf")
    font_bold_path = os.path.join(base_dir, "fonts", "arialbd.ttf")
    has_font = os.path.exists(font_path)
    
    # Собираем правильные ответы (ключи)
    all_keys = []
    
    for variant in range(1, num_variants + 1):
        pdf.add_page()
        
        if has_font:
            pdf.add_font("Arial", style="", fname=font_path)
            if os.path.exists(font_bold_path):
                pdf.add_font("Arial", style="B", fname=font_bold_path)
            pdf.set_font("Arial", style="B", size=16)
        else:
            pdf.set_font("helvetica", style="B", size=16)
            
        pdf.multi_cell(0, 10, txt=f"{pdf_title}\nВариант {variant}", align='C')
        pdf.ln(10)
        
        if has_font:
            pdf.set_font("Arial", size=12)
        else:
            pdf.set_font("helvetica", size=12)
        
        # Перемешиваем вопросы для каждого варианта
        random.shuffle(questions)
        
        variant_keys = []
        
        for i, q in enumerate(questions, 1):
            # Текст вопроса
            pdf.set_x(10)
            pdf.multi_cell(0, 10, txt=f"{i}. {q.text}", new_x="LMARGIN", new_y="NEXT")
            
            answers = [
                {'text': q.correct_answer, 'is_correct': True},
                {'text': q.wrong_answer_1, 'is_correct': False},
                {'text': q.wrong_answer_2, 'is_correct': False},
                {'text': q.wrong_answer_3, 'is_correct': False}
            ]
            
            random.shuffle(answers)
            shuffled_answers = answers
                
            prefixes = ['A', 'B', 'C', 'D']
            correct_letter = 'A'
            answers_text_parts = []
            for j, ans in enumerate(shuffled_answers):
                ans_clean = ans['text'].replace('\r', '').replace('\n', ' ').strip()
                answers_text_parts.append(f"{prefixes[j]}) {ans_clean}")
                if ans['is_correct']:
                    correct_letter = prefixes[j]
                    
            pdf.set_x(15) # Отступ для вариантов
            pdf.multi_cell(0, 8, txt="   ".join(answers_text_parts), new_x="LMARGIN", new_y="NEXT")
                    
            variant_keys.append((i, correct_letter))
            pdf.ln(5)
            
        all_keys.append(variant_keys)
        
    # Печатаем ключи в конце
    pdf.add_page()
    if has_font:
        pdf.set_font("Arial", style="B", size=16)
    else:
        pdf.set_font("helvetica", style="B", size=16)
    pdf.cell(0, 10, txt="Ключи (Правильные ответы)", align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    if has_font:
        pdf.set_font("Arial", size=12)
    else:
        pdf.set_font("helvetica", size=12)
        
    for variant, keys in enumerate(all_keys, 1):
        if has_font:
            pdf.set_font("Arial", style="B", size=14)
        else:
            pdf.set_font("helvetica", style="B", size=14)
        pdf.cell(0, 8, txt=f"Вариант {variant}:", new_x="LMARGIN", new_y="NEXT")
        
        if has_font:
            pdf.set_font("Arial", size=12)
        else:
            pdf.set_font("helvetica", size=12)
            
        # Группируем ответы по строкам (по 5 штук)
        key_strings = [f"{k[0]}-{k[1]}" for k in keys]
        for i in range(0, len(key_strings), 5):
            pdf.cell(0, 8, txt="   " + "   ".join(key_strings[i:i+5]), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        
    export_path = os.path.join(os.path.dirname(__file__), "test_variant.pdf")
    pdf.output(export_path)
    
    filename = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(export_path, as_attachment=True, download_name=filename)

def open_browser():
    webbrowser.open("http://127.0.0.1:5001/")

if __name__ == '__main__':
    # Открываем браузер через 1 секунду после старта сервера
    threading.Timer(1.0, open_browser).start()
    # debug=False чтобы сервер не перезапускался дважды
    app.run(debug=False, port=5001)

