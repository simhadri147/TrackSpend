from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime,timedelta
import config
from flask import render_template, request, redirect, session
from pytz import timezone
import csv
import io
from flask import Response, request
from datetime import datetime, timedelta

app = Flask(__name__)
app.config.from_object(config)

mysql = MySQL(app)
mail = Mail(app)

# Serializer for token generation
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

@app.route('/')
def home():
    return redirect('/login')

# REGISTER
import os
from werkzeug.utils import secure_filename

from flask import flash  # for showing messages

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = generate_password_hash(request.form.get('password'))

        profile_pic = request.files.get('profile_pic')
        profile_filename = 'default.png'

        # ✅ Check if user already exists
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s OR phone = %s", (email, phone))
        existing_user = cur.fetchone()

        if existing_user:
            cur.close()
            flash("Email or phone number already registered. Please login.", "warning")
            return redirect('/login')

        # ✅ Handle profile picture upload
        if profile_pic and profile_pic.filename != '':
            ext = os.path.splitext(profile_pic.filename)[1]
            profile_filename = secure_filename(f"{email}_VNH{ext}")
            upload_path = os.path.join('static', 'uploads', profile_filename)
            profile_pic.save(upload_path)

        # ✅ Insert new user
        cur.execute("""
            INSERT INTO users (username, email, phone, password, profile_pic)
            VALUES (%s, %s, %s, %s, %s)
        """, (username, email, phone, password, profile_filename))
        mysql.connection.commit()
        cur.close()

        flash("Registration successful! Please login.", "success")
        return redirect('/login')

    return render_template('register.html')

# LOGIN
from flask import flash, get_flashed_messages

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']  # email or phone
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT * FROM users WHERE email = %s OR phone = %s
        """, (identifier, identifier))
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['profile_pic'] = user.get('profile_pic', 'default.png')
            return redirect('/dashboard')
        else:
            flash("Invalid credentials. Please try again.", "danger")
            return redirect('/login')

    return render_template('login.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    username = session.get('username')
    email = session.get('email')

    if request.method == 'POST':
        if 'remove_pic' in request.form:
            # ✅ Remove the custom profile pic if exists (except default.png)
            cur = mysql.connection.cursor()
            cur.execute("SELECT profile_pic FROM users WHERE id = %s", (user_id,))
            current_pic = cur.fetchone()['profile_pic']

            if current_pic and current_pic != 'default.png':
                try:
                    os.remove(os.path.join('static', 'uploads', current_pic))
                except FileNotFoundError:
                    pass

            # ✅ Update DB to default image
            cur.execute("UPDATE users SET profile_pic = %s WHERE id = %s", ('default.png', user_id))
            mysql.connection.commit()
            cur.close()

            session['profile_pic'] = 'default.png'
            flash("Profile picture removed.", "info")
            return redirect('/dashboard')

        # ✅ Profile picture upload logic
        profile_pic = request.files.get('profile_pic')
        if profile_pic and profile_pic.filename != '':
            ext = os.path.splitext(profile_pic.filename)[1]
            filename = secure_filename(f"{email}_VNH{ext}")
            filepath = os.path.join('static', 'uploads', filename)
            profile_pic.save(filepath)

            cur = mysql.connection.cursor()
            cur.execute("UPDATE users SET profile_pic = %s WHERE id = %s", (filename, user_id))
            mysql.connection.commit()
            cur.close()

            session['profile_pic'] = filename
            flash("Profile picture updated successfully.", "success")
            return redirect('/dashboard')

    return render_template('profile.html')


# DASHBOARD
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    # Fetch all transactions
    cur.execute("SELECT * FROM transactions WHERE user_id = %s ORDER BY date DESC", (user_id,))
    txns = cur.fetchall()

    # Summary
    total_income = sum(float(txn['amount']) for txn in txns if txn['type'] == 'income')
    total_expense = sum(float(txn['amount']) for txn in txns if txn['type'] == 'expense')
    balance = total_income - total_expense
    txn_count = len(txns)

    recent_txns = txns[:5]  # First 5 transactions

    cur.close()
    return render_template('dashboard.html',
                           username=session['username'],
                           total_income=total_income,
                           total_expense=total_expense,
                           balance=balance,
                           txn_count=txn_count,
                           recent_txns=recent_txns)


# LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        email = request.form['email']
        token = s.dumps(email, salt='reset-password')

        link = url_for('reset', token=token, _external=True)
        msg = Message("Password Reset Request", sender=config.MAIL_USERNAME, recipients=[email])
        msg.body = f"Click the link to reset your password: {link}"

        mail.send(msg)
        return render_template('forgot_success.html', email=email)
    return render_template('forgot.html')


# RESET PASSWORD
@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset(token):
    try:
        email = s.loads(token, salt='reset-password', max_age=1800)  # 30 mins expiry
    except:
        return "The reset link is invalid or expired."

    if request.method == 'POST':
        new_password = generate_password_hash(request.form['password'])
        cur = mysql.connection.cursor()
        cur.execute("UPDATE users SET password = %s WHERE email = %s", (new_password, email))
        mysql.connection.commit()
        cur.close()
        return redirect('/login')

    return render_template('reset.html')


from datetime import datetime
from pytz import timezone

@app.route('/add_transaction', methods=['GET', 'POST'])
def add_transaction():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    # ✅ Fetch suggested categories from past entries
    # Fetch user-defined categories instead of distinct from transactions
    cur.execute("SELECT name FROM categories WHERE user_id = %s ORDER BY name", (user_id,))
    categories = [row['name'] for row in cur.fetchall()]

    
    if request.method == 'POST':
        txn_type = request.form.get('type')
        amount = request.form.get('amount')
        category = request.form.get('category')
        note = request.form.get('note')

        # ✅ Auto IST time
        ist = timezone('Asia/Kolkata')
        current_time = datetime.now(ist)

        # ✅ Insert
        cur.execute("""
            INSERT INTO transactions (user_id, type, amount, category, note, date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, txn_type, amount, category, note, current_time))
        mysql.connection.commit()
        cur.close()

        return redirect('/transactions')

    cur.close()
    return render_template('add_transaction.html', txn=None, suggestions=categories)



