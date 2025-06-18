from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///booking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'felixvandijkk@gmail.com'
app.config['MAIL_PASSWORD'] = 'bsjw ztxr aqfm etkv'
app.config['MAIL_DEFAULT_SENDER'] = 'felixvandijkk@gmail.com'

db = SQLAlchemy(app)
mail = Mail(app)

# Configuration
INVITE_PASSWORD = "cut123"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    bookings = db.relationship('Booking', backref='user', lazy=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(10), nullable=False)  # e.g., "09:00"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ScheduleOverride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    is_open = db.Column(db.Boolean, default=True)  # False means closed
    opening_time = db.Column(db.String(5), default='09:00')  # e.g., "09:00"
    closing_time = db.Column(db.String(5), default='16:00')  # e.g., "16:00"
    note = db.Column(db.String(200))  # Optional note like "Holiday", "Early close", etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Helper functions
def get_available_slots(selected_date=None):
    """Generate time slots based on schedule overrides or default hours"""
    if selected_date is None:
        selected_date = date.today()
    
    # Check for schedule override
    override = ScheduleOverride.query.filter_by(date=selected_date).first()
    
    if override:
        if not override.is_open:
            # Business is closed this day
            return []
        
        # Use custom hours
        opening_hour = int(override.opening_time.split(':')[0])
        closing_hour = int(override.closing_time.split(':')[0])
    else:
        # Use default hours (9 AM to 4 PM)
        opening_hour = 9
        closing_hour = 16
    
    slots = []
    for hour in range(opening_hour, closing_hour):
        slots.append(f"{hour:02d}:00")
    return slots

def get_schedule_info(selected_date):
    """Get schedule information for a specific date"""
    override = ScheduleOverride.query.filter_by(date=selected_date).first()
    
    if override:
        if not override.is_open:
            return {
                'is_open': False,
                'hours': None,
                'note': override.note or 'Closed',
                'is_custom': True
            }
        else:
            return {
                'is_open': True,
                'hours': f"{override.opening_time} - {override.closing_time}",
                'note': override.note,
                'is_custom': True
            }
    else:
        return {
            'is_open': True,
            'hours': '09:00 - 16:00',
            'note': None,
            'is_custom': False
        }

def get_booked_slots(selected_date):
    """Get all booked slots for a specific date"""
    bookings = Booking.query.filter_by(date=selected_date).all()
    return [booking.time_slot for booking in bookings]

def is_admin():
    """Check if current user is admin"""
    return session.get('is_admin', False)

