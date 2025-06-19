#!/usr/bin/env python3
"""
Migration script to help transfer data from SQLite to PostgreSQL
Run this script if you need to migrate existing data from your local SQLite database
to the new PostgreSQL database on Render.

Usage:
1. First, set your DATABASE_URL environment variable to your PostgreSQL connection string
2. Make sure your SQLite database file (booking.db) is in the same directory
3. Run: python migrate_to_postgres.py
"""

import os
import sqlite3
from app import app, db, User, Booking, ScheduleOverride
from werkzeug.security import generate_password_hash
from datetime import datetime

def migrate_data():
    """Migrate data from SQLite to PostgreSQL"""
    
    # Check if SQLite database exists
    if not os.path.exists('booking.db'):
        print("No SQLite database found (booking.db). Nothing to migrate.")
        return
    
    print("Starting migration from SQLite to PostgreSQL...")
    
    # Connect to SQLite database
    sqlite_conn = sqlite3.connect('booking.db')
    sqlite_conn.row_factory = sqlite3.Row  # This enables column access by name
    cursor = sqlite_conn.cursor()
    
    with app.app_context():
        # Create all tables in PostgreSQL
        db.create_all()
        
        # Migrate Users
        print("Migrating users...")
        cursor.execute("SELECT * FROM user")
        users = cursor.fetchall()
        
        for sqlite_user in users:
            # Check if user already exists in PostgreSQL
            existing_user = User.query.filter_by(username=sqlite_user['username']).first()
            if not existing_user:
                user = User(
                    username=sqlite_user['username'],
                    email=sqlite_user['email'],
                    phone=sqlite_user['phone'],
                    password_hash=sqlite_user['password_hash'],
                    is_admin=bool(sqlite_user['is_admin'])
                )
                db.session.add(user)
                print(f"  Added user: {sqlite_user['username']}")
            else:
                print(f"  User already exists: {sqlite_user['username']}")
        
        db.session.commit()
        
        # Migrate Schedule Overrides
        print("Migrating schedule overrides...")
        try:
            cursor.execute("SELECT * FROM schedule_override")
            schedule_overrides = cursor.fetchall()
            
            for sqlite_override in schedule_overrides:
                # Check if override already exists
                override_date = datetime.strptime(sqlite_override['date'], '%Y-%m-%d').date()
                existing_override = ScheduleOverride.query.filter_by(date=override_date).first()
                
                if not existing_override:
                    override = ScheduleOverride(
                        date=override_date,
                        is_open=bool(sqlite_override['is_open']),
                        opening_time=sqlite_override['opening_time'],
                        closing_time=sqlite_override['closing_time'],
                        note=sqlite_override['note'],
                        created_at=datetime.strptime(sqlite_override['created_at'], '%Y-%m-%d %H:%M:%S.%f')
                    )
                    db.session.add(override)
                    print(f"  Added schedule override for: {override_date}")
                else:
                    print(f"  Schedule override already exists for: {override_date}")
        except sqlite3.OperationalError:
            print("  No schedule overrides table found in SQLite database")
        
        db.session.commit()
        
        # Migrate Bookings
        print("Migrating bookings...")
        cursor.execute("SELECT * FROM booking")
        bookings = cursor.fetchall()
        
        for sqlite_booking in bookings:
            # Parse the date
            booking_date = datetime.strptime(sqlite_booking['date'], '%Y-%m-%d').date()
            
            # Check if booking already exists
            existing_booking = Booking.query.filter_by(
                date=booking_date,
                time_slot=sqlite_booking['time_slot']
            ).first()
            
            if not existing_booking:
                # Find the corresponding user in PostgreSQL if it's not a guest booking
                postgres_user = None
                if sqlite_booking['user_id']:
                    # Get the username from SQLite
                    cursor.execute("SELECT username FROM user WHERE id = ?", (sqlite_booking['user_id'],))
                    sqlite_user_row = cursor.fetchone()
                    if sqlite_user_row:
                        postgres_user = User.query.filter_by(username=sqlite_user_row['username']).first()
                
                booking = Booking(
                    user_id=postgres_user.id if postgres_user else None,
                    date=booking_date,
                    time_slot=sqlite_booking['time_slot'],
                    guest_name=sqlite_booking.get('guest_name'),
                    guest_phone=sqlite_booking.get('guest_phone'),
                    guest_email=sqlite_booking.get('guest_email'),
                    admin_note=sqlite_booking.get('admin_note'),
                    is_guest_booking=bool(sqlite_booking.get('is_guest_booking', False)),
                    created_at=datetime.strptime(sqlite_booking['created_at'], '%Y-%m-%d %H:%M:%S.%f')
                )
                db.session.add(booking)
                print(f"  Added booking: {booking_date} at {sqlite_booking['time_slot']}")
            else:
                print(f"  Booking already exists: {booking_date} at {sqlite_booking['time_slot']}")
        
        db.session.commit()
    
    sqlite_conn.close()
    print("Migration completed successfully!")
    print("\nNext steps:")
    print("1. Test your application with the PostgreSQL database")
    print("2. If everything works correctly, you can delete the booking.db file")
    print("3. Deploy your updated application to Render")

if __name__ == '__main__':
    # Make sure DATABASE_URL is set to PostgreSQL
    if not os.environ.get('DATABASE_URL'):
        print("ERROR: DATABASE_URL environment variable not set!")
        print("Please set it to your PostgreSQL connection string before running this script.")
        print("Example: export DATABASE_URL='postgres://username:password@host:port/dbname'")
        exit(1)
    
    if os.environ.get('DATABASE_URL', '').startswith('sqlite'):
        print("ERROR: DATABASE_URL is still pointing to SQLite!")
        print("Please set it to your PostgreSQL connection string.")
        exit(1)
    
    migrate_data() 