from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

# Database configuration - PostgreSQL with fallback to SQLite for local development
def get_database_url():
    """Get the database URL with proper format conversion for SQLAlchemy"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Convert postgres:// to postgresql:// for SQLAlchemy compatibility
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    else:
        # Fallback to SQLite for local development
        return 'sqlite:///booking.db'

app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
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
    has_logged_in_before = db.Column(db.Boolean, default=False)  # Track first login
    bookings = db.relationship('Booking', backref='user', lazy=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Nullable for guest bookings
    date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(10), nullable=False)  # e.g., "09:00"
    guest_name = db.Column(db.String(100))  # For non-registered customers
    guest_phone = db.Column(db.String(20))  # For non-registered customers
    guest_email = db.Column(db.String(120))  # For non-registered customers
    admin_note = db.Column(db.String(200))  # Admin's private note
    is_guest_booking = db.Column(db.Boolean, default=False)
    is_paid = db.Column(db.Boolean, default=False)  # Track payment status
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
    current_time = datetime.now()
    
    for hour in range(opening_hour, closing_hour):
        time_slot = f"{hour:02d}:00"
        
        # If this is today, only include slots that haven't passed yet
        if selected_date == date.today():
            slot_time = datetime.combine(selected_date, datetime.strptime(time_slot, '%H:%M').time())
            if slot_time <= current_time:
                continue  # Skip past time slots
        
        slots.append(time_slot)
    
    return slots

def get_conflicting_bookings(selected_date, is_open, opening_time=None, closing_time=None):
    """Get bookings that would conflict with new schedule settings"""
    conflicting_bookings = []
    
    # Get all bookings for this date
    bookings = Booking.query.filter_by(date=selected_date).all()
    
    if not is_open:
        # If closing the day, all bookings conflict
        conflicting_bookings = bookings
    else:
        # If changing hours, check which bookings fall outside new hours
        if opening_time and closing_time:
            opening_hour = int(opening_time.split(':')[0])
            closing_hour = int(closing_time.split(':')[0])
            
            for booking in bookings:
                booking_hour = int(booking.time_slot.split(':')[0])
                if booking_hour < opening_hour or booking_hour >= closing_hour:
                    conflicting_bookings.append(booking)
    
    return conflicting_bookings

def cancel_conflicting_bookings(conflicting_bookings):
    """Cancel bookings and send notification emails"""
    cancelled_count = 0
    email_failures = 0
    
    for booking in conflicting_bookings:
        # Send cancellation email
        email_sent = False
        if booking.is_guest_booking:
            # For guest bookings, use guest email if available
            if booking.guest_email:
                email_sent = send_booking_email(
                    booking.guest_email, 
                    booking.guest_name, 
                    booking.date, 
                    booking.time_slot, 
                    is_confirmation=False,
                    is_schedule_cancellation=True
                )
        else:
            # For regular user bookings, get user and send email
            user = User.query.get(booking.user_id)
            if user:
                email_sent = send_booking_email(
                    user.email, 
                    user.username, 
                    booking.date, 
                    booking.time_slot, 
                    is_confirmation=False,
                    is_schedule_cancellation=True
                )
        
        if not email_sent:
            email_failures += 1
        
        # Delete the booking
        db.session.delete(booking)
        cancelled_count += 1
    
    db.session.commit()
    return cancelled_count, email_failures

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
def send_booking_email(user_email, username, booking_date, time_slot, is_confirmation=True, is_schedule_cancellation=False):
    """Send email notification for booking confirmation or cancellation"""
    try:
        if is_confirmation:
            subject = "Booking Confirmation - S&F Barbers, Mold"
            body = f"""
Dear {username},

Your appointment at S&F Barbers in Mold has been confirmed!

📅 Date: {booking_date.strftime('%A, %B %d, %Y')}
⏰ Time: {time_slot}

Please arrive 5 minutes early for your appointment with Nath.

If you need to cancel or reschedule, please log into your account at least 2 hours before your appointment time.

Thank you for choosing S&F Barbers!

Best regards,
Nath
S&F Barbers, Mold
            """
        else:
            subject = "Booking Cancellation - S&F Barbers, Mold"
            if is_schedule_cancellation:
                body = f"""
Dear {username},

We regret to inform you that your appointment at S&F Barbers in Mold has been cancelled due to a schedule change.

📅 Date: {booking_date.strftime('%A, %B %d, %Y')}
⏰ Time: {time_slot}

This cancellation was necessary due to updated business hours or closure on this date. We sincerely apologize for any inconvenience this may cause.

Please contact us or book a new appointment through our online system for an alternative time that works for you.

Thank you for your understanding.

Best regards,
Nath
S&F Barbers, Mold
                """
            else:
                body = f"""
