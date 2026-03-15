from flask import Flask, render_template, request, redirect, jsonify, send_file, url_for, flash 
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import csv
import io

app = Flask(__name__)
app.secret_key = '12345'  # Use a secure random key in production

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ---------- User Model ----------
class Admin(UserMixin):
    def __init__(self, id_, username):
        self.id = id_
        self.username = username

    @staticmethod
    def get_by_username(username):
        with sqlite3.connect('orders.db') as conn:
            c = conn.cursor()
            c.execute("SELECT id, username, password FROM admin WHERE username=?", (username,))
            result = c.fetchone()
            if result:
                return {'id': result[0], 'username': result[1], 'password': result[2]}
            return None

@login_manager.user_loader
def load_user(user_id):
    with sqlite3.connect('orders.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, username FROM admin WHERE id=?", (user_id,))
        result = c.fetchone()
        if result:
            return Admin(id_=result[0], username=result[1])
        return None

# ---------- Database Setup ----------
def init_db():
    with sqlite3.connect('orders.db') as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seat_id TEXT NOT NULL,
                drink TEXT NOT NULL,
                extras TEXT,
                status TEXT DEFAULT 'Pending',
                booking_time TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        ''')
        c.execute("SELECT * FROM admin WHERE username='admin'")
        if not c.fetchone():
            hashed_password = generate_password_hash('admin123')  # Default password
            c.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ('admin', hashed_password))
        conn.commit()

# ---------- Menu ----------
@app.route('/menu/<seat_id>', methods=['GET', 'POST'])
def menu(seat_id):
    if request.method == 'POST':
        drink = request.form.get('drink', '').strip()
        extras = request.form.get('extras', '').strip()

        if drink.lower() == 'tea':
            milk = request.form.get('extras_tea_milk', '')
            sugar = request.form.get('extras_tea_sugar', '')
            if milk:
                extras += f" | Milk: {milk}"
            if sugar:
                extras += f", Sugar: {sugar}"
        elif drink.lower() == 'coffee':
            style = request.form.get('extras_coffee_style', '')
            if style:
                extras += f" | Coffee Style: {style}"

        booking_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with sqlite3.connect('orders.db') as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO orders (seat_id, drink, extras, status, booking_time)
                VALUES (?, ?, ?, 'Pending', ?)
            ''', (seat_id, drink, extras, booking_time))
            conn.commit()

        return render_template('thanks.html', seat_id=seat_id)

    return render_template('menu.html', seat_id=seat_id)

# ---------- Login ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Admin.get_by_username(username)
        if user and check_password_hash(user['password'], password):
            login_user(Admin(id_=user['id'], username=user['username']))
            return redirect(url_for('dashboard'))
        flash("Invalid username or password.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# ---------- Change Password ----------
@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form['current_password']
        new_pw = request.form['new_password']
        user_data = Admin.get_by_username(current_user.username)
        if user_data and check_password_hash(user_data['password'], current_pw):
            hashed = generate_password_hash(new_pw)
            with sqlite3.connect('orders.db') as conn:
                c = conn.cursor()
                c.execute("UPDATE admin SET password=? WHERE username=?", (hashed, current_user.username))
                conn.commit()
            flash("Password updated successfully.")
        else:
            flash("Current password is incorrect.")
    return render_template("change_password.html")

# ---------- Dashboard ----------
@app.route('/dashboard')
@login_required
def dashboard():
    with sqlite3.connect('orders.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, seat_id, drink, extras, status, booking_time FROM orders ORDER BY booking_time DESC")
        orders = c.fetchall()
    current_month = datetime.now().strftime('%Y-%m')
    return render_template('dashboard.html', orders=orders, current_month=current_month)

# ---------- Live Orders ----------
@app.route('/orders/live')
@login_required
def live_orders():
    with sqlite3.connect('orders.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, seat_id, drink, extras, status, booking_time FROM orders ORDER BY booking_time DESC")
        orders = [
            {
                'id': row[0],
                'seat_id': row[1],
                'drink': row[2],
                'extras': row[3],
                'status': row[4],
                'booking_time': row[5]
            }
            for row in c.fetchall()
        ]
    return jsonify(orders)

# ---------- Update Order ----------
@app.route('/orders/update/<int:order_id>/<status>', methods=['POST'])
@login_required
def update_order_status(order_id, status):
    if status not in ['Pending', 'Preparing', 'Completed']:
        return 'Invalid status', 400
    with sqlite3.connect('orders.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        conn.commit()
    return '', 204

# ---------- Clear Completed ----------
@app.route('/orders/clear', methods=['POST'])
@login_required
def clear_completed_orders():
    with sqlite3.connect('orders.db') as conn:
        c = conn.cursor()
        c.execute("DELETE FROM orders WHERE status='Completed'")
        conn.commit()
    return '', 204

# ---------- Export CSV ----------
@app.route('/orders/export/csv')
@login_required
def export_csv():
    month = request.args.get('month')
    if not month:
        return "Month query parameter required (YYYY-MM)", 400

    start_date = f"{month}-01"
    end_date = f"{month}-31"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Seat ID', 'Drink', 'Extras', 'Status', 'Booking Time'])

    with sqlite3.connect('orders.db') as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, seat_id, drink, extras, status, booking_time
            FROM orders
            WHERE booking_time BETWEEN ? AND ?
            ORDER BY booking_time ASC
        ''', (start_date, end_date))
        for row in c.fetchall():
            writer.writerow(row)

    output.seek(0)
    return send_file(io.BytesIO(output.read().encode('utf-8')),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=f'orders_{month}.csv')

# ---------- Main ----------
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