def login_required(f):
    """Decorator to require login"""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def admin_required(f):
    """Decorator to require admin access"""
    def decorated_function(*args, **kwargs):
        if not is_admin():
            flash('Admin access required.', 'danger')
            return redirect(url_for('calendar'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Email functions
def send_booking_email(user_email, username, booking_date, time_slot, is_confirmation=True):
    """Send email notification for booking confirmation or cancellation"""
    try:
        if is_confirmation:
            subject = "Booking Confirmation - Barber Appointment"
            body = f"""
Dear {username},

Your barber appointment has been confirmed!

📅 Date: {booking_date.strftime('%A, %B %d, %Y')}
⏰ Time: {time_slot}

Please arrive 5 minutes early for your appointment.

If you need to cancel or reschedule, please log into your account at least 2 hours before your appointment time.

Thank you for choosing our barber services!

Best regards,
Barber Booking Team
            """
        else:
            subject = "Booking Cancellation - Barber Appointment"
            body = f"""
Dear {username},

Your barber appointment has been cancelled.

📅 Date: {booking_date.strftime('%A, %B %d, %Y')}
⏰ Time: {time_slot}

If this cancellation was unexpected, please contact us or book a new appointment through our system.

Thank you for your understanding.

Best regards,
Barber Booking Team
            """
        
        msg = Message(subject=subject, recipients=[user_email], body=body)
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('calendar'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        invite_password = request.form['invite_password']
        
        # Check invite password
        if invite_password != INVITE_PASSWORD:
            flash('Invalid invite password.', 'danger')
            return render_template('register.html')
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(phone=phone).first():
            flash('Phone number already exists.', 'danger')
            return render_template('register.html')
        
        # Create new user
        password_hash = generate_password_hash(password)
        new_user = User(username=username, email=email, phone=phone, password_hash=password_hash)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check for admin login
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['user_id'] = 'admin'
            session['username'] = 'Admin'
            session['is_admin'] = True
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin'))
        
        # Check for regular user
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = False
            flash('Login successful!', 'success')
            return redirect(url_for('calendar'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/calendar')
@login_required
def calendar():
    # Get the selected date (default to today)
    selected_date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    
    # Generate next 14 days for date picker
    dates = []
    for i in range(14):
        current_date = date.today() + timedelta(days=i)
        dates.append(current_date)
    
    # Get available and booked slots
    all_slots = get_available_slots(selected_date)
    booked_slots = get_booked_slots(selected_date)
    available_slots = [slot for slot in all_slots if slot not in booked_slots]
    
    # Get schedule information
    schedule_info = get_schedule_info(selected_date)
    
    # Get current user's bookings
    user_bookings = []
    if not is_admin():
        user_bookings = Booking.query.filter_by(user_id=session['user_id']).order_by(Booking.date, Booking.time_slot).all()
    
    return render_template('calendar.html', 
                         selected_date=selected_date,
                         dates=dates,
                         available_slots=available_slots,
                         booked_slots=booked_slots,
                         schedule_info=schedule_info,
                         user_bookings=user_bookings)

@app.route('/book', methods=['POST'])
@login_required
def book():
    if is_admin():
        flash('Admins cannot make bookings.', 'warning')
        return redirect(url_for('calendar'))
    
    selected_date_str = request.form['date']
    time_slot = request.form['time_slot']
    
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('calendar'))
    
    # Check if slot is available
    existing_booking = Booking.query.filter_by(date=selected_date, time_slot=time_slot).first()
    if existing_booking:
        flash('This time slot is already booked.', 'danger')
        return redirect(url_for('calendar', date=selected_date_str))
    
    # Check if user already has a booking on this date
    user_booking = Booking.query.filter_by(user_id=session['user_id'], date=selected_date).first()
    if user_booking:
        flash('You already have a booking on this date.', 'warning')
        return redirect(url_for('calendar', date=selected_date_str))
    
    # Get user for email
    user = User.query.get(session['user_id'])
    
    # Create booking
    new_booking = Booking(user_id=session['user_id'], date=selected_date, time_slot=time_slot)
    db.session.add(new_booking)
    db.session.commit()
    
    # Send confirmation email
    if send_booking_email(user.email, user.username, selected_date, time_slot, is_confirmation=True):
        flash(f'Booking confirmed for {selected_date} at {time_slot}! Confirmation email sent.', 'success')
    else:
        flash(f'Booking confirmed for {selected_date} at {time_slot}! (Email notification failed)', 'warning')
    
    return redirect(url_for('calendar', date=selected_date_str))

@app.route('/cancel', methods=['POST'])
@login_required
def cancel():
    booking_id = request.form['booking_id']
    booking = Booking.query.get_or_404(booking_id)
    
    # Check if user can cancel this booking
    if not is_admin() and booking.user_id != session['user_id']:
        flash('You can only cancel your own bookings.', 'danger')
        return redirect(url_for('calendar'))
    
    # Get user for email notification
    user = User.query.get(booking.user_id)
    booking_date = booking.date
    time_slot = booking.time_slot
    
    # Delete booking
    db.session.delete(booking)
    db.session.commit()
    
    # Send cancellation email
    if send_booking_email(user.email, user.username, booking_date, time_slot, is_confirmation=False):
        flash('Booking cancelled successfully. Cancellation email sent.', 'success')
    else:
        flash('Booking cancelled successfully. (Email notification failed)', 'warning')
    
    if is_admin():
        return redirect(url_for('admin'))
    else:
        return redirect(url_for('calendar'))

@app.route('/admin')
@admin_required
def admin():
    # Get all bookings with user information
    bookings = db.session.query(Booking, User).join(User).order_by(Booking.date, Booking.time_slot).all()
    
    # Group bookings by date
    bookings_by_date = {}
    for booking, user in bookings:
        date_str = booking.date.strftime('%Y-%m-%d')
        if date_str not in bookings_by_date:
            bookings_by_date[date_str] = []
        bookings_by_date[date_str].append((booking, user))
    
    return render_template('admin.html', bookings_by_date=bookings_by_date)

@app.route('/admin/schedule')
@admin_required
def admin_schedule():
    # Get all schedule overrides for the next 30 days
    start_date = date.today()
    end_date = start_date + timedelta(days=30)
    
    overrides = ScheduleOverride.query.filter(
        ScheduleOverride.date >= start_date,
        ScheduleOverride.date <= end_date
    ).order_by(ScheduleOverride.date).all()
    
    # Create a list of dates with their schedule info
    schedule_data = []
    for i in range(31):  # Next 30 days
        current_date = start_date + timedelta(days=i)
        override = next((o for o in overrides if o.date == current_date), None)
        
        if override:
            schedule_data.append({
                'date': current_date,
                'is_open': override.is_open,
                'hours': f"{override.opening_time} - {override.closing_time}" if override.is_open else "Closed",
                'note': override.note,
                'has_override': True,
                'override_id': override.id
            })
        else:
            schedule_data.append({
                'date': current_date,
                'is_open': True,
                'hours': "09:00 - 16:00",
                'note': "Default hours",
                'has_override': False,
                'override_id': None
            })
    
    return render_template('admin_schedule.html', schedule_data=schedule_data)

@app.route('/admin/schedule/add', methods=['POST'])
@admin_required
def add_schedule_override():
    selected_date_str = request.form['date']
    is_open = request.form.get('is_open') == 'on'
    opening_time = request.form.get('opening_time', '09:00')
    closing_time = request.form.get('closing_time', '16:00')
    note = request.form.get('note', '')
    
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('admin_schedule'))
    
    # Check if override already exists
    existing = ScheduleOverride.query.filter_by(date=selected_date).first()
    if existing:
        # Update existing override
        existing.is_open = is_open
        existing.opening_time = opening_time if is_open else '09:00'
        existing.closing_time = closing_time if is_open else '16:00'
        existing.note = note
        flash(f'Schedule updated for {selected_date.strftime("%B %d, %Y")}', 'success')
    else:
        # Create new override
        override = ScheduleOverride(
            date=selected_date,
            is_open=is_open,
            opening_time=opening_time if is_open else '09:00',
            closing_time=closing_time if is_open else '16:00',
            note=note
        )
        db.session.add(override)
        flash(f'Schedule override added for {selected_date.strftime("%B %d, %Y")}', 'success')
    
    db.session.commit()
    return redirect(url_for('admin_schedule'))

@app.route('/admin/schedule/delete/<int:override_id>', methods=['POST'])
@admin_required
def delete_schedule_override(override_id):
    override = ScheduleOverride.query.get_or_404(override_id)
    date_str = override.date.strftime("%B %d, %Y")
    db.session.delete(override)
    db.session.commit()
    flash(f'Schedule override removed for {date_str}. Default hours will apply.', 'success')
    return redirect(url_for('admin_schedule'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 