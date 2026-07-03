from flask import Flask, render_template, request, redirect, session, flash ,g ,url_for, send_file
from database import get_connection
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import bcrypt
import re
from datetime import datetime, timedelta, date
import io
from reportlab.pdfgen import canvas
import sqlite3


app = Flask(__name__)
app.secret_key = "admin123"
DATABASE = "hostel.db"


# ==========================
# MAIL CONFIGURATION
# ==========================
app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']           = 587
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USERNAME']       = 'p24016577@student.newinti.edu.my'
app.config['MAIL_PASSWORD']       = 'fqzr qrbj gnlx ssgm'
app.config['MAIL_DEFAULT_SENDER'] = 'p24016577@student.newinti.edu.my'

mail = Mail(app)

def get_db():
    #if no connection create one
    if 'db' not in g:
        g.db = get_connection()
    #else use old one
    return g.db


@app.teardown_appcontext
def close_db(error):
    #delete db from g
    db = g.pop('db', None)
    #close connection
    if db is not None:
        db.close()


@app.context_processor          # run this before every template render
def inject_unread_status():

    user_id = session.get('user_id')
    role = session.get('role')
    has_unread = False                       # assume no unread by default

    if user_id and role == 'student':       # only check if someone is logged in and student
        conn = get_db()

        student = conn.execute(
            "SELECT last_read_announcement_at FROM Student WHERE student_id = ?",
            (user_id,)
        ).fetchone()
        # fetches the timestamp of when they last opened announcements

        if student['last_read_announcement_at'] is None:
            has_unread = True
            # they have NEVER opened announcements → definitely unread

        else:
            unread = conn.execute("""
                SELECT 1 FROM Announcement
                WHERE audience = 'all' AND created_at > ?
                UNION
                SELECT 1 FROM Announcement_Recipient
                WHERE student_id = ? AND is_read = 0
                LIMIT 1
            """, (student['last_read_announcement_at'], user_id)).fetchone()
            # checks if any announcement was posted AFTER their last visit
            # OR if they have a personal (audience='one') unread announcement

            has_unread = unread is not None
            # if the query found anything → has_unread = True

    return dict(has_unread=has_unread)
    # injects has_unread into every template


# ==========================
# RESET TOKEN HELPERS
# ==========================
def generate_reset_token(email):
    s = URLSafeTimedSerializer(app.secret_key)
    return s.dumps(email, salt="password-reset-salt")

def verify_reset_token(token, max_age=1800):
    s = URLSafeTimedSerializer(app.secret_key)
    try:
        return s.loads(token, salt="password-reset-salt", max_age=max_age)
    except Exception:
        return None


# ==========================
# TABLE RESOLVER
# Determines whether to query Student or Staff table based on email domain.
# Raises ValueError if the resolved name is not in the whitelist.
# ==========================
VALID_TABLES = {'Student', 'Staff'}

def resolve_table(email):
    table = 'Student' if email.endswith('@student.newinti.edu.my') else 'Staff'
    if table not in VALID_TABLES:
        raise ValueError(f"Unexpected table: {table}")
    return table


# ==========================
# ROLE REDIRECT
# ==========================
def redirect_by_role(role):
    if role == 'admin':
        return redirect('/admin_dashboard')
    elif role == 'warden':
        return redirect('/warden_dashboard')
    elif role == 'student':
        return redirect('/student_dashboard')
    return redirect('/user_login')


# ==========================
# VALIDATORS
# ==========================
def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w{2,}$'
    return re.match(pattern, email)

def is_valid_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit."
    if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
        return False, "Password must contain at least one special character."
    return True, ""


# ==========================
# EMAIL HELPER — Password reset
# ==========================
def send_reset_email(to_email, reset_link):
    subject = "Password Reset Request"
    body = f"""You requested to reset your Hostel Management System password.

Click the link below to set a new password (valid for 30 minutes):

{reset_link}

If you did not request this, please ignore this email.

Regards,
Hostel Management Team
"""
    msg = Message(subject=subject, recipients=[to_email], body=body)
    try:
        mail.send(msg)
    except Exception as e:
        print(f"[EMAIL ERROR] {to_email}: {e}")


# ==========================
# EMAIL HELPER — Application result
# login_url is passed in from the route via url_for so nothing is hardcoded.
# ==========================
def send_application_email(to_email, fullname, status, login_url=None):
    if status == 'approved':
        subject = "Your Hostel Application Has Been Approved"
        body = f"""Dear {fullname},

Congratulations! Your hostel application has been approved.

You may now log in using your student email and the password you registered with.

Login here: {login_url}

If you have any questions, please contact the hostel admin.

Regards,
Hostel Management Team
"""
    else:
        subject = "Your Hostel Application Has Been Rejected"
        body = f"""Dear {fullname},

We regret to inform you that your hostel application has been rejected.

If you believe this is a mistake or would like further clarification,
please contact the hostel admin directly.

Regards,
Hostel Management Team
"""

    msg = Message(subject=subject, recipients=[to_email], body=body)
    try:
        mail.send(msg)
    except Exception as e:
        print(f"[EMAIL ERROR] {to_email}: {e}")


# CHECK PAYMENT TIMEOUT FUNCTION
def check_payment_timeout():
    if 'payment_start_time' not in session:
        return False

    start_time = datetime.strptime(session['payment_start_time'], "%Y-%m-%d %H:%M:%S")
    time_limit = timedelta(minutes=10)

    if datetime.now() - start_time > time_limit:
        session.pop('payment_start_time', None)
        return False

    return True


# ==========================
# AUTO GENERATE LATE PAYMENT FINE
# Inserts into Late_Payment table (amount = late fee only)
# ==========================
def check_late_payments(student_id):
    conn = get_db()

    # Only unpaid rentals that are overdue
    rentals = conn.execute("""
        SELECT * FROM Rental_Bill
        WHERE student_id = ?
        AND payment_id IS NULL
    """, (student_id,)).fetchall()

    for rental in rentals:
        days_late, late_fine = calculate_late_fine(rental['end_date'])

        if late_fine > 0:
            existing = conn.execute("""
                SELECT * FROM Late_Payment
                WHERE rental_id = ?
                AND payment_id IS NULL
            """, (rental['rental_id'],)).fetchone()

            if existing:
                # Update the late fee amount if it has grown
                conn.execute("""
                    UPDATE Late_Payment
                    SET amount = ?
                    WHERE late_payment_id = ?
                """, (late_fine, existing['late_payment_id']))
            else:
                # Insert a new Late_Payment row (amount = late fee only)
                conn.execute("""
                    INSERT INTO Late_Payment (amount, rental_id)
                    VALUES (?, ?)
                """, (late_fine, rental['rental_id']))

    conn.commit()


# ==========================
# CALCULATE LATE FINE
# ==========================
def calculate_late_fine(due_date):
    today = date.today()
    due = datetime.strptime(due_date, "%Y-%m-%d").date()

    if today <= due:
        return 0, 0

    days_late = (today - due).days

    if days_late <= 7:
        late_fine = 10
    elif days_late <= 14:
        late_fine = 10 + (days_late - 7) * 2
    elif days_late <= 30:
        late_fine = 10 + (7 * 2) + (days_late - 14) * 5
    else:
        late_fine = 10 + (7 * 2) + (16 * 5) + (days_late - 30) * 10

    return days_late, late_fine


# ==========================
# CALCULATE TOTAL LATE DAYS FOR A STUDENT
# Sums up all overdue days across every unpaid rental bill.
# Returns a dict with total_days_late and a per-rental breakdown.
# ==========================
def get_total_late_days(student_id):
    conn = get_db()

    unpaid_rentals = conn.execute("""
        SELECT rental_id, end_date FROM Rental_Bill
        WHERE student_id = ?
        AND payment_id IS NULL
    """, (student_id,)).fetchall()

    total_days_late = 0
    breakdown = []

    for rental in unpaid_rentals:
        days_late, late_fine = calculate_late_fine(rental['end_date'])

        if days_late > 0:
            total_days_late += days_late
            breakdown.append({
                'rental_id'  : rental['rental_id'],
                'due_date'   : rental['end_date'],
                'days_late'  : days_late,
                'late_fine'  : late_fine,
            })

    return {
        'total_days_late' : total_days_late,
        'breakdown'       : breakdown,
    }


# ==========================
# EMAIL RECEIPT NOTIFICATION
# Sends a confirmation email after any successful payment.
# Fails silently (logs to console) so a broken email never blocks payment.
# ==========================
def send_payment_receipt_email(conn, student_id, payment_id, amount, payment_method):
    student = conn.execute("SELECT * FROM Student WHERE student_id = ?", (student_id,)).fetchone()

    if not student or not student['email']:
        return  # no email on file, skip silently

    msg = Message(
        subject='Payment Receipt - Confirmation',
        recipients=[student['email']],
        body=f"""Dear {student['fullname']},

We have received your payment.

Payment ID     : {payment_id}
Amount Paid    : RM {amount}
Payment Method : {payment_method}

Thank you for your payment.
"""
    )

    try:
        mail.send(msg)
    except Exception as e:
        print(f"Failed to send receipt email: {e}")