Dear {username},

Your appointment at S&F Barbers in Mold has been cancelled.

📅 Date: {booking_date.strftime('%A, %B %d, %Y')}
⏰ Time: {time_slot}

If this cancellation was unexpected, please contact us or book a new appointment through our system.

Thank you for your understanding.

Best regards,
Nath
S&F Barbers, Mold
                """
        
        msg = Message(subject=subject, recipients=[user_email], body=body)
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def send_payment_reminder_email(user_email, username, booking_date, time_slot):
    """Send payment reminder email for completed appointments"""
    try:
        subject = "Payment Reminder - S&F Barbers, Mold"
        body = f"""
Dear {username},

This is a friendly reminder that your recent appointment at S&F Barbers in Mold is awaiting payment.

📅 Date: {booking_date.strftime('%A, %B %d, %Y')}
⏰ Time: {time_slot}

Please settle your payment at your earliest convenience. You can pay:
• In person during our business hours (9 AM - 4 PM)
• By contacting us directly

If you have already paid, please disregard this message.

Thank you for choosing S&F Barbers!

Best regards,
Nath
S&F Barbers, Mold
        """
        
        msg = Message(subject=subject, recipients=[user_email], body=body)
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Failed to send payment reminder email: {e}")
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
            
            # Check if this is their first login
            if not user.has_logged_in_before:
                # First time login
                user.has_logged_in_before = True
                db.session.commit()
                session['show_welcome_message'] = f'Welcome to S&F Barbers, {user.username}! We\'re excited to have you as a customer.'
            else:
                # Returning user
                session['show_welcome_message'] = f'Welcome back, {user.username}! Ready to book your next appointment?'
            
            return redirect(url_for('calendar'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dismiss-welcome', methods=['POST'])
def dismiss_welcome():
    """Clear the welcome message from session"""
    session.pop('show_welcome_message', None)
    return '', 204  # Return empty response with "No Content" status

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
    
    # Check if trying to book a past time slot for today
    if selected_date == date.today():
        current_time = datetime.now()
        slot_time = datetime.combine(selected_date, datetime.strptime(time_slot, '%H:%M').time())
        if slot_time <= current_time:
            flash('Cannot book a time slot that has already passed.', 'warning')
            return redirect(url_for('calendar', date=selected_date_str))
    
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
    
    booking_date = booking.date
    time_slot = booking.time_slot
    
    # Handle email notification based on booking type
    email_sent = False
    if booking.is_guest_booking:
        # For guest bookings, use guest email if available
        if booking.guest_email:
            email_sent = send_booking_email(
                booking.guest_email, 
                booking.guest_name, 
                booking_date, 
                time_slot, 
                is_confirmation=False
            )
    else:
        # For regular user bookings, get user and send email
        user = User.query.get(booking.user_id)
        if user:
            email_sent = send_booking_email(
                user.email, 
                user.username, 
                booking_date, 
                time_slot, 
                is_confirmation=False
            )
    
    # Delete booking
    db.session.delete(booking)
    db.session.commit()
    
    # Show appropriate success message
    if email_sent:
        flash('Booking cancelled successfully. Cancellation email sent.', 'success')
    else:
        flash('Booking cancelled successfully.', 'success')
    
    if is_admin():
        return redirect(url_for('admin'))
    else:
        return redirect(url_for('calendar'))

@app.route('/admin')
@admin_required
def admin():
    # Get current and upcoming bookings only (not past bookings)
    today = date.today()
    now = datetime.now()
    
    # For today's bookings, only show those that haven't passed yet
    bookings = db.session.query(Booking).outerjoin(User).filter(
        (Booking.date > today) |  # Future dates
        (
            (Booking.date == today) &  # Today's bookings
            (Booking.time_slot >= now.strftime('%H:%M'))  # That haven't passed yet
        )
    ).order_by(Booking.date, Booking.time_slot).all()
    
    # Group bookings by date
    bookings_by_date = {}
    for booking in bookings:
        date_str = booking.date.strftime('%Y-%m-%d')
        if date_str not in bookings_by_date:
            bookings_by_date[date_str] = []
        bookings_by_date[date_str].append(booking)
    
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
    confirm = request.form.get('confirm') == 'true'  # Check if this is a confirmation
    
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('admin_schedule'))
    
    # Check for conflicting bookings
    conflicting_bookings = get_conflicting_bookings(selected_date, is_open, opening_time, closing_time)
    
    if conflicting_bookings and not confirm:
        # Store the form data in session for confirmation
        session['pending_schedule_change'] = {
            'date': selected_date_str,
            'is_open': is_open,
            'opening_time': opening_time,
            'closing_time': closing_time,
            'note': note
        }
        
        # Prepare booking details for confirmation
        booking_details = []
        for booking in conflicting_bookings:
            if booking.is_guest_booking:
                booking_details.append({
                    'name': booking.guest_name,
                    'time': booking.time_slot,
                    'type': 'Guest'
                })
            else:
                user = User.query.get(booking.user_id)
                booking_details.append({
                    'name': user.username if user else 'Unknown User',
                    'time': booking.time_slot,
                    'type': 'Registered User'
                })
        
        return render_template('admin_schedule_confirm.html', 
                             selected_date=selected_date,
                             booking_details=booking_details,
                             is_open=is_open,
                             opening_time=opening_time,
                             closing_time=closing_time,
                             note=note)
    
    # If confirmed or no conflicts, proceed with the change
    if conflicting_bookings and confirm:
        # Cancel conflicting bookings
        cancelled_count, email_failures = cancel_conflicting_bookings(conflicting_bookings)
        
        if email_failures > 0:
            flash(f'Schedule updated. {cancelled_count} bookings cancelled ({email_failures} email notifications failed).', 'warning')
        else:
            flash(f'Schedule updated. {cancelled_count} bookings cancelled and notification emails sent.', 'success')
    
    # Apply the schedule change
    existing = ScheduleOverride.query.filter_by(date=selected_date).first()
    if existing:
        # Update existing override
        existing.is_open = is_open
        existing.opening_time = opening_time if is_open else '09:00'
        existing.closing_time = closing_time if is_open else '16:00'
        existing.note = note
        if not conflicting_bookings:
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
        if not conflicting_bookings:
            flash(f'Schedule override added for {selected_date.strftime("%B %d, %Y")}', 'success')
    
    db.session.commit()
    
    # Clear pending change from session
    session.pop('pending_schedule_change', None)
    
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

@app.route('/admin/book/<date>/<time_slot>')
@admin_required
def admin_book_slot(date, time_slot):
    """Admin booking interface for a specific slot"""
    try:
        selected_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('calendar'))
    
    # Check if slot is available
    existing_booking = Booking.query.filter_by(date=selected_date, time_slot=time_slot).first()
    if existing_booking:
        flash('This time slot is already booked.', 'danger')
        return redirect(url_for('calendar', date=date))
    
    # Check if the date/time is within business hours
    schedule_info = get_schedule_info(selected_date)
    if not schedule_info['is_open']:
        flash('Cannot book on a closed day.', 'danger')
        return redirect(url_for('calendar', date=date))
    
    return render_template('admin_book.html', 
                         selected_date=selected_date, 
                         time_slot=time_slot)

@app.route('/admin/search-users')
@admin_required
def search_users():
    """Search for users by name, email, or phone"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    # Use ilike for case-insensitive search (PostgreSQL compatible)
    search_pattern = f"%{query}%"
    users = User.query.filter(
        (User.username.ilike(search_pattern)) |
        (User.email.ilike(search_pattern)) |
        (User.phone.ilike(search_pattern))
    ).limit(10).all()
    
    user_list = []
    for user in users:
        user_list.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'phone': user.phone
        })
    
    return jsonify(user_list)

