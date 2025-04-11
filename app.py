from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection
from matcher import match_startups

app = Flask(__name__)
app.secret_key = 'your_secret_key'

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

        cursor.execute('''
            INSERT INTO startups (user_id, name, pitch, industry, funding_needed, traction, stage, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], name, pitch, industry, funding_needed, traction, stage, risk_level))
        conn.commit()
        flash('New startup added successfully!', 'success')

    # Fetch all startups for this founder
    cursor.execute('SELECT * FROM startups WHERE user_id = ?', (session['user_id'],))
    startups = cursor.fetchall()

    # Analytics and interactions per startup
    startups_data = []
    for startup in startups:
        startup_dict = dict(startup)

        # Analytics
        cursor.execute('SELECT COUNT(*) as view_count FROM views WHERE startup_id = ?', (startup['id'],))
        startup_dict['views'] = cursor.fetchone()['view_count']
        cursor.execute('SELECT COUNT(*) as interest_count FROM interactions WHERE startup_id = ? AND type = ?', (startup['id'], 'interest'))
        startup_dict['interests'] = cursor.fetchone()['interest_count']
        cursor.execute('SELECT SUM(amount) as total_invested FROM interactions WHERE startup_id = ? AND type = ?', (startup['id'], 'investment'))
        total_invested = cursor.fetchone()['total_invested']
        startup_dict['total_invested'] = total_invested if total_invested else 0.0

        # Interactions with investor details
        cursor.execute('''
            SELECT i.type, i.amount, i.timestamp, u.id as investor_id, u.username
            FROM interactions i
            JOIN users u ON i.investor_id = u.id
            WHERE i.startup_id = ? AND i.type = 'investment'
            ORDER BY i.timestamp DESC
        ''', (startup['id'],))
        startup_dict['investors'] = cursor.fetchall()

        startups_data.append(startup_dict)

    cursor.execute('SELECT COUNT(*) as unread_count FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
    unread_messages = cursor.fetchone()['unread_count']

    conn.close()
    return render_template('founder_dashboard.html', startups=startups_data, unread_messages=unread_messages)

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

    cursor.execute('SELECT COUNT(*) as unread_count FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
    unread_messages = cursor.fetchone()['unread_count']

    conn.close()
    return render_template('investor_dashboard.html', startups=startups, unread_messages=unread_messages)

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

    cursor.execute('SELECT id FROM users WHERE id = (SELECT user_id FROM startups WHERE id = ?)', (startup_id,))
    founder_id = cursor.fetchone()['id']

    conn.close()
    return render_template('startup_detail.html', startup=startup, unread_messages=unread_messages, founder_id=founder_id)

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
            return redirect(url_for('messages', startup_id=startup_id, other_user_id=receiver_id))

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

if __name__ == '__main__':
    app.run(debug=True)