# ==========================
# HELPER: Mark all selected items as paid
# Used by online_banking and ewallet (student self-service flow,
# items are stored in session from payment_summary). Needed because
# without this, paid fines/rentals/late fees would never get their
# payment_id set, so they'd keep showing up as unpaid forever and the
# same bill could be "paid" repeatedly.
# ==========================
def _mark_items_paid(conn, payment_id):
    # Mark damage fines
    for fine_id in session.get('fine_ids', []):
        conn.execute("UPDATE Fine SET payment_id = ? WHERE fine_id = ?", (payment_id, fine_id))

    # Mark standalone rental bills (no late payment)
    for rental_id in session.get('rental_ids', []):
        conn.execute("UPDATE Rental_Bill SET payment_id = ? WHERE rental_id = ?", (payment_id, rental_id))

    # Mark late payment rows AND their linked rental bill together
    for lp_id in session.get('late_payment_ids', []):
        lp = conn.execute("SELECT * FROM Late_Payment WHERE late_payment_id = ?", (lp_id,)).fetchone()
        if lp:
            conn.execute("UPDATE Late_Payment SET payment_id = ? WHERE late_payment_id = ?", (payment_id, lp_id))
            conn.execute("UPDATE Rental_Bill SET payment_id = ? WHERE rental_id = ?", (payment_id, lp['rental_id']))


# ==========================
# HELPER: Detect a duplicate/double-click submission
# True only if every item in the current payment session is already
# marked paid (or there's nothing left to charge) - a sign this request
# is a resubmit, not a genuine new payment, so the caller should not
# create a second Payment row for the same items.
# ==========================
def _items_already_paid(conn):
    fine_ids = session.get('fine_ids', [])
    rental_ids = session.get('rental_ids', [])
    late_payment_ids = session.get('late_payment_ids', [])

    if not (fine_ids or rental_ids or late_payment_ids):
        return True

    for fine_id in fine_ids:
        row = conn.execute("SELECT payment_id FROM Fine WHERE fine_id = ?", (fine_id,)).fetchone()
        if row and row['payment_id'] is None:
            return False
    for rental_id in rental_ids:
        row = conn.execute("SELECT payment_id FROM Rental_Bill WHERE rental_id = ?", (rental_id,)).fetchone()
        if row and row['payment_id'] is None:
            return False
    for lp_id in late_payment_ids:
        row = conn.execute("SELECT payment_id FROM Late_Payment WHERE late_payment_id = ?", (lp_id,)).fetchone()
        if row and row['payment_id'] is None:
            return False
    return True


def _clear_payment_session():
    for key in ('payment_start_time', 'fine_ids', 'rental_ids', 'late_payment_ids', 'total_amount',
                'selected_bank', 'selected_ewallet'):
        session.pop(key, None)


# ==========================
# HOME
# ==========================
@app.route('/', methods=['GET', 'POST'])
def home():

    return redirect('/user_login')