@app.route('/admin/book-for-user', methods=['POST'])
@admin_required
def book_for_user():
    """Admin books a slot for an existing user"""
    selected_date_str = request.form['date']
    time_slot = request.form['time_slot']
    user_id = request.form.get('user_id')
    
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('calendar'))
    
    # Check if slot is still available
    existing_booking = Booking.query.filter_by(date=selected_date, time_slot=time_slot).first()
    if existing_booking:
        flash('This time slot is no longer available.', 'danger')
        return redirect(url_for('calendar', date=selected_date_str))
    
    # Get user
    user = User.query.get(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('calendar', date=selected_date_str))
    
    # Create booking
    new_booking = Booking(
        user_id=user.id, 
        date=selected_date, 
        time_slot=time_slot,
        is_guest_booking=False
    )
    db.session.add(new_booking)
    db.session.commit()
    
    # Send confirmation email
    if send_booking_email(user.email, user.username, selected_date, time_slot, is_confirmation=True):
        flash(f'Booking created for {user.username} on {selected_date} at {time_slot}. Email sent.', 'success')
    else:
        flash(f'Booking created for {user.username} on {selected_date} at {time_slot}. (Email failed)', 'warning')
    
    return redirect(url_for('calendar', date=selected_date_str))

@app.route('/admin/book-guest', methods=['POST'])
@admin_required
def book_guest():
    """Admin books a slot for a walk-in/guest customer"""
    selected_date_str = request.form['date']
    time_slot = request.form['time_slot']
    guest_name = request.form.get('guest_name', '').strip()
    guest_phone = request.form.get('guest_phone', '').strip()
    guest_email = request.form.get('guest_email', '').strip()
    admin_note = request.form.get('admin_note', '').strip()
    
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('calendar'))
    
    if not guest_name:
        flash('Guest name is required.', 'danger')
        return redirect(url_for('admin_book_slot', date=selected_date_str, time_slot=time_slot))
    
    # Check if slot is still available
    existing_booking = Booking.query.filter_by(date=selected_date, time_slot=time_slot).first()
    if existing_booking:
        flash('This time slot is no longer available.', 'danger')
        return redirect(url_for('calendar', date=selected_date_str))
    
    # Create guest booking
    new_booking = Booking(
        date=selected_date,
        time_slot=time_slot,
        guest_name=guest_name,
        guest_phone=guest_phone,
        guest_email=guest_email,
        admin_note=admin_note,
        is_guest_booking=True
    )
    db.session.add(new_booking)
    db.session.commit()
    
    # Send email if guest provided email
    if guest_email:
        if send_booking_email(guest_email, guest_name, selected_date, time_slot, is_confirmation=True):
            flash(f'Guest booking created for {guest_name} on {selected_date} at {time_slot}. Email sent.', 'success')
        else:
            flash(f'Guest booking created for {guest_name} on {selected_date} at {time_slot}. (Email failed)', 'warning')
    else:
        flash(f'Guest booking created for {guest_name} on {selected_date} at {time_slot}.', 'success')
    
    return redirect(url_for('calendar', date=selected_date_str))

