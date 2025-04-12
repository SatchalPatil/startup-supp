from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, join_room, emit
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db, get_db_connection
from matcher import match_startups
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)

init_db()

def is_session_active(scheduled_at):
    if not scheduled_at:
        return True  # Instant sessions are always active
    now = datetime.now()
    scheduled_time = datetime.strptime(scheduled_at, '%Y-%m-%d %H:%M:%S')
    start_window = scheduled_time - timedelta(minutes=5)
    end_window = scheduled_time + timedelta(hours=1)
    return start_window <= now <= end_window

@app.route('/')
def index():
    unread_messages = 0
    if 'user_id' in session:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as unread_count FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
        unread_messages = cursor.fetchone()['unread_count']
        conn.close()
    return render_template('index.html', unread_messages=unread_messages)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        email = request.form['email']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            flash('Username already exists.', 'danger')
            conn.close()
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)',
            (username, hashed_password, role, email)
        )
        conn.commit()
        conn.close()
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, password, role FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['role'] = user[2]
            flash('Logged in successfully!', 'success')
            if user[2] == 'founder':
                return redirect(url_for('founder_dashboard'))
            else:
                return redirect(url_for('investor_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/founder_dashboard', methods=['GET', 'POST'])
def founder_dashboard():
    if 'user_id' not in session or session['role'] != 'founder':
        flash('Please log in as a founder.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        pitch = request.form['pitch']
        industry = request.form['industry']
        funding_needed = float(request.form['funding_needed'])
        traction = request.form['traction']
        stage = request.form['stage']
        risk_level = request.form['risk_level']

        cursor.execute('SELECT id FROM startups WHERE user_id = ?', (session['user_id'],))
        existing = cursor.fetchone()

        if existing:
            cursor.execute('''
                UPDATE startups SET name = ?, pitch = ?, industry = ?, funding_needed = ?,
                traction = ?, stage = ?, risk_level = ?
                WHERE user_id = ?
            ''', (name, pitch, industry, funding_needed, traction, stage, risk_level, session['user_id']))
        else:
            cursor.execute('''
                INSERT INTO startups (user_id, name, pitch, industry, funding_needed, traction, stage, risk_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], name, pitch, industry, funding_needed, traction, stage, risk_level))

        conn.commit()
        flash('Startup details saved successfully!', 'success')

    cursor.execute('SELECT * FROM startups WHERE user_id = ?', (session['user_id'],))
    startup = cursor.fetchone()

    interactions = []
    analytics = {}
    if startup:
        cursor.execute('''
            SELECT i.type, i.amount, i.timestamp, u.username
            FROM interactions i
            JOIN users u ON i.investor_id = u.id
            WHERE i.startup_id = ?
            ORDER BY i.timestamp DESC
        ''', (startup['id'],))
        interactions = cursor.fetchall()

        cursor.execute('SELECT COUNT(*) as view_count FROM views WHERE startup_id = ?', (startup['id'],))
        analytics['views'] = cursor.fetchone()['view_count']
        cursor.execute('SELECT COUNT(*) as interest_count FROM interactions WHERE startup_id = ? AND type = ?', (startup['id'], 'interest'))
        analytics['interests'] = cursor.fetchone()['interest_count']
        cursor.execute('SELECT SUM(amount) as total_invested FROM interactions WHERE startup_id = ? AND type = ?', (startup['id'], 'investment'))
        total_invested = cursor.fetchone()['total_invested']
        analytics['total_invested'] = total_invested if total_invested else 0.0

    cursor.execute('SELECT COUNT(*) as unread_count FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
    unread_messages = cursor.fetchone()['unread_count']

    conn.close()
    return render_template('founder_dashboard.html', startup=startup, interactions=interactions, analytics=analytics, unread_messages=unread_messages)

@app.route('/investor_dashboard', methods=['GET', 'POST'])
def investor_dashboard():
    if 'user_id' not in session or session['role'] != 'investor':
        flash('Please log in as an investor.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    startups = []

    if request.method == 'POST':
        industry = request.form.get('industry', '')
        stage = request.form.get('stage', '')
        risk_level = request.form.get('risk_level', '')
        cursor.execute('SELECT * FROM startups')
        all_startups = cursor.fetchall()
        startups = match_startups(all_startups, industry, stage, risk_level)
    else:
        cursor.execute('SELECT * FROM startups')
        startups = cursor.fetchall()

    cursor.execute('''
        SELECT ps.id, ps.title, ps.scheduled_at, s.name as startup_name
        FROM pitch_sessions ps
        JOIN startups s ON ps.startup_id = s.id
        WHERE ps.is_active = 1 AND (ps.scheduled_at > ? OR ps.scheduled_at IS NULL)
        ORDER BY ps.scheduled_at ASC
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
    scheduled_sessions = cursor.fetchall()

    cursor.execute('SELECT COUNT(*) as unread_count FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
    unread_messages = cursor.fetchone()['unread_count']

    conn.close()
    return render_template('investor_dashboard.html', startups=startups, scheduled_sessions=scheduled_sessions, is_session_active=is_session_active, unread_messages=unread_messages)

@app.route('/startup/<int:startup_id>', methods=['GET', 'POST'])
def startup_detail(startup_id):
    if 'user_id' not in session or session['role'] != 'investor':
        flash('Please log in as an investor.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM startups WHERE id = ?', (startup_id,))
    startup = cursor.fetchone()

    if not startup:
        flash('Startup not found.', 'danger')
        conn.close()
        return redirect(url_for('investor_dashboard'))

    cursor.execute('INSERT INTO views (startup_id, viewer_id) VALUES (?, ?)', (startup_id, session['user_id']))
    conn.commit()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'invest':
            try:
                amount = float(request.form.get('amount'))
                if amount <= 0:
                    flash('Investment amount must be greater than zero.', 'danger')
                else:
                    cursor.execute('''
                        INSERT INTO interactions (investor_id, startup_id, type, amount)
                        VALUES (?, ?, ?, ?)
                    ''', (session['user_id'], startup_id, 'investment', amount))
                    conn.commit()
                    flash(f'Successfully invested ${amount:.2f} in {startup["name"]}.', 'success')
            except ValueError:
                flash('Invalid investment amount.', 'danger')

        elif action == 'interest':
            cursor.execute('''
                SELECT id FROM interactions
                WHERE investor_id = ? AND startup_id = ? AND type = ?
            ''', (session['user_id'], startup_id, 'interest'))
            if cursor.fetchone():
                flash('You have already shown interest in this startup.', 'warning')
            else:
                cursor.execute('''
                    INSERT INTO interactions (investor_id, startup_id, type)
                    VALUES (?, ?, ?)
                ''', (session['user_id'], startup_id, 'interest'))
                conn.commit()
                flash(f'Interest shown in {startup["name"]}.', 'success')

        conn.close()
        return redirect(url_for('startup_detail', startup_id=startup_id))

    cursor.execute('SELECT COUNT(*) as unread_count FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
    unread_messages = cursor.fetchone()['unread_count']

    conn.close()
    return render_template('startup_detail.html', startup=startup, unread_messages=unread_messages)

@app.route('/messages', methods=['GET', 'POST'])
def messages():
    if 'user_id' not in session:
        flash('Please log in to view messages.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        receiver_id = int(request.form['receiver_id'])
        startup_id = int(request.form['startup_id'])
        content = request.form['content'].strip()

        if not content:
            flash('Message cannot be empty.', 'danger')
        else:
            cursor.execute('''
                INSERT INTO messages (sender_id, receiver_id, startup_id, content)
                VALUES (?, ?, ?, ?)
            ''', (session['user_id'], receiver_id, startup_id, content))
            conn.commit()
            flash('Message sent successfully!', 'success')

    cursor.execute('''
        SELECT DISTINCT m.startup_id, s.name as startup_name,
               CASE
                   WHEN m.sender_id = ? THEN m.receiver_id
                   ELSE m.sender_id
               END as other_user_id,
               u.username as other_username
        FROM messages m
        JOIN startups s ON m.startup_id = s.id
        JOIN users u ON (u.id = m.sender_id OR u.id = m.receiver_id) AND u.id != ?
        WHERE m.sender_id = ? OR m.receiver_id = ?
        ORDER BY m.timestamp DESC
    ''', (session['user_id'], session['user_id'], session['user_id'], session['user_id']))
    conversations = cursor.fetchall()

    messages_list = []
    selected_startup_id = request.args.get('startup_id', type=int)
    selected_other_user_id = request.args.get('other_user_id', type=int)

    if selected_startup_id and selected_other_user_id:
        cursor.execute('''
            SELECT m.id, m.sender_id, m.receiver_id, m.content, m.timestamp, m.is_read, u.username as sender_username
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.startup_id = ? AND (
                (m.sender_id = ? AND m.receiver_id = ?) OR
                (m.sender_id = ? AND m.receiver_id = ?)
            )
            ORDER BY m.timestamp ASC
        ''', (selected_startup_id, session['user_id'], selected_other_user_id, selected_other_user_id, session['user_id']))
        messages_list = cursor.fetchall()

        cursor.execute('''
            UPDATE messages SET is_read = 1
            WHERE startup_id = ? AND sender_id = ? AND receiver_id = ? AND is_read = 0
        ''', (selected_startup_id, selected_other_user_id, session['user_id']))
        conn.commit()

    cursor.execute('SELECT COUNT(*) as unread_count FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
    unread_messages = cursor.fetchone()['unread_count']

    conn.close()
    return render_template('messages.html', conversations=conversations, messages=messages_list,
                         selected_startup_id=selected_startup_id, selected_other_user_id=selected_other_user_id,
                         unread_messages=unread_messages)

@app.route('/start_pitch', methods=['GET', 'POST'])
def start_pitch():
    if 'user_id' not in session or session['role'] != 'founder':
        flash('Please log in as a founder.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM startups WHERE user_id = ?', (session['user_id'],))
    startup = cursor.fetchone()

    if not startup:
        flash('Create a startup profile first.', 'danger')
        conn.close()
        return redirect(url_for('founder_dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        pitch_content = request.form['pitch_content']

        cursor.execute('''
            INSERT INTO pitch_sessions (startup_id, title, pitch_content)
            VALUES (?, ?, ?)
        ''', (startup['id'], title, pitch_content))
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        flash('Pitch session started!', 'success')
        return redirect(url_for('pitch_session', session_id=session_id))

    conn.close()
    return render_template('start_pitch.html', startup=startup)

@app.route('/schedule_pitch', methods=['GET', 'POST'])
def schedule_pitch():
    if 'user_id' not in session or session['role'] != 'founder':
        flash('Please log in as a founder.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM startups WHERE user_id = ?', (session['user_id'],))
    startup = cursor.fetchone()

    if not startup:
        flash('Create a startup profile first.', 'danger')
        conn.close()
        return redirect(url_for('founder_dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        pitch_content = request.form['pitch_content']
        date = request.form['date']
        time = request.form['time']
        try:
            scheduled_at = datetime.strptime(f"{date} {time}", '%Y-%m-%d %H:%M')
            if scheduled_at < datetime.now():
                flash('Cannot schedule a session in the past.', 'danger')
                conn.close()
                return redirect(url_for('schedule_pitch'))
            scheduled_at_str = scheduled_at.strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT INTO pitch_sessions (startup_id, title, pitch_content, scheduled_at)
                VALUES (?, ?, ?, ?)
            ''', (startup['id'], title, pitch_content, scheduled_at_str))
            session_id = cursor.lastrowid
            conn.commit()
            conn.close()
            flash('Pitch session scheduled successfully!', 'success')
            return redirect(url_for('founder_dashboard'))
        except ValueError:
            flash('Invalid date or time format.', 'danger')
            conn.close()
            return redirect(url_for('schedule_pitch'))

    conn.close()
    return render_template('schedule_pitch.html', startup=startup)

@app.route('/pitch_session/<int:session_id>', methods=['GET', 'POST'])
def pitch_session(session_id):
    if 'user_id' not in session:
        flash('Please log in to view pitch sessions.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT ps.*, s.name as startup_name, s.user_id as founder_id
        FROM pitch_sessions ps
        JOIN startups s ON ps.startup_id = s.id
        WHERE ps.id = ?
    ''', (session_id,))
    session_data = cursor.fetchone()

    if not session_data:
        flash('Pitch session not found.', 'danger')
        conn.close()
        return redirect(url_for('investor_dashboard' if session['role'] == 'investor' else 'founder_dashboard'))

    if not is_session_active(session_data['scheduled_at']):
        flash('This session is not currently active.', 'danger')
        conn.close()
        return redirect(url_for('investor_dashboard' if session['role'] == 'investor' else 'founder_dashboard'))

    cursor.execute('''
        SELECT qm.*, u.username
        FROM qna_messages qm
        JOIN users u ON qm.user_id = u.id
        WHERE qm.session_id = ?
        ORDER BY qm.timestamp ASC
    ''', (session_id,))
    qna_messages = cursor.fetchall()

    cursor.execute('SELECT COUNT(*) as unread_count FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
    unread_messages = cursor.fetchone()['unread_count']

    conn.close()
    return render_template('pitch_session.html', session=session_data, qna_messages=qna_messages, unread_messages=unread_messages)

@socketio.on('join_session')
def handle_join_session(data):
    session_id = data['session_id']
    join_room(str(session_id))
    emit('status', {'msg': 'Joined session'}, room=str(session_id))

@socketio.on('send_qna')
def handle_send_qna(data):
    session_id = data['session_id']
    content = data['content']
    is_answer = data.get('is_answer', False)
    user_id = session.get('user_id')

    if not user_id:
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO qna_messages (session_id, user_id, content, is_answer)
        VALUES (?, ?, ?, ?)
    ''', (session_id, user_id, content, is_answer))
    conn.commit()

    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    username = cursor.fetchone()['username']
    conn.close()

    emit('new_qna', {
        'username': username,
        'content': content,
        'is_answer': is_answer,
        'timestamp': 'just now'
    }, room=str(session_id))

if __name__ == '__main__':
    socketio.run(app, debug=True)