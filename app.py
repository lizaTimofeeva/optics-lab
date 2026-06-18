import json
import os
import random
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, session, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'optics-lab-secret-key-2025')

DATABASE_URL = os.environ.get('DATABASE_URL', '')


@app.template_filter('from_json')
def from_json_filter(s):
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def query_db(sql, args=(), one=False, commit=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, args)
    if commit:
        conn.commit()
        try:
            rv = cur.fetchone()
        except Exception:
            rv = None
        cur.close()
        conn.close()
        return rv
    rv = cur.fetchall()
    cur.close()
    conn.close()
    return (rv[0] if rv else None) if one else rv


def generate_task_params():
    """Генерирует уникальные случайные данные для 5 задач по оптике.
    У каждого студента будут свои числа."""
    params = {}

    # Задача 1: Найти f = L - d
    L1 = random.choice([0.400, 0.420, 0.440, 0.460, 0.480, 0.500, 0.520, 0.550])
    d1_opts = [x for x in [0.200, 0.220, 0.250, 0.270, 0.280, 0.300, 0.320, 0.350]
               if x < L1 - 0.05]
    d1 = random.choice(d1_opts) if d1_opts else 0.200
    params['1'] = {'L': L1, 'd': d1,
                   'answer': round(L1 - d1, 3), 'tolerance': 0.005}

    # Задача 2: Найти D = 1/F
    F2 = random.choice([0.10, 0.20, 0.25, 0.40, 0.50])
    params['2'] = {'F': F2,
                   'answer': round(1 / F2, 2), 'tolerance': 0.1}

    # Задача 3: Найти F = df/(d+f), округлить до сотых
    d3 = random.choice([0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30])
    f3 = random.choice([0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50])
    params['3'] = {'d': d3, 'f': f3,
                   'answer': round((d3 * f3) / (d3 + f3), 2), 'tolerance': 0.01}

    # Задача 4: Найти Г = f/d
    d4 = random.choice([0.10, 0.12, 0.15, 0.18, 0.20, 0.25])
    f4 = random.choice([0.30, 0.36, 0.40, 0.45, 0.50, 0.60])
    params['4'] = {'d': d4, 'f': f4,
                   'answer': round(f4 / d4, 2), 'tolerance': 0.1}

    # Задача 5: Найти D, где f = L - d
    L5 = random.choice([0.400, 0.450, 0.500, 0.550, 0.600])
    d5_opts = [x for x in [0.150, 0.160, 0.170, 0.180, 0.200, 0.220, 0.250]
               if x < L5 - 0.10]
    d5 = random.choice(d5_opts) if d5_opts else 0.150
    f5 = round(L5 - d5, 3)
    F5 = (d5 * f5) / (d5 + f5)
    params['5'] = {'L': L5, 'd': d5,
                   'answer': round(1 / F5, 2), 'tolerance': 0.15}

    return params


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS teachers (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        password TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        grp TEXT NOT NULL,
        d_value REAL,
        lab_data TEXT,
        test_score INTEGER,
        test_answers TEXT,
        task_results TEXT,
        task_params TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    )""")
    # Миграция: добавить task_params если колонки нет
    try:
        cur.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS task_params TEXT")
    except Exception:
        conn.rollback()
    cur.execute('SELECT COUNT(*) FROM teachers')
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO teachers (name, password) VALUES (%s, %s)",
                     ('Валентина Семеновна', 'admin'))
    conn.commit()
    cur.close()
    conn.close()


init_db()


def calculate(d):
    f = 0.450 - d
    if f <= 0 or d <= 0:
        return None
    inv_d = 1 / d
    inv_f = 1 / f
    inv_F = inv_d + inv_f
    F = 1 / inv_F
    D = 1 / F
    G = f / d
    steps = {
        'f': 'f = 0,450 − {} = {} м'.format(d, round(f, 4)),
        'F': '1/F = 1/{} + 1/{} = {} + {} = {} → F = {} м'.format(
            d, round(f, 4), round(inv_d, 4), round(inv_f, 4),
            round(inv_F, 4), round(F, 4)),
        'D': 'D = 1 / {} = {} дптр'.format(round(F, 4), round(D, 2)),
        'G': 'Г = {} / {} = {}'.format(round(f, 4), d, round(G, 4))
    }
    return {
        'd': round(d, 4), 'f': round(f, 4), 'F': round(F, 4),
        'D': round(D, 2), 'G': round(G, 4),
        'd_gt_F': d > F, 'steps': steps
    }


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role', 'student')
        if role == 'teacher':
            password = request.form.get('password', '').strip()
            if not password:
                return render_template('login.html', error='Введите пароль')
            teacher = query_db('SELECT * FROM teachers WHERE password = %s',
                               (password,), one=True)
            if teacher:
                session['role'] = 'teacher'
                session['name'] = teacher['name']
                session['teacher_id'] = teacher['id']
                return redirect('/teacher')
            else:
                return render_template('login.html', error='Неверный пароль')
        else:
            name = request.form.get('name', '').strip()
            group = request.form.get('group', '').strip()
            if not name or not group:
                return render_template('login.html', error='Заполните все поля')
            session['role'] = 'student'
            session['name'] = name
            session['group'] = group
            existing = query_db(
                'SELECT id, task_params FROM students WHERE name = %s AND grp = %s',
                (name, group), one=True)
            if existing:
                session['student_id'] = existing['id']
                # Генерируем задачи если ещё нет
                if not existing.get('task_params'):
                    params = generate_task_params()
                    query_db('UPDATE students SET task_params = %s WHERE id = %s',
                             (json.dumps(params), existing['id']), commit=True)
            else:
                params = generate_task_params()
                row = query_db(
                    'INSERT INTO students (name, grp, task_params) VALUES (%s, %s, %s) RETURNING id',
                    (name, group, json.dumps(params)), commit=True)
                session['student_id'] = row['id']
            return redirect('/lab')
    return render_template('login.html')


@app.route('/lab')
def lab():
    if session.get('role') != 'student':
        return redirect('/')
    return render_template('lab.html', name=session['name'], group=session['group'])


@app.route('/teacher')
def teacher():
    if session.get('role') != 'teacher':
        return redirect('/')
    students = query_db('SELECT * FROM students ORDER BY created_at DESC')
    return render_template('teacher.html', name=session['name'], students=students)


@app.route('/api/calc', methods=['POST'])
def api_calc():
    data = request.get_json()
    if not data or 'd' not in data:
        return jsonify({'error': 'Не указано значение d'}), 400
    try:
        d = float(str(data['d']).replace(',', '.'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Некорректное значение d'}), 400
    if d <= 0 or d >= 0.450:
        return jsonify({'error': 'Ошибка: d должно быть больше 0 и меньше 0,450'}), 400
    result = calculate(d)
    if result is None:
        return jsonify({'error': 'Ошибка вычислений'}), 400
    if result['d_gt_F']:
        if abs(result['G']) < 1:
            result['desc'] = 'действительное, перевёрнутое, уменьшенное'
        else:
            result['desc'] = 'действительное, перевёрнутое, увеличенное'
    else:
        result['desc'] = 'мнимое, прямое, увеличенное'
    student_id = session.get('student_id')
    if student_id:
        row = query_db('SELECT lab_data FROM students WHERE id = %s',
                        (student_id,), one=True)
        history = []
        if row and row['lab_data']:
            try:
                old = json.loads(row['lab_data'])
                history = old if isinstance(old, list) else [old]
            except Exception:
                pass
        history.append(result)
        query_db('UPDATE students SET d_value = %s, lab_data = %s WHERE id = %s',
                 (d, json.dumps(history, ensure_ascii=False), student_id),
                 commit=True)
    return jsonify(result)


@app.route('/api/test', methods=['POST'])
def api_test():
    if session.get('role') != 'student':
        return jsonify({'error': 'Доступ запрещён'}), 403
    data = request.get_json()
    if not data or 'answers' not in data:
        return jsonify({'error': 'Нет ответов'}), 400
    answers = data['answers']
    correct = [1, 2, 1, 2, 2, 2, 1, 1, 1, 2]
    score = 0
    for i in range(10):
        if i < len(answers) and answers[i] == correct[i]:
            score += 1
    student_id = session.get('student_id')
    if student_id:
        row = query_db('SELECT test_answers FROM students WHERE id = %s',
                        (student_id,), one=True)
        history = []
        if row and row['test_answers']:
            try:
                old = json.loads(row['test_answers'])
                history = old if isinstance(old, list) and len(old) > 0 \
                    and isinstance(old[0], dict) else []
            except Exception:
                pass
        history.append({'score': score, 'answers': answers})
        query_db('UPDATE students SET test_score = %s, test_answers = %s WHERE id = %s',
                 (score, json.dumps(history), student_id), commit=True)
    return jsonify({'score': score, 'total': 10, 'correct': correct})


@app.route('/api/task_params', methods=['GET'])
def api_task_params():
    """Возвращает параметры задач студента (без правильных ответов)"""
    if session.get('role') != 'student':
        return jsonify({'error': 'Доступ запрещён'}), 403
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'error': 'Студент не найден'}), 400
    row = query_db('SELECT task_params FROM students WHERE id = %s',
                    (student_id,), one=True)
    if not row or not row.get('task_params'):
        params = generate_task_params()
        query_db('UPDATE students SET task_params = %s WHERE id = %s',
                 (json.dumps(params), student_id), commit=True)
    else:
        params = json.loads(row['task_params'])
    # Убираем ответы — студент их не увидит
    safe = {}
    for key, val in params.items():
        safe[key] = {k: v for k, v in val.items()
                     if k not in ('answer', 'tolerance')}
    return jsonify(safe)


@app.route('/api/task', methods=['POST'])
def api_task():
    if session.get('role') != 'student':
        return jsonify({'error': 'Доступ запрещён'}), 403
    data = request.get_json()
    if not data or 'task' not in data or 'answer' not in data:
        return jsonify({'error': 'Нет данных'}), 400
    task_num = int(data['task'])
    try:
        answer = float(str(data['answer']).replace(',', '.'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Некорректный ответ'}), 400

    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'error': 'Студент не найден'}), 400

    row = query_db('SELECT task_params, task_results FROM students WHERE id = %s',
                    (student_id,), one=True)
    if not row or not row.get('task_params'):
        return jsonify({'error': 'Параметры задач не найдены'}), 400

    params = json.loads(row['task_params'])
    task_key = str(task_num)
    if task_key not in params:
        return jsonify({'error': 'Неверный номер задачи'}), 400

    correct_val = params[task_key]['answer']
    tolerance = params[task_key]['tolerance']
    is_correct = abs(answer - correct_val) <= tolerance

    task_results = {}
    if row.get('task_results'):
        task_results = json.loads(row['task_results'])

    hint_used = data.get('hint_used', False)
    if task_key not in task_results:
        task_results[task_key] = {'attempts': 0, 'solved': False, 'hint_used': False}
    task_results[task_key]['attempts'] += 1
    if hint_used:
        task_results[task_key]['hint_used'] = True
    if is_correct:
        task_results[task_key]['solved'] = True

    query_db('UPDATE students SET task_results = %s WHERE id = %s',
             (json.dumps(task_results), student_id), commit=True)

    return jsonify({'correct': is_correct})


@app.route('/api/change_password', methods=['POST'])
def api_change_password():
    if session.get('role') != 'teacher':
        return jsonify({'error': 'Доступ запрещён'}), 403
    data = request.get_json()
    if not data or 'old' not in data or 'new' not in data:
        return jsonify({'error': 'Укажите старый и новый пароль'}), 400
    old_pass = data['old'].strip()
    new_pass = data['new'].strip()
    if not new_pass:
        return jsonify({'error': 'Новый пароль не может быть пустым'}), 400
    teacher_id = session.get('teacher_id')
    teacher = query_db('SELECT * FROM teachers WHERE id = %s AND password = %s',
                        (teacher_id, old_pass), one=True)
    if not teacher:
        return jsonify({'error': 'Неверный текущий пароль'}), 400
    query_db('UPDATE teachers SET password = %s WHERE id = %s',
             (new_pass, teacher_id), commit=True)
    return jsonify({'ok': True})


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