# User Login
@app.route("/user_login", methods=['GET', 'POST'])
def user_login():
    if 'email' in session:
        return redirect_by_role(session.get('role'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash("Email and password are required.","danger")
            return render_template('User Login.html')

        if not is_valid_email(email):
            flash("Please enter a valid email address.","danger")
            return render_template('User Login.html')

        conn = get_db()

        if email.endswith('@student.newinti.edu.my'):
            user = conn.execute(
                "SELECT * FROM Student WHERE email = ?", (email,)
            ).fetchone()

            if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                session['email']    = user['email']
                session['fullname'] = user['fullname']
                session['role']     = 'student'
                session['user_id']  = user['student_id']
                session['phone'] = user['phone']
                session['gender'] = user['gender']
                return redirect_by_role('student')

        else:
            user = conn.execute(
                "SELECT * FROM Staff WHERE email = ?", (email,)
            ).fetchone()

            if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                session['email']    = user['email']
                session['fullname'] = user['fullname']
                session['role']     = user['role']
                session['user_id']  = user['staff_id']
                session['phone'] = user['phone']

                return redirect_by_role(user['role'])

        flash("Invalid email or password.","danger")

    return render_template('User Login.html')


# ==========================
# FORGOT PASSWORD
# Step 1 — User enters email, reset link is sent
# ==========================
@app.route('/user_forgot_password', methods=['GET', 'POST'])
def user_forgot_password():
    message = ""
    success = False

    if request.method == 'POST':
        email = request.form.get('email', '').strip()

        if not email:
            message = "Please enter your email."
            return render_template('User Forgot Password.html', message=message, success=False)

        if not is_valid_email(email):
            message = "Please enter a valid email address."
            return render_template('User Forgot Password.html', message=message, success=False)

        try:
            table = resolve_table(email)
        except ValueError:
            # Still show generic message — don't reveal if email/table is invalid
            return render_template('User Forgot Password.html',
                                   message="If this email is registered, a reset link has been sent.",
                                   success=True)

        conn = get_db()
        account = conn.execute(
            f"SELECT * FROM {table} WHERE email = ?", (email,)
        ).fetchone()

        if account:
            token = generate_reset_token(email)
            conn.execute(
                f"UPDATE {table} SET reset_token = ?, reset_token_used = 0 WHERE email = ?",
                (token, email)
            )
            conn.commit()
            reset_link = url_for('user_reset_password', token=token, _external=True)
            send_reset_email(to_email=email, reset_link=reset_link)

        message = "If this email is registered, a password reset link has been sent to it."
        success = True

    return render_template('User Forgot Password.html', message=message, success=success)


# ==========================
# RESET PASSWORD
# Step 2 — User clicks the link from email
# ==========================
@app.route('/user_reset_password/<token>', methods=['GET', 'POST'])
def user_reset_password(token):
    email = verify_reset_token(token)

    if not email:
        flash("This reset link is invalid or has expired. Please request a new one.", "danger")
        return redirect('/user_forgot_password')

    try:
        table = resolve_table(email)
    except ValueError:
        flash("Account error. Please contact admin.", "danger")
        return redirect('/user_forgot_password')

    conn = get_db()
    account = conn.execute(
        f"SELECT * FROM {table} WHERE email = ?", (email,)
    ).fetchone()

    # Block if token doesn't match what was issued, or was already used
    if not account or account['reset_token'] != token or account['reset_token_used'] == 1:
        flash("This reset link is invalid or has already been used. Please request a new one.", "danger")
        return redirect('/user_forgot_password')

    message = ""

    if request.method == 'POST':
        new_password     = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        valid, pw_msg = is_valid_password(new_password)
        if not valid:
            return render_template('User Reset Password.html', token=token, message=pw_msg)

        if new_password != confirm_password:
            return render_template('User Reset Password.html', token=token, message="Passwords do not match.")

        conn = get_db()
        account = conn.execute(
            f"SELECT * FROM {table} WHERE email = ?", (email,)
        ).fetchone()

        if not account:
            flash("Account not found.", "danger")
            return redirect('/user_forgot_password')

        if bcrypt.checkpw(new_password.encode('utf-8'), account['password'].encode('utf-8')):
            return render_template('User Reset Password.html', token=token,
                                   message="New password must be different from the current one.")

        new_hash = bcrypt.hashpw(
            new_password.encode('utf-8'), bcrypt.gensalt(rounds=12)
        ).decode('utf-8')

        conn.execute(
            f"UPDATE {table} SET password = ?, reset_token_used = 1 WHERE email = ?",
            (new_hash, email)
        )
        conn.commit()

        session.clear()

        flash("Password reset successful! You can now log in.", "success")
        return redirect('/user_login')

    return render_template('User Reset Password.html', token=token, message=message)


# ==========================
# STUDENT APPLICATION
# ==========================
@app.route('/user_application', methods=['GET', 'POST'])
def user_application():
    if request.method == 'POST':
        fullname         = request.form.get('fullname', '').strip()
        email            = request.form.get('email', '').strip()
        password         = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        gender           = request.form.get('gender', '').strip()
        phone            = request.form.get('phone', '').strip()

        success = True
        if not all([fullname, email, password, confirm_password, gender, phone]):
            flash("All required fields must be filled.", "danger")
            success = False

        if not email.endswith('@student.newinti.edu.my'):
            flash("Please use your student email (e.g. name@student.newinti.edu.my).", "danger")
            success = False

        valid, pw_msg = is_valid_password(password)
        if not valid:
            flash(pw_msg, "danger")
            success = False

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            success = False

        if phone and not phone.isdigit():
            flash("Phone number must contain digits only.", "danger")
            success = False

        if phone and len(phone) < 10:
            flash("Phone number must be at least 10 digits.", "danger")
            success = False

        if success:
            conn = get_db()

            existing_application = conn.execute(
                "SELECT * FROM Application WHERE email = ?", (email,)
            ).fetchone()

            existing_student = conn.execute(
                "SELECT * FROM Student WHERE email = ?", (email,)
            ).fetchone()

            if existing_student:
                flash("This email is already registered. Please log in instead.", "danger")
                success = False

            if existing_application:
                if existing_application['status'] == 'pending':
                    flash("You have already submitted an application. Please wait for admin approval.", "danger")
                elif existing_application['status'] == 'rejected':
                    flash("Your previous application was rejected. Please contact the admin for further assistance.", "danger")
                success = False

            if success:
                hashed_password = bcrypt.hashpw(
                    password.encode('utf-8'), bcrypt.gensalt(rounds=12)
                ).decode('utf-8')

                conn.execute("""
                    INSERT INTO Application
                    (fullname, email, password, gender, phone, status)
                    VALUES (?, ?, ?, ?, ?, 'pending')
                """, (fullname, email, hashed_password, gender, phone))

                conn.commit()
                flash("Application submitted successfully!", "success")
                return redirect(url_for('user_application'))

    return render_template('User Application.html')

# ==========================
# LOGOUT
# ==========================
@app.route('/user_logout')
def user_logout():
    session.clear()
    return redirect('/user_login')


@app.route("/admin_dashboard")
def admin_dashboard():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()
    total_application = conn.execute("""
        SELECT COUNT(*)
        FROM Application
    """).fetchone()[0]

    pending_application = conn.execute("""
        SELECT COUNT(*)
        FROM Application
        WHERE status = "pending"
    """).fetchone()[0]

    approved_application = conn.execute("""
        SELECT COUNT(*)
        FROM Application
        WHERE status = "approved"
    """).fetchone()[0]

    rejected_application = conn.execute("""
        SELECT COUNT(*)
        FROM Application
        WHERE status = "rejected"
    """).fetchone()[0]

    total_room = conn.execute("""
        SELECT COUNT(*) FROM Room
    """).fetchone()[0]

    available_room = conn.execute("""
        SELECT COUNT(*)
        FROM Room
        WHERE (
            SELECT COUNT(*)
            FROM Rental_Bill
            WHERE Rental_Bill.room_id = Room.room_id
            AND start_date <= DATE('now')
            AND end_date >= DATE('now')
        ) < capacity
    """).fetchone()[0]

    total_students = conn.execute("""
        SELECT COUNT(*) FROM Student
    """).fetchone()[0]

    total_maintenance = conn.execute("""
        SELECT COUNT(*) FROM Maintenance
    """).fetchone()[0]


    rental_bill = conn.execute("""
        SELECT SUM(amount) FROM Rental_Bill
        WHERE payment_id IS NULL
    """).fetchone()[0]
    fine = conn.execute("""
        SELECT SUM(amount) FROM Fine
        WHERE payment_id IS NULL
    """).fetchone()[0]
    late_payment = conn.execute("""
        SELECT SUM(amount) FROM Late_Payment
        WHERE payment_id IS NULL
    """).fetchone()[0]
    total_due_payment = (rental_bill or 0) + (fine or 0) + (late_payment or 0)

    total_revenue = conn.execute("""
        SELECT SUM(amount) FROM Payment
    """).fetchone()[0] or 0

    occupied_room = total_room - available_room
    return render_template("Admin Dashboard.html",
                           total_application=total_application, pending_application=pending_application,
                           approved_application=approved_application,rejected_application=rejected_application,
                           total_room=total_room, occupied_room=occupied_room,
                           available_room=available_room,total_students=total_students,
                           total_maintenance=total_maintenance,total_due_payment=total_due_payment,
                           total_revenue=total_revenue)


@app.route("/admin_user_list_application")
def admin_user_list_application():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()

    table_data = conn.execute("""
        SELECT *
        FROM Application
        ORDER BY created_at DESC
    """).fetchall()

    return render_template("Admin User List Application.html",table_data=table_data)


# ==========================
# APPROVE APPLICATION (Admin)
# ==========================
@app.route("/admin_user_list_application_approve")
def admin_user_list_application_approve():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')

    application_id = request.args.get("application_id","")
    conn = get_db()
    application = conn.execute(
        "SELECT * FROM Application WHERE application_id = ?", (application_id,)
    ).fetchone()
    student_id = application["email"].split('@')[0]
    conn.execute("""
        INSERT INTO Student
        (student_id, fullname, email, password, gender, phone, application_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        student_id,
        application['fullname'],
        application['email'],
        application['password'],
        application['gender'],
        application['phone'],
        application_id
    ))

    conn.execute(
        "UPDATE Application SET status = 'approved' WHERE application_id = ?",
        (application_id,)
    )
    conn.commit()

    send_application_email(
        to_email  = application['email'],
        fullname  = application['fullname'],
        status    = 'approved',
        login_url = url_for('user_login', _external=True)
    )

    flash("Application approved and student account created.", "success")
    return redirect('/admin_user_list_application')


# ==========================
# REJECT APPLICATION (Admin)
# ==========================
@app.route('/admin_user_list_application_reject')
def admin_user_list_application_reject():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')

    application_id = request.args.get("application_id","")
    conn = get_db()
    application = conn.execute(
        "SELECT * FROM Application WHERE application_id = ?", (application_id,)
    ).fetchone()

    conn.execute(
        "UPDATE Application SET status = 'rejected' WHERE application_id = ?",
        (application_id,)
    )
    conn.commit()

    send_application_email(
        to_email = application['email'],
        fullname = application['fullname'],
        status   = 'rejected'
    )

    flash("Application rejected.", "warning")
    return redirect('/admin_user_list_application')


@app.route("/admin_user_list_staff")
def admin_user_list_staff():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()
    table_data = conn.execute("""
            SELECT *
            FROM Staff
        """).fetchall()

    return render_template("Admin User List Staff.html",table_data=table_data)


@app.route("/admin_user_list_staff_add", methods=["GET", "POST"])
def admin_user_list_staff_add():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()

    if request.method == "POST":
        fullname       = request.form.get("fullname", "").strip()
        email     = request.form.get("email", "").strip()
        role = request.form.get("role", "").strip()
        phone      = request.form.get("phone", "").strip()
        password = "warden123"

        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'), bcrypt.gensalt(rounds=12)
        ).decode('utf-8')

        if not fullname or not email or not role or not phone:
            flash("All fields are required.", "danger")
        else:
            conn.execute("""
                INSERT INTO Staff (fullname, email, password, role, phone)
                VALUES (?, ?, ?, ?, ?)
            """, (fullname, email, hashed_password, role, phone))
            conn.commit()
            flash("Staff added successfully.", "success")
            return redirect("/admin_user_list_staff")

    return render_template("Admin User List Staff Add.html")


@app.route("/admin_user_list_student")
def admin_user_list_student():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()
    search_data = request.args.get("search_data", "")

    if search_data:
        table_data = conn.execute("""
            SELECT *
            FROM Student
            WHERE student_id = ?
        """, (search_data,)).fetchall()
    else:
        table_data = conn.execute("""
            SELECT *
            FROM Student
        """).fetchall()

    return render_template("Admin User List Student.html", table_data=table_data, search_data=search_data)


@app.route("/admin_user_list_student_edit",methods=["GET", "POST"])
def admin_user_list_student_edit():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()

    if request.method == "POST":
        student_id    = request.form.get("student_id", "").strip()
        fullname     = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip()
        gender      = request.form.get("gender", "").strip()
        phone      = request.form.get("phone", "").strip()

        if not fullname or not email or not gender or not phone:
            flash("All fields are required.", "danger")
            return redirect(f"/admin_user_list_student_edit?student_id={student_id}")

        conn.execute("""
            UPDATE Student
            SET fullname = ?, email = ?, gender = ?, phone = ?
            WHERE student_id = ?
        """, (fullname, email, gender, phone, student_id))
        conn.commit()

        flash("Student updated successfully.", "success")
        return redirect("/admin_user_list_student")

    student_id = request.args.get("student_id", "")
    row = conn.execute("""
        SELECT * FROM Student
        WHERE student_id = ?
    """, (student_id,)).fetchone()

    if not row:
        return redirect("/admin_user_list_student")

    return render_template("Admin User List Student Edit.html", row=row)


@app.route("/admin_room")
def admin_room():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()
    search_room = request.args.get("search_room", "")

    if search_room:
        table_data = conn.execute("""
            SELECT *
            FROM Room
            WHERE room_id = ?
        """, (search_room,)).fetchall()
    else:
        table_data = conn.execute("""
            SELECT *
            FROM Room
        """).fetchall()

    return render_template("Admin Room.html", table_data=table_data, search_room=search_room)


@app.route("/admin_room_edit", methods=["GET", "POST"])
def admin_room_edit():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()

    if request.method == "POST":
        room_id       = request.form.get("room_id", "").strip()
        room_type     = request.form.get("room_type", "").strip()
        fee_per_month = request.form.get("fee_per_month", "").strip()
        capacity      = request.form.get("capacity", "").strip()

        if not room_type or not fee_per_month or not capacity:
            flash("All fields are required.", "danger")
            return redirect(f"/admin_room_edit?room_id={room_id}")

        conn.execute("""
            UPDATE Room
            SET room_type = ?, fee_per_month = ?, capacity = ?
            WHERE room_id = ?
        """, (room_type, fee_per_month, capacity, room_id))
        conn.commit()

        flash("Room updated successfully.", "success")
        return redirect("/admin_room")

    room_id = request.args.get("room_id", "")
    row = conn.execute("""
        SELECT * FROM Room
        WHERE room_id = ?
    """, (room_id,)).fetchone()

    if not row:
        return redirect("/admin_room")

    return render_template("Admin Room Edit.html", row=row)


@app.route("/admin_room_delete", methods=["POST"])
def admin_room_delete():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    room_id = request.form.get("room_id", "")
    conn = get_db()
    try:
        conn.execute("DELETE FROM Room WHERE room_id = ?", (room_id,))
        conn.commit()
        flash("Room deleted successfully.", "success")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash("Cannot delete room — it is currently in use.", "danger")
    return redirect("/admin_room")


@app.route("/admin_room_add", methods=["GET", "POST"])
def admin_room_add():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()

    if request.method == "POST":
        room_id       = request.form.get("room_id", "").strip()
        room_type     = request.form.get("room_type", "").strip()
        fee_per_month = request.form.get("fee_per_month", "").strip()
        capacity      = request.form.get("capacity", "").strip()

        if not room_id or not room_type or not fee_per_month or not capacity:
            flash("All fields are required.", "danger")
        else:
            try:
                conn.execute("""
                    INSERT INTO Room (room_id, room_type, fee_per_month, capacity)
                    VALUES (?, ?, ?, ?)
                """, (room_id, room_type, fee_per_month, capacity))
                conn.commit()
                flash("Room added successfully.", "success")
                return redirect("/admin_room")
            except sqlite3.IntegrityError:
                conn.rollback()
                flash("Room ID already exists.", "danger")

    return render_template("Admin Room Add.html")


@app.route("/admin_analytics_date", methods=["GET","POST"])
def admin_analytics_date():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    if request.method == "POST":
        session["start_date"] = request.form["start_date"]
        session["end_date"] = request.form["end_date"]
        return redirect("/admin_analytics_application_form")

    return render_template("Admin Analytics Date.html")


@app.route("/admin_analytics_application_form")
def admin_analytics_application_form():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    start_date = session.get("start_date", "")
    end_date = session.get("end_date", "")

    if not start_date or not end_date:
        return redirect("/")

    conn = get_db()

    status_data = [list(row) for row in conn.execute("""
        SELECT status, COUNT(*) as total
        FROM Application
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY status
    """, (start_date, end_date)).fetchall()]

    timeline_data = [list(row) for row in conn.execute("""
        SELECT strftime('%Y-%m', created_at), COUNT(*)
        FROM Application
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY strftime('%Y-%m', created_at)
    """, (start_date, end_date)).fetchall()]

    table_data = conn.execute("""
        SELECT *
        FROM Application
        WHERE DATE(created_at) BETWEEN ? AND ?
        ORDER BY created_at
    """, (start_date, end_date)).fetchall()

    return render_template("Admin Analytics Application Form.html", start_date=start_date, end_date=end_date, status_data=status_data, timeline_data = timeline_data, table_data=table_data)


@app.route("/admin_analytics_maintenance_request")
def admin_analytics_maintenance_request():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    start_date = session.get("start_date", "")
    end_date = session.get("end_date", "")

    if not start_date or not end_date:
        return redirect("/")

    conn = get_db()

    status_data = [list(row) for row in conn.execute("""
        SELECT status, COUNT(*) as total
        FROM Maintenance
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY status
    """, (start_date, end_date)).fetchall()]

    timeline_data = [list(row) for row in conn.execute("""
        SELECT strftime('%Y-%m', created_at), COUNT(*)
        FROM Maintenance
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY strftime('%Y-%m', created_at)
    """, (start_date, end_date)).fetchall()]

    table_data = conn.execute("""
        SELECT *
        FROM Maintenance
        WHERE DATE(created_at) BETWEEN ? AND ?
        ORDER BY created_at
    """, (start_date, end_date)).fetchall()

    return render_template("Admin Analytics Maintenance Request.html",start_date = start_date, end_date = end_date, status_data=status_data, timeline_data = timeline_data, table_data=table_data)


@app.route("/admin_analytics_revenue")
def admin_analytics_revenue():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    start_date = session.get("start_date", "")
    end_date = session.get("end_date", "")

    if not start_date or not end_date:
        return redirect("/")

    conn = get_db()

    status_data = [list(row) for row in conn.execute("""
        SELECT
            CASE
                WHEN payment_id IS NOT NULL THEN 'paid'
                WHEN end_date < DATE('now') THEN 'overdue'
                ELSE 'unpaid'
            END AS status,
            SUM(amount) as total
        FROM Rental_Bill
        WHERE DATE(start_date) BETWEEN ? AND ?
        GROUP BY status
    """, (start_date, end_date)).fetchall()]

    # Line chart — total payment amount collected per month
    timeline_data = [list(row) for row in conn.execute("""
        SELECT strftime('%Y-%m', created_at), SUM(amount)
        FROM Payment
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY strftime('%Y-%m', created_at)
    """, (start_date, end_date)).fetchall()]

    table_data = conn.execute("""
        SELECT *
        FROM Payment
        WHERE DATE(created_at) BETWEEN ? AND ?
        ORDER BY created_at
    """, (start_date, end_date)).fetchall()

    return render_template("Admin Analytics Revenue.html",start_date = start_date, end_date = end_date, status_data=status_data, timeline_data = timeline_data, table_data=table_data)


@app.route("/new_date")
def new_date():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    session.pop("start_date", None)
    session.pop("end_date", None)
    return redirect("/")


@app.route("/admin_due_payment")
def admin_due_payment():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    conn = get_db()
    search_data = request.args.get("search_data","")

    if search_data:
        table_data = conn.execute("""
            SELECT
            s.student_id,
            s.fullname,
            s.email,
            SUM(d.amount) AS total_due
            FROM Student s
            JOIN (
                SELECT student_id, amount FROM Rental_Bill WHERE payment_id IS NULL
                UNION ALL
                SELECT student_id, amount FROM Fine WHERE payment_id IS NULL
            ) d ON d.student_id = s.student_id
            WHERE s.student_id = ?
            GROUP BY s.student_id 
            """,(search_data,)).fetchall()
    else:
        table_data = conn.execute("""
            SELECT
            s.student_id,
            s.fullname,
            s.email,
            SUM(d.amount) AS total_due
            FROM Student s
            JOIN (
                SELECT student_id, amount FROM Rental_Bill WHERE payment_id IS NULL
                UNION ALL
                SELECT student_id, amount FROM Fine WHERE payment_id IS NULL
            ) d ON d.student_id = s.student_id
            GROUP BY s.student_id;  
            """).fetchall()

    return render_template("Admin Due Payment.html",table_data=table_data,search_data=search_data)


@app.route("/admin_announcement_page")
def admin_announcement_page():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login') 
    
    conn = get_db()

    search_date = request.args.get("search_date", "")
    if search_date:
        table_data = conn.execute("""
            SELECT a.announcement_id, a.title, a.description, a.created_at,
                   s.fullname AS staff_name,
                   a.audience,
                   st.fullname AS recipient_name
            FROM Announcement a
            JOIN Staff s ON a.staff_id = s.staff_id
            LEFT JOIN Announcement_Recipient ar ON a.announcement_id = ar.announcement_id
            LEFT JOIN Student st ON ar.student_id = st.student_id
            WHERE DATE(a.created_at) = ?
            ORDER BY a.created_at DESC
        """, (search_date,)).fetchall()
    else:
        table_data = conn.execute("""
            SELECT a.announcement_id, a.title, a.description, a.created_at,
                   s.fullname AS staff_name,
                   a.audience,
                   st.fullname AS recipient_name
            FROM Announcement a
            JOIN Staff s ON a.staff_id = s.staff_id
            LEFT JOIN Announcement_Recipient ar ON a.announcement_id = ar.announcement_id
            LEFT JOIN Student st ON ar.student_id = st.student_id
            ORDER BY a.created_at DESC
        """).fetchall()

    return render_template("Admin Announcement Page.html", table_data=table_data, search_date=search_date)


@app.route("/admin_announcement_add", methods=["GET", "POST"])
def admin_announcement_add():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login') 
    
    conn = get_db()

    if request.method == "POST":
        title          = request.form.get("title", "").strip()
        description    = request.form.get("description", "").strip()
        audience       = request.form.get("audience", "all")
        student_id     = request.form.get("student_id", "").strip()

        if not title or not description:
            flash("Title and description are required.", "danger")
        elif audience == "one" and not student_id:
            flash("Please select a student.", "danger")
        else:
            staff_id = session.get('user_id')

            try:
                cursor = conn.execute(
                    "INSERT INTO Announcement (title, description, audience, staff_id) VALUES (?, ?, ?, ?)",
                    (title, description, audience, staff_id)
                )
                announcement_id = cursor.lastrowid
                if audience == "one":
                    conn.execute(
                        "INSERT INTO Announcement_Recipient (announcement_id, student_id) VALUES (?, ?)",
                        (announcement_id, student_id)
                    )
                conn.commit()
                flash("Announcement sent successfully.", "success")
                return redirect("/admin_announcement_page")
            except sqlite3.IntegrityError:
                conn.rollback()
                flash("Student ID does not exist.", "danger")

    students = conn.execute(
        "SELECT student_id, fullname FROM Student ORDER BY fullname"
    ).fetchall()
    return render_template("Admin Announcement Add.html", students=students)


@app.route("/admin_announcement_view")
def admin_announcement_view():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    announcement_id = request.args.get("announcement_id", "")
    conn = get_db()
    row = conn.execute("""
        SELECT a.announcement_id, a.title, a.description, a.created_at,
               s.fullname AS staff_name
        FROM Announcement a
        JOIN Staff s ON a.staff_id = s.staff_id
        WHERE a.announcement_id = ?
    """, (announcement_id,)).fetchone()

    if not row:
        return redirect("/admin_announcement_page")

    return render_template("Admin Announcement View.html", row=row)


@app.route("/admin_announcement_delete", methods=["POST"])
def admin_announcement_delete():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')
    
    announcement_id = request.form.get("announcement_id", "")

    conn = get_db()
    conn.execute("DELETE FROM Announcement_Recipient WHERE announcement_id = ?", (announcement_id,))
    conn.execute("DELETE FROM Announcement WHERE announcement_id = ?", (announcement_id,))
    conn.commit()
    flash("Announcement Deleted Successfully","success")

    return redirect("/admin_announcement_page")


@app.route("/admin_profile")
def admin_profile():
    if session.get('user_id') is None or session.get('role') != 'admin':
        return redirect('/user_login')

    return render_template("Admin Profile.html")


@app.route("/student_dashboard")
def student_dashboard():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    conn = get_db()
    student_id = session.get('user_id')

    total_announcement = conn.execute("""
        SELECT COUNT(*)
        FROM Announcement a
        LEFT JOIN Announcement_Recipient ar
            ON ar.announcement_id = a.announcement_id
           AND ar.student_id = ?
        WHERE a.audience = 'all'
           OR (a.audience = 'one' AND ar.student_id IS NOT NULL)
    """, (student_id,)).fetchone()[0]

    student = conn.execute(
        "SELECT last_read_announcement_at FROM Student WHERE student_id = ?",
        (student_id,)
    ).fetchone()
    last_read = student['last_read_announcement_at']

    # Unread 'all' announcements
    unread_all = conn.execute("""
        SELECT COUNT(*) FROM Announcement
        WHERE audience = 'all'
          AND (? IS NULL OR created_at > ?)
    """, (last_read, last_read)).fetchone()[0]

    # Unread 'one' (specific) announcements
    unread_one = conn.execute("""
        SELECT COUNT(*) FROM Announcement_Recipient
        WHERE student_id = ? AND is_read = 0
    """, (student_id,)).fetchone()[0]

    unread_announcement = unread_all + unread_one

    due_rental_fees = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM Rental_Bill
        WHERE student_id = ? AND payment_id IS NULL
    """, (student_id,)).fetchone()[0]

    due_fines = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM Fine
        WHERE student_id = ? AND payment_id IS NULL
    """, (student_id,)).fetchone()[0]

    total_due_payment = due_rental_fees + due_fines

    total_request = conn.execute(
        "SELECT COUNT(*) FROM Maintenance WHERE student_id = ?", (student_id,)
    ).fetchone()[0]

    pending_request = conn.execute(
        "SELECT COUNT(*) FROM Maintenance WHERE student_id = ? AND status = 'pending'",
        (student_id,)
    ).fetchone()[0]

    in_progress_request = conn.execute(
        "SELECT COUNT(*) FROM Maintenance WHERE student_id = ? AND status = 'in-progress'",
        (student_id,)
    ).fetchone()[0]

    completed_request = conn.execute(
        "SELECT COUNT(*) FROM Maintenance WHERE student_id = ? AND status = 'resolved'",
        (student_id,)
    ).fetchone()[0]

    return render_template(
        'Student Dashboard.html',
        total_announcement=total_announcement,
        unread_announcement=unread_announcement,
        due_rental_fees=due_rental_fees,
        due_fines=due_fines,
        total_due_payment=total_due_payment,
        total_request=total_request,
        pending_request=pending_request,
        in_progress_request=in_progress_request,
        completed_request=completed_request
    )


@app.route("/student_due_payment")
def student_due_payment():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    check_late_payments(session['user_id'])

    month = request.args.get('month','')
    year = request.args.get('year','')
    status = request.args.get('status','')

    conn = get_db()

    query = "SELECT * FROM Fine WHERE student_id = ?"
    params = [session['user_id']]

    if month:
        query += " AND strftime('%m', created_at) = ?"
        params.append(month)

    if year:
        query += " AND strftime('%Y', created_at) = ?"
        params.append(year)

    if status == 'paid':
        query += " AND payment_id IS NOT NULL"
    elif status == 'unpaid':
        query += " AND payment_id IS NULL"

    fines = conn.execute(query, params).fetchall()

    return render_template('Student Due Payment.html',
                           fines=fines,
                           month=month,
                           year=year,
                           status=status)


# ==========================
# RENTAL FEES PAGE
# Shows rental bills + their associated late payment (if any)
# ==========================
@app.route('/student_due_payment_rental')
def student_due_payment_rental():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')

    month = request.args.get('month','')
    year = request.args.get('year','')
    status = request.args.get('status','')

    conn = get_db()

    query = "SELECT * FROM Rental_Bill WHERE student_id = ?"
    params = [session['user_id']]

    if month:
        query += " AND strftime('%m', start_date) = ?"
        params.append(month)

    if year:
        query += " AND strftime('%Y', start_date) = ?"
        params.append(year)

    if status == 'paid':
        query += " AND payment_id IS NOT NULL"
    elif status == 'unpaid':
        query += " AND payment_id IS NULL"

    rentals = conn.execute(query, params).fetchall()

    # Fetch all late payments for this student's rentals (paid and unpaid)
    late_payments = conn.execute("""
        SELECT Late_Payment.*
        FROM Late_Payment
        JOIN Rental_Bill ON Late_Payment.rental_id = Rental_Bill.rental_id
        WHERE Rental_Bill.student_id = ?
    """, (session['user_id'],)).fetchall()

    # Build a lookup: rental_id -> late_payment row
    late_payment_map = {lp['rental_id']: lp for lp in late_payments}

    late_summary = get_total_late_days(session['user_id'])

    return render_template('Student Due Payment Rental.html',
                           rentals=rentals,
                           late_payment_map=late_payment_map,
                           late_summary=late_summary,
                           month=month,
                           year=year,
                           status=status)


# ==========================
# PAYMENT SUMMARY PAGE
# Total = rental amount + late fee (stored separately, added here)
# ==========================
@app.route('/student_due_payment_summary', methods=['POST'])
def student_due_payment_summary():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')

    fine_ids = request.form.getlist('fine_ids')
    rental_ids = request.form.getlist('rental_ids')
    late_payment_ids = request.form.getlist('late_payment_ids')

    if not fine_ids and not rental_ids and not late_payment_ids:
        flash(message='Please select at least one item to pay.', category='danger')
        return redirect(request.referrer)

    conn = get_db()
    selected_fines = []
    selected_rentals = []
    selected_late_payments = []
    total_amount = 0

    for fine_id in fine_ids:
        fine = conn.execute("SELECT * FROM Fine WHERE fine_id = ? AND student_id = ?", (fine_id, session['user_id'])).fetchone()
        if fine:
            selected_fines.append(fine)
            total_amount += fine['amount']

    for rental_id in rental_ids:
        rental = conn.execute("SELECT * FROM Rental_Bill WHERE rental_id = ? AND student_id = ?", (rental_id, session['user_id'])).fetchone()
        if rental:
            unpaid_late_fee = conn.execute("""
                SELECT * FROM Late_Payment
                WHERE rental_id = ? AND payment_id IS NULL
            """, (rental_id,)).fetchone()
            if unpaid_late_fee:
                conn.close()
                flash(message='This rental has an unpaid late fee and must be paid together with it.', category='danger')
                return redirect(request.referrer)

            selected_rentals.append(rental)
            total_amount += rental['amount']

    for lp_id in late_payment_ids:
        lp = conn.execute("""
            SELECT Late_Payment.*, Rental_Bill.amount AS rental_amount
            FROM Late_Payment
            JOIN Rental_Bill ON Late_Payment.rental_id = Rental_Bill.rental_id
            WHERE Late_Payment.late_payment_id = ? AND Rental_Bill.student_id = ?
        """, (lp_id, session['user_id'])).fetchone()
        if lp:
            selected_late_payments.append(lp)
            # Total = rental bill amount + late fee amount
            total_amount += lp['rental_amount'] + lp['amount']

    session['fine_ids'] = fine_ids
    session['rental_ids'] = rental_ids
    session['late_payment_ids'] = late_payment_ids
    session['total_amount'] = total_amount

    return render_template('Student Due Payment Summary.html',
                           selected_fines=selected_fines,
                           selected_rentals=selected_rentals,
                           selected_late_payments=selected_late_payments,
                           total_amount=total_amount)


# ==========================
# PAYMENT PAGE
# ==========================
@app.route('/student_due_payment_method', methods=['GET', 'POST'])
def student_due_payment_method():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    if request.method == 'POST':
        payment_method = request.form['payment_method']

        session['payment_start_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if payment_method == 'online_banking':
            return redirect('/student_due_payment_method_online_banking')
        elif payment_method == 'ewallet':
            return redirect('/student_due_payment_method_ewallet')
        else:
            flash(message='Please select a payment method.', category='danger')
            return redirect('/student_due_payment_method')

    return render_template('Student Due Payment Method.html', total_amount=session.get('total_amount', 0))


# ==========================
# ONLINE BANKING
# ==========================
@app.route('/student_due_payment_method_online_banking', methods=['GET', 'POST'])
def student_due_payment_method_online_banking():
    if session.get('role') != 'student':
        return redirect('/user_login')
    
    if 'user_id' not in session:
        flash(message='Your session has expired. Please log in again.', category='danger')
        return redirect('/')

    if not check_payment_timeout():
        flash(message='Payment session expired. Please try again.', category='danger')
        return redirect('/student_due_payment_method')

    total_amount = session.get('total_amount', 0)
    if total_amount <= 0:
        flash(message='No items selected to pay.', category='danger')
        return redirect('/student_due_payment')

    if request.method == 'POST':
        bank = request.form.get('bank', '').strip()
        if not bank:
            flash(message='Please select a bank.', category='danger')
            return redirect('/student_due_payment_method_online_banking')

        session['selected_bank'] = bank
        return redirect('/student_due_payment_method_online_banking_portal')

    return render_template('Student Due Payment Method Online Banking.html', total_amount=total_amount)


@app.route("/student_due_payment_method_online_banking_portal", methods=['GET', 'POST'])
def student_due_payment_method_online_banking_portal():
    if session.get('role') != 'student':
        return redirect('/user_login')

    if 'user_id' not in session:
        return redirect('/')

    if not check_payment_timeout():
        flash(message='Payment session expired. Please try again.', category='danger')
        return redirect('/student_due_payment_method')

    bank = session.get('selected_bank')
    if not bank:
        flash(message='No bank selected.', category='danger')
        return redirect('/student_due_payment_method_online_banking')

    total_amount = session.get('total_amount', 0)

    if request.method == 'POST':
        account_number = request.form.get('account_number', '').strip()

        if not account_number.isdigit() or not (6 <= len(account_number) <= 20):
            flash(message='Account number must be digits only (6-20 characters).', category='danger')
            return redirect('/student_due_payment_method_online_banking_portal')

        conn = get_db()

        if _items_already_paid(conn):
            flash(message='These items have already been paid.', category='danger')
            _clear_payment_session()
            return redirect('/student_due_payment')

        try:
            payment_id = conn.execute("""
                INSERT INTO Payment (student_id, amount, payment_method)
                VALUES (?, ?, ?)
            """, (session['user_id'], total_amount, 'online_banking')).lastrowid

            _mark_items_paid(conn, payment_id)
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(message='Payment could not be processed. Please try again.', category='danger')
            return redirect('/student_due_payment_method_online_banking_portal')

        send_payment_receipt_email(conn, session['user_id'], payment_id, total_amount, 'Online Banking')
        _clear_payment_session()

        return redirect(url_for('receipt',
                                payment_id=payment_id,
                                payment_method='Online Banking',
                                bank=bank,
                                account_number=account_number,
                                amount=total_amount))

    return render_template('Student Due Payment Method Online Banking Portal.html', bank=bank, total_amount=total_amount)


# ==========================
# EWALLET
# ==========================
@app.route('/student_due_payment_method_ewallet', methods=['GET', 'POST'])
def student_due_payment_method_ewallet():
    if session.get('role') != 'student':
        return redirect('/user_login')
    
    if 'user_id' not in session:
        flash(message='Your session has expired. Please log in again.', category='danger')
        return redirect('/')

    if not check_payment_timeout():
        flash(message='Payment session expired. Please try again.', category='danger')
        return redirect('/student_due_payment_method')

    total_amount = session.get('total_amount', 0)
    if total_amount <= 0:
        flash(message='No items selected to pay.', category='danger')
        return redirect('/student_due_payment')

    if request.method == 'POST':
        ewallet_name = request.form.get('ewallet', '').strip()
        if not ewallet_name:
            flash(message='Please select an e-wallet.', category='danger')
            return redirect('/student_due_payment_method_ewallet')

        session['selected_ewallet'] = ewallet_name
        return redirect('/student_due_payment_method_ewallet_portal')

    return render_template('Student Due Payment Method Ewallet.html', total_amount=total_amount)


# ==========================
# EWALLET PORTAL
# ==========================
@app.route('/student_due_payment_method_ewallet_portal', methods=['GET', 'POST'])
def student_due_payment_method_ewallet_portal():
    if session.get('role') != 'student':
        return redirect('/user_login')
    
    if 'user_id' not in session:
        return redirect('/')

    if not check_payment_timeout():
        flash(message='Payment session expired. Please try again.', category='danger')
        return redirect('/student_due_payment_method')

    ewallet_name = session.get('selected_ewallet')
    if not ewallet_name:
        flash(message='No e-wallet selected.', category='danger')
        return redirect('/student_due_payment_method_ewallet')

    total_amount = session.get('total_amount', 0)

    if request.method == 'POST':

        conn = get_db()

        if _items_already_paid(conn):
            flash(message='These items have already been paid.', category='danger')
            _clear_payment_session()
            return redirect('/student_due_payment')

        try:
            payment_id = conn.execute("""
                INSERT INTO Payment (student_id, amount, payment_method)
                VALUES (?, ?, ?)
            """, (session['user_id'], total_amount, 'e-wallet')).lastrowid

            _mark_items_paid(conn, payment_id)
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(message='Payment could not be processed. Please try again.', category='danger')
            return redirect('/student_due_payment_method_ewallet_portal')

        send_payment_receipt_email(conn, session['user_id'], payment_id, total_amount, 'E-Wallet')
        _clear_payment_session()

        return redirect(url_for('receipt',
                                payment_id=payment_id,
                                payment_method='E-Wallet',
                                ewallet=ewallet_name,
                                amount=total_amount))

    return render_template('Student Due Payment Method Ewallet Portal.html', ewallet_name=ewallet_name, total_amount=total_amount)


# ==========================
# RECEIPT PAGE
# Shown immediately after online banking / e-wallet payment.
# ==========================
@app.route('/receipt')
def receipt():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    payment_id = request.args.get('payment_id')
    payment_method = request.args.get('payment_method')
    bank = request.args.get('bank')
    account_number = request.args.get('account_number')
    ewallet = request.args.get('ewallet')
    amount = request.args.get('amount')

    return render_template('receipt.html',
                           payment_id=payment_id,
                           payment_method=payment_method,
                           bank=bank,
                           account_number=account_number,
                           ewallet=ewallet,
                           amount=amount)


# ==========================
# DOWNLOAD RECEIPT AS PDF
# ==========================
@app.route('/download_receipt/<int:payment_id>')
def download_receipt(payment_id):
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    conn = get_db()
    payment = conn.execute("SELECT * FROM Payment WHERE payment_id = ?", (payment_id,)).fetchone()

    if not payment:
        flash(message='Receipt not found.', category='danger')
        return redirect('/student_due_payment')

    pdf_buffer = io.BytesIO()
    pdf = canvas.Canvas(pdf_buffer)
    width = 612

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(width / 2, 750, "PAYMENT RECEIPT")
    pdf.line(50, 735, width - 50, 735)

    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 700, "Payment ID")
    pdf.drawString(200, 700, str(payment['payment_id']))

    pdf.drawString(50, 670, "Student ID")
    pdf.drawString(200, 670, str(payment['student_id']))

    pdf.drawString(50, 640, "Payment Method")
    pdf.drawString(200, 640, payment['payment_method'])

    pdf.drawString(50, 610, "Amount Paid")
    pdf.drawString(200, 610, f"RM {payment['amount']:.2f}")

    pdf.drawString(50, 580, "Payment Date")
    pdf.drawString(200, 580, payment['created_at'])

    pdf.drawCentredString(width / 2, 520, "Thank you for your payment.")

    pdf.save()
    pdf_buffer.seek(0)

    return send_file(pdf_buffer,
                     as_attachment=True,
                     download_name="payment_receipt.pdf",
                     mimetype='application/pdf')


@app.route("/student_announcement")
def student_announcement():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')

    conn = get_db()
    student_id = session.get('user_id')
    conn.execute("""
        UPDATE Student SET last_read_announcement_at = CURRENT_TIMESTAMP
        WHERE student_id = ?
    """, (student_id,))
    conn.execute("""
        UPDATE Announcement_Recipient SET is_read = 1
        WHERE student_id = ?
    """, (student_id,))
    conn.commit()

    table_data = conn.execute("""
        SELECT a.announcement_id,a.title,a.description, st.fullname AS posted_by, a.created_at
        FROM Announcement a
        JOIN Staff st ON st.staff_id = a.staff_id
        WHERE a.audience = 'all'
           OR a.announcement_id IN (
               SELECT announcement_id FROM Announcement_Recipient WHERE student_id = ?
           )
        ORDER BY a.created_at DESC
    """, (student_id,)).fetchall()

    return render_template('Student Announcement.html', table_data=table_data)



@app.route("/student_announcement_view")
def student_announcement_view():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')

    announcement_id = request.args.get("announcement_id", "")
    conn = get_db()
    row = conn.execute("""
        SELECT a.announcement_id, a.title, a.description, a.created_at,
               s.fullname AS staff_name
        FROM Announcement a
        JOIN Staff s ON a.staff_id = s.staff_id
        WHERE a.announcement_id = ?
    """, (announcement_id,)).fetchone()

    if not row:
        return redirect("/student_announcement")

    return render_template("Student Announcement View.html", row=row)


@app.route("/student_book_room", methods=['GET', 'POST'])
def student_book_room():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    conn = get_db()
    today = date.today().isoformat()

    form = None
    selected_room = None
    end_date = None
    total_fee = None
    rooms = []

    student_gender = session.get('gender')

    if request.method == 'POST':
        form = {
            'start_date': request.form.get('start_date', '').strip(),
            'duration':   request.form.get('duration', '').strip(),
            'room_id':    request.form.get('room_id', '').strip(),
        }

        if form['start_date'] and form['duration']:
            end_date = conn.execute(
                "SELECT date(?, '+' || ? || ' months', '-1 day')",
                (form['start_date'], form['duration'])
            ).fetchone()[0]

            room_rows = conn.execute("""
                SELECT r.*,
                       COUNT(DISTINCT rb.student_id) AS occupancy,
                       COUNT(DISTINCT rb.student_id) >= r.capacity AS is_full,
                       SUM(CASE WHEN s.gender IS NOT NULL AND s.gender != ? THEN 1 ELSE 0 END) > 0 AS is_gender_blocked,
                       MAX(CASE WHEN s.gender IS NOT NULL AND s.gender != ? THEN s.gender END) AS conflicting_gender
                FROM Room r
                LEFT JOIN Rental_Bill rb
                    ON r.room_id = rb.room_id
                    AND rb.start_date <= ?
                    AND rb.end_date >= ?
                LEFT JOIN Student s ON s.student_id = rb.student_id
                GROUP BY r.room_id
            """, (student_gender, student_gender, end_date, form['start_date'])).fetchall()

            rooms = []
            for room in room_rows:
                room_data = dict(room)
                room_data['gender_block_message'] = None
                if room_data['is_gender_blocked']:
                    room_data['gender_block_message'] = (
                        f"Reserved for {room_data['conflicting_gender']} students during this period"
                    )
                rooms.append(room_data)

            if form['room_id']:
                selected_room = next((r for r in rooms if r['room_id'] == form['room_id']), None)
                if selected_room:
                    total_fee = selected_room['fee_per_month'] * int(form['duration'])

    return render_template('Student Book Room.html',
                           rooms=rooms,
                           selected_room=selected_room,
                           form=form,
                           end_date=end_date,
                           total_fee=total_fee,
                           today=today)


@app.route('/student_book_room_confirm', methods=['POST'])
def student_book_room_confirm():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    room_id = request.form.get('room_id')
    start_date = request.form.get('start_date')
    duration = request.form.get('duration')
    end_date = request.form.get('end_date')

    conn = get_db()

    room = conn.execute(
        'SELECT * FROM Room WHERE room_id = ?', (room_id,)
    ).fetchone()

    if room is None:
        flash('Room not found.', 'danger')
        return redirect(url_for('student_book_room'))

    student_gender = session.get('gender')
    conflict_row = conn.execute("""
        SELECT
            COUNT(DISTINCT rb.student_id) AS occupancy,
            SUM(CASE WHEN s.gender IS NOT NULL AND s.gender != ? THEN 1 ELSE 0 END) > 0 AS is_gender_blocked,
            MAX(CASE WHEN s.gender IS NOT NULL AND s.gender != ? THEN s.gender END) AS conflicting_gender
        FROM Rental_Bill rb
        LEFT JOIN Student s ON s.student_id = rb.student_id
        WHERE rb.room_id = ?
          AND rb.start_date <= ?
          AND rb.end_date >= ?
    """, (student_gender, student_gender, room_id, end_date, start_date)).fetchone()

    if conflict_row['is_gender_blocked']:
        flash(
            f"Sorry, this room is currently reserved for {conflict_row['conflicting_gender']} students during your selected period.",
            'danger'
        )
        return redirect(url_for('student_book_room'))

    occupancy = conflict_row['occupancy']

    if occupancy >= room['capacity']:
        flash('This room is fully occupied during your selected period.', 'danger')
        return redirect(url_for('student_book_room'))

    total_fee = room['fee_per_month'] * int(duration)

    conn.execute('''
        INSERT INTO Rental_Bill (amount, start_date, end_date, student_id, room_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (total_fee, start_date, end_date, session['user_id'], room_id))

    conn.commit()

    flash('Room booked successfully!', 'success')
    return redirect(url_for('student_book_room'))


@app.route("/student_maintenance")
def student_maintenance():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    student_id = session['user_id']

    conn = get_db()
    issues = conn.execute("""
        SELECT request_id, category, description, created_at, status
        FROM Maintenance
        WHERE student_id = ?
        ORDER BY request_id DESC
    """, (student_id,)).fetchall()

    return render_template('Student Maintenance.html', issues=issues)


@app.route("/student_maintenance_add", methods=['GET', 'POST'])
def student_maintenance_add():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')
    
    categories = [
        'Electrical',
        'Plumbing',
        'Furniture',
        'Internet/WiFi',
        'Air Conditioning/Fan',
        'Cleaning/Pest Control',
        'Door/Window/Lock',
        'Other'
    ]

    if request.method == 'POST':
        conn = get_db()
        student_id  = session['user_id']
        row = conn.execute("""
        SELECT rb.room_id
        FROM Rental_Bill rb
        WHERE rb.student_id = ?
        """,(student_id,)).fetchone()
        if not row:
            flash("No belonged room found.", "danger")
            return render_template('Student Maintenance Add.html', categories=categories)

        room_id = row["room_id"]

        category    = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()

        if not category:
            flash("Please select a category.", "danger")
            return render_template('Student Maintenance Add.html', categories=categories)

        if not description:
            flash("Description cannot be empty or spaces only.", "danger")
            return render_template('Student Maintenance Add.html', categories=categories)

        if len(description) < 10:
            flash("Description is too short. Please provide more details.", "danger")
            return render_template('Student Maintenance Add.html', categories=categories)

        conn.execute("""
            INSERT INTO Maintenance (description, category, status, room_id, student_id)
            VALUES (?, ?, ?, ?, ? )
        """, (description, category,'pending', room_id, student_id))
        conn.commit()

        flash("Maintenance request submitted successfully.", "success")
        return redirect(url_for('student_maintenance'))

    return render_template('Student Maintenance Add.html', categories=categories)



@app.route("/student_profile")
def student_profile():
    if session.get('user_id') is None or session.get('role') != 'student':
        return redirect('/user_login')

    return render_template("Student Profile.html")


@app.route("/warden_dashboard")
def warden_dashboard():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    conn = get_db()
    total_request = conn.execute("""
    SELECT COUNT(*) FROM Maintenance
    """).fetchone()[0]
    pending_request = conn.execute("""
    SELECT COUNT(*) FROM Maintenance
    WHERE status = 'pending'
    """).fetchone()[0]
    in_progress_request = conn.execute("""
    SELECT COUNT(*) FROM Maintenance
    WHERE status = 'in-progress'
    """).fetchone()[0]
    completed_request = conn.execute("""
    SELECT COUNT(*) FROM Maintenance
    WHERE status = 'resolved'
    """).fetchone()[0]
    due_rental_fees = conn.execute("""
    SELECT COALESCE(SUM(amount), 0) FROM Rental_Bill WHERE payment_id IS NULL
    """).fetchone()[0]
    due_fines = conn.execute("""
    SELECT COALESCE(SUM(amount), 0) FROM Fine WHERE payment_id IS NULL;
    """).fetchone()[0]
    fine_row = conn.execute("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_fine,
            COALESCE(SUM(CASE WHEN payment_id IS NULL THEN amount ELSE 0 END), 0) AS total_unpaid_fine,
            COALESCE(SUM(CASE WHEN payment_id IS NOT NULL THEN amount ELSE 0 END), 0) AS total_paid_fine
        FROM Fine
    """).fetchone()
    total_due_payment = due_fines + due_rental_fees
    return render_template("Warden Dashboard.html",total_request=total_request, pending_request=pending_request,
                           in_progress_request=in_progress_request, completed_request=completed_request, total_due_payment=total_due_payment,
                           due_rental_fees=due_rental_fees, due_fines=due_fines,total_fine=fine_row["total_fine"],total_unpaid_fine=fine_row["total_unpaid_fine"],
                            total_paid_fine=fine_row["total_paid_fine"])


@app.route("/warden_student_list")
def warden_student_list():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    conn = get_db()
    search_data = request.args.get("search_data", "")

    if search_data:
        table_data = conn.execute("""
            SELECT *
            FROM Student
            WHERE student_id = ?
        """, (search_data,)).fetchall()
    else:
        table_data = conn.execute("""
            SELECT *
            FROM Student
        """).fetchall()

    return render_template("Warden Student List.html", table_data=table_data)


@app.route("/warden_maintenance")
def warden_maintenance():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    conn = get_db()
    issues = conn.execute("""
        SELECT request_id, student_id, room_id, category, description, created_at, status
        FROM Maintenance
        ORDER BY created_at DESC

    """).fetchall()

    return render_template("Warden Maintenance.html",issues=issues)


# ================= UPDATE STATUS (WARDEN) =================
@app.route('/update_status/<int:id>', methods=['POST'])
def update_status(id):
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')

    status = request.form.get('status')

    valid_statuses = ['pending', 'in-progress', 'resolved']
    if status not in valid_statuses:
        flash("Invalid status value.", "error")
        return redirect(url_for('warden_maintenance'))

    db = get_db()
    db.execute("""
        UPDATE Maintenance
        SET status = ?
        WHERE request_id = ?
    """, (status, id))
    db.commit()

    flash("Status updated successfully.", "success")
    return redirect(url_for('warden_maintenance'))


@app.route("/warden_announcement")
def warden_announcement():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    conn = get_db()

    search_date = request.args.get("search_date", "")
    if search_date:
        table_data = conn.execute("""
            SELECT a.announcement_id, a.title, a.description, a.created_at,
                   s.fullname AS staff_name,
                   a.audience,
                   st.fullname AS recipient_name
            FROM Announcement a
            JOIN Staff s ON a.staff_id = s.staff_id
            LEFT JOIN Announcement_Recipient ar ON a.announcement_id = ar.announcement_id
            LEFT JOIN Student st ON ar.student_id = st.student_id
            WHERE DATE(a.created_at) = ?
            ORDER BY a.created_at DESC
        """, (search_date,)).fetchall()
    else:
        table_data = conn.execute("""
            SELECT a.announcement_id, a.title, a.description, a.created_at,
                   s.fullname AS staff_name,
                   a.audience,
                   st.fullname AS recipient_name
            FROM Announcement a
            JOIN Staff s ON a.staff_id = s.staff_id
            LEFT JOIN Announcement_Recipient ar ON a.announcement_id = ar.announcement_id
            LEFT JOIN Student st ON ar.student_id = st.student_id
            ORDER BY a.created_at DESC
        """).fetchall()

    return render_template("Warden Announcement.html", table_data=table_data, search_date=search_date)


@app.route("/warden_announcement_add", methods=["GET", "POST"])
def warden_announcement_add():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    conn = get_db()

    if request.method == "POST":
        title          = request.form.get("title", "").strip()
        description    = request.form.get("description", "").strip()
        audience       = request.form.get("audience", "all")
        student_id     = request.form.get("student_id", "").strip()

        if not title or not description:
            flash("Title and description are required.", "danger")
        elif audience == "one" and not student_id:
            flash("Please select a student.", "danger")
        else:
            staff_id = session.get('user_id')

            try:
                cursor = conn.execute(
                    "INSERT INTO Announcement (title, description, audience, staff_id) VALUES (?, ?, ?, ?)",
                    (title, description, audience, staff_id)
                )
                announcement_id = cursor.lastrowid
                if audience == "one":
                    conn.execute(
                        "INSERT INTO Announcement_Recipient (announcement_id, student_id) VALUES (?, ?)",
                        (announcement_id, student_id)
                    )
                conn.commit()
                flash("Announcement sent successfully.", "success")
                return redirect("/warden_announcement")
            except sqlite3.IntegrityError:
                conn.rollback()
                flash("Student ID does not exist.", "danger")

    students = conn.execute(
        "SELECT student_id, fullname FROM Student ORDER BY fullname"
    ).fetchall()
    return render_template("Warden Announcement Add.html", students=students)


@app.route("/warden_announcement_view")
def warden_announcement_view():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    announcement_id = request.args.get("announcement_id", "")
    conn = get_db()
    row = conn.execute("""
        SELECT a.announcement_id, a.title, a.description, a.created_at,
               s.fullname AS staff_name
        FROM Announcement a
        JOIN Staff s ON a.staff_id = s.staff_id
        WHERE a.announcement_id = ?
    """, (announcement_id,)).fetchone()

    if not row:
        return redirect("/warden_announcement")

    return render_template("Warden Announcement View.html", row=row)


@app.route("/warden_announcement_delete", methods=["POST"])
def warden_announcement_delete():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    announcement_id = request.form.get("announcement_id", "")

    conn = get_db()
    conn.execute("DELETE FROM Announcement_Recipient WHERE announcement_id = ?", (announcement_id,))
    conn.execute("DELETE FROM Announcement WHERE announcement_id = ?", (announcement_id,))
    conn.commit()
    flash("Announcement Deleted Successfully","success")

    return redirect("/warden_announcement")


@app.route("/warden_due_payment")
def warden_due_payment():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    conn = get_db()
    search_data = request.args.get("search_data","")

    if search_data:
        table_data = conn.execute("""
            SELECT
            s.student_id,
            s.fullname,
            s.email,
            SUM(d.amount) AS total_due
            FROM Student s
            JOIN (
                SELECT student_id, amount FROM Rental_Bill WHERE payment_id IS NULL
                UNION ALL
                SELECT student_id, amount FROM Fine WHERE payment_id IS NULL
            ) d ON d.student_id = s.student_id
            WHERE s.student_id = ?
            GROUP BY s.student_id 
            """,(search_data,)).fetchall()
    else:
        table_data = conn.execute("""
            SELECT
            s.student_id,
            s.fullname,
            s.email,
            SUM(d.amount) AS total_due
            FROM Student s
            JOIN (
                SELECT student_id, amount FROM Rental_Bill WHERE payment_id IS NULL
                UNION ALL
                SELECT student_id, amount FROM Fine WHERE payment_id IS NULL
            ) d ON d.student_id = s.student_id
            GROUP BY s.student_id;  
            """).fetchall()

    return render_template("Warden Due Payment.html",table_data=table_data,search_data=search_data)


@app.route('/warden_fines', methods=['GET', 'POST'])
def warden_fines():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')

    # GET
    search = request.args.get('search', '')
    conn = get_db()

    if search:
        fines = conn.execute("""
            SELECT Fine.*, Student.fullname 
            FROM Fine 
            JOIN Student ON Fine.student_id = Student.student_id
            WHERE Student.fullname LIKE ? OR Fine.student_id LIKE ?
            ORDER BY Fine.created_at DESC
        """, (f'%{search}%', f'%{search}%')).fetchall()
    else:
        fines = conn.execute("""
            SELECT Fine.*, Student.fullname 
            FROM Fine 
            JOIN Student ON Fine.student_id = Student.student_id
            ORDER BY Fine.created_at DESC
        """).fetchall()

    return render_template('Warden Fines.html', fines=fines, search=search)


@app.route('/warden_fines_add', methods=['GET', 'POST'])
def warden_fines_add():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')

    if request.method == 'POST':
        student_id = request.form['student_id']
        reason = request.form['reason']
        amount = request.form['amount']

        try:
            amount = float(amount)
            if amount <= 0:
                flash(message='Amount must be a positive number.', category='danger')
                return redirect('/warden_fines_add')
        except ValueError:
            flash(message='Invalid amount entered.', category='danger')
            return redirect('/warden_fines_add')

        conn = get_db()

        student = conn.execute("SELECT * FROM Student WHERE student_id = ?", (student_id,)).fetchone()
        if not student:
            flash(message='Student ID does not exist.', category='danger')
            return redirect('/warden_fines_add')

        conn.execute("""
            INSERT INTO Fine (student_id, staff_id, reason, amount)
            VALUES (?, ?, ?, ?)
        """, (student_id, session['user_id'], reason, amount))
        conn.commit()

        flash(message='Fine added successfully!', category='success')
        return redirect('/warden_fines')

    return render_template('Warden Fines Add.html')


@app.route("/warden_profile")
def warden_profile():
    if session.get('user_id') is None or session.get('role') != 'warden':
        return redirect('/user_login')
    
    return render_template("Warden Profile.html")


if __name__ == "__main__":
    app.run(debug=True)