@app.route('/admin/past-bookings')
@admin_required
def admin_past_bookings():
    # Get past bookings that haven't been marked as paid
    today = date.today()
    now = datetime.now()
    
    # Include bookings from past dates OR today's bookings that have already passed
    past_bookings = db.session.query(Booking).outerjoin(User).filter(
        (
            (Booking.date < today) |  # Past dates
            (
                (Booking.date == today) &  # Today's bookings
                (Booking.time_slot < now.strftime('%H:%M'))  # That have already passed
            )
        ) &
        (Booking.is_paid == False)  # And haven't been marked as paid
    ).order_by(Booking.date.desc(), Booking.time_slot).all()
    
    # Group bookings by date
    bookings_by_date = {}
    for booking in past_bookings:
        date_str = booking.date.strftime('%Y-%m-%d')
        if date_str not in bookings_by_date:
            bookings_by_date[date_str] = []
        bookings_by_date[date_str].append(booking)
    
    return render_template('admin_past_bookings.html', bookings_by_date=bookings_by_date)

@app.route('/admin/mark-paid/<int:booking_id>', methods=['POST'])
@admin_required
def mark_booking_paid(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    booking.is_paid = True
    db.session.commit()
    
    # Get customer name for flash message
    if booking.is_guest_booking:
        customer_name = booking.guest_name
    else:
        user = User.query.get(booking.user_id)
        customer_name = user.username if user else 'Unknown User'
    
    flash(f'Booking for {customer_name} on {booking.date.strftime("%B %d")} at {booking.time_slot} marked as paid.', 'success')
    return redirect(url_for('admin_past_bookings'))

@app.route('/admin/send-payment-reminder/<int:booking_id>', methods=['POST'])
@admin_required
def send_payment_reminder(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    
    # Get customer details
    if booking.is_guest_booking:
        if not booking.guest_email:
            flash('No email address available for this guest booking.', 'warning')
            return redirect(url_for('admin_past_bookings'))
        
        customer_name = booking.guest_name
        customer_email = booking.guest_email
    else:
        user = User.query.get(booking.user_id)
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('admin_past_bookings'))
        
        customer_name = user.username
        customer_email = user.email
    
    # Send payment reminder email
    if send_payment_reminder_email(customer_email, customer_name, booking.date, booking.time_slot):
        flash(f'Payment reminder sent to {customer_name} ({customer_email}).', 'success')
    else:
        flash(f'Failed to send payment reminder to {customer_name}.', 'danger')
    
    return redirect(url_for('admin_past_bookings'))

def init_database():
    """Initialize the database with tables and admin user"""
    try:
        # Create all tables
        db.create_all()
        
        # Create admin user if it doesn't exist
        admin_user = User.query.filter_by(username=ADMIN_USERNAME).first()
        if not admin_user:
            admin_user = User(
                username=ADMIN_USERNAME,
                email='admin@sfbarbers.com',  # Default admin email
                phone='0000000000',  # Default admin phone
                password_hash=generate_password_hash(ADMIN_PASSWORD),
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created successfully")
        else:
            print("Admin user already exists")
            
    except Exception as e:
        print(f"Database initialization error: {e}")
        # For PostgreSQL, we might need to handle connection issues gracefully
        pass

if __name__ == '__main__':
    with app.app_context():
        init_database()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 