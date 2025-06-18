# Barber Booking System

A complete Flask web application for managing barber appointments with user authentication and admin panel.

## Features

- **User Registration**: Secure registration with invite password (`cut123`)
- **Authentication**: Session-based login system with password hashing
- **Booking System**: Calendar interface for booking hourly time slots (9 AM - 4 PM)
- **User Management**: Users can view and cancel their own bookings
- **Admin Panel**: Administrators can view and manage all bookings
- **Responsive Design**: Modern UI with Bootstrap 5 and Font Awesome icons

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

### 3. Access the System

#### Demo Credentials:
- **Admin Login**: `admin` / `admin123`
- **User Registration**: Use invite code `cut123`

## Project Structure

```
nath_booking/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── booking.db            # SQLite database (auto-created)
└── templates/            # HTML templates
    ├── base.html         # Base template with navigation
    ├── login.html        # Login page
    ├── register.html     # Registration page
    ├── calendar.html     # Booking calendar interface
    └── admin.html        # Admin panel
```

## Usage

### For Users:
1. **Register**: Go to `/register` and use invite code `cut123`
2. **Login**: Use your username and password
3. **Book Appointment**: Select a date and available time slot
4. **Manage Bookings**: View and cancel your appointments

### For Administrators:
1. **Login**: Use `admin` / `admin123`
2. **View All Bookings**: Access the admin panel to see all appointments
3. **Cancel Bookings**: Remove any user's booking if needed

## API Routes

- `GET /` - Home page (redirects to login or calendar)
- `GET/POST /register` - User registration
- `GET/POST /login` - User login
- `GET /logout` - User logout
- `GET /calendar` - Booking calendar interface
- `POST /book` - Create a new booking
- `POST /cancel` - Cancel a booking
- `GET /admin` - Admin panel (admin only)

## Configuration

### Environment Variables (for production):
- `SECRET_KEY`: Flask secret key for sessions
- `PORT`: Application port (default: 5000)

### Settings in `app.py`:
- `INVITE_PASSWORD`: Password required for user registration
- `ADMIN_USERNAME`/`ADMIN_PASSWORD`: Admin credentials
- Business hours: 9:00 AM - 4:00 PM (configurable in `get_available_slots()`)

## Database Schema

### Users Table:
- `id`: Primary key
- `username`: Unique username
- `email`: Unique email address
- `password_hash`: Hashed password
- `is_admin`: Admin flag

### Bookings Table:
- `id`: Primary key
- `user_id`: Foreign key to users
- `date`: Booking date
- `time_slot`: Booking time (e.g., "09:00")
- `created_at`: Timestamp

## Deployment

### Deploy to Render:
1. Connect your repository to Render
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `python app.py`
4. The app will run on the port specified by the `PORT` environment variable

### Deploy to Other Platforms:
The application is configured to work with any platform that supports Python/Flask:
- Uses `gunicorn` for production WSGI server
- SQLite database (no external database required)
- Environment-based port configuration

## Security Features

- Password hashing using Werkzeug's security utilities
- Session-based authentication
- CSRF protection through Flask sessions
- Input validation and sanitization
- Invite-only registration system

## License

This project is open source and available under the MIT License. 