from datetime import datetime
from pytz import timezone

@app.route('/edit_transaction/<int:id>', methods=['GET', 'POST'])
def edit_transaction(id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    # Fetch the transaction to edit
    cur.execute("SELECT * FROM transactions WHERE id = %s AND user_id = %s", (id, user_id))
    txn = cur.fetchone()

    if not txn:
        cur.close()
        return "Transaction not found or unauthorized", 404

    # Fetch unique categories for suggestions
    cur.execute("SELECT DISTINCT category FROM transactions WHERE user_id = %s", (user_id,))
    suggestions = [row['category'] for row in cur.fetchall()]
    cur.close()

    if request.method == 'POST':
        # Get updated values from the form
        txn_type = request.form.get('type')
        amount = request.form.get('amount')
        category = request.form.get('category')
        note = request.form.get('note')


        # Update the transaction
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE transactions 
            SET type = %s, amount = %s, category = %s, note = %s, date = %s 
            WHERE id = %s AND user_id = %s
        """, (txn_type, amount, category, note, id, user_id))
        mysql.connection.commit()
        cur.close()

        return redirect('/transactions')

    # GET request — show form with prefilled txn values
    return render_template("add_transaction.html", txn=txn, suggestions=suggestions)

@app.route('/transactions', methods=['GET', 'POST'])
def transactions():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    # ✅ Fetch user-defined categories for the filter dropdown
    cur.execute("SELECT name FROM categories WHERE user_id = %s ORDER BY name", (user_id,))
    categories = [row['name'] for row in cur.fetchall()]

    # Default query (no filter)
    query = "SELECT * FROM transactions WHERE user_id = %s"
    filters = [user_id]

    # Default selected category (used in template)
    selected_category = ''

    # Collect filters from POST request
    if request.method == 'POST':
        from_date = request.form.get('from_date')
        to_date = request.form.get('to_date')
        txn_type = request.form.get('type')
        category = request.form.get('category')
        quick_filter = request.form.get('quick_filter')

        # Apply quick filters
        today = datetime.today().date()
        if quick_filter == 'today':
            from_date = to_date = today
        elif quick_filter == 'this_week':
            from_date = today - timedelta(days=today.weekday())
            to_date = today
        elif quick_filter == 'this_month':
            from_date = today.replace(day=1)
            to_date = today
        elif quick_filter == 'this_year':
            from_date = today.replace(month=1, day=1)
            to_date = today

        # Filter by date
        if from_date:
            query += " AND DATE(date) >= %s"
            filters.append(from_date)
        if to_date:
            query += " AND DATE(date) <= %s"
            filters.append(to_date)

        # Filter by type
        if txn_type and txn_type != 'all':
            query += " AND type = %s"
            filters.append(txn_type)

        # Filter by category
        if category:
            query += " AND category = %s"
            filters.append(category)
            selected_category = category  # Store for highlighting selected in dropdown

    query += " ORDER BY date DESC"
    cur.execute(query, filters)
    txns = cur.fetchall()
    cur.close()

    total_income = sum(float(t['amount']) for t in txns if t['type'] == 'income')
    total_expense = sum(float(t['amount']) for t in txns if t['type'] == 'expense')
    balance = total_income - total_expense

    return render_template('transactions.html',
                           txns=txns,
                           total_income=total_income,
                           total_expense=total_expense,
                           balance=balance,
                           categories=categories,
                           selected_category=selected_category)

    
    # EXPORT TRANSACTIONS
@app.route('/export_transactions', methods=['POST'])
def export_transactions():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    # Reuse same filtering logic
    query = "SELECT date, type, amount, category, note FROM transactions WHERE user_id = %s"
    filters = [user_id]

    # Filters from POST
    from_date = request.form.get('from_date')
    to_date = request.form.get('to_date')
    txn_type = request.form.get('type')
    category = request.form.get('category')
    quick_filter = request.form.get('quick_filter')

    today = datetime.today().date()
    if quick_filter == 'today':
        from_date = to_date = today
    elif quick_filter == 'this_week':
        from_date = today - timedelta(days=today.weekday())
        to_date = today
    elif quick_filter == 'this_month':
        from_date = today.replace(day=1)
        to_date = today
    elif quick_filter == 'this_year':
        from_date = today.replace(month=1, day=1)
        to_date = today

    if from_date:
        query += " AND DATE(date) >= %s"
        filters.append(from_date)
    if to_date:
        query += " AND DATE(date) <= %s"
        filters.append(to_date)

    if txn_type and txn_type != 'all':
        query += " AND type = %s"
        filters.append(txn_type)

    if category:
        query += " AND category LIKE %s"
        filters.append(f"%{category}%")

    query += " ORDER BY date DESC"
    cur.execute(query, filters)
    txns = cur.fetchall()
    cur.close()

    # Write CSV to memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Type', 'Amount', 'Category', 'Note'])

    for t in txns:
        writer.writerow([t['date'], t['type'], t['amount'], t['category'], t['note']])

    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=filtered_transactions.csv"}
    )


#manage categories
@app.route('/manage_categories', methods=['GET', 'POST'])
def manage_categories():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    # Add new category
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            cur.execute("INSERT INTO categories (user_id, name) VALUES (%s, %s)", (user_id, name))
            mysql.connection.commit()

    # Show categories
    cur.execute("SELECT id, name FROM categories WHERE user_id = %s", (user_id,))
    categories = cur.fetchall()
    cur.close()

    return render_template("manage_categories.html", categories=categories)



if __name__ == '__main__':
    app.run(debug=True)
