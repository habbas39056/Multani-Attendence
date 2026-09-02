"""
Seed initial realistic data for Multani Attendance & Payroll System
"""
from datetime import datetime, date, timedelta
from database import init_db, get_db_connection
from attendance_engine import process_attendance_range
from payroll_engine import calculate_monthly_payroll

def seed_all():
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Company Settings
    cursor.execute("SELECT COUNT(*) as cnt FROM company_settings")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("""
            INSERT INTO company_settings (
                company_name, currency, working_days_per_month, overtime_multiplier, 
                late_grace_minutes, late_penalty_days, late_threshold_count, 
                auto_sync_interval_seconds, address, phone, email
            ) VALUES (
                'Multani Enterprises', 'PKR', 26, 1.5, 
                15, 0.33, 3, 
                60, 'Industrial Estate, Multan, Pakistan', '+92 300 9876543', 'hr@multanienterprises.com'
            )
        """)

    # 2. Default Shift
    cursor.execute("SELECT COUNT(*) as cnt FROM shifts")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("""
            INSERT INTO shifts (name, start_time, end_time, grace_minutes, half_day_hours, full_day_hours, min_overtime_minutes, work_days, is_active)
            VALUES ('Standard Morning Shift', '09:00', '18:00', 15, 4.0, 8.0, 30, 'Mon,Tue,Wed,Thu,Fri,Sat', 1)
        """)
        cursor.execute("""
            INSERT INTO shifts (name, start_time, end_time, grace_minutes, half_day_hours, full_day_hours, min_overtime_minutes, work_days, is_active)
            VALUES ('Night Production Shift', '20:00', '05:00', 15, 4.0, 8.0, 30, 'Mon,Tue,Wed,Thu,Fri,Sat', 1)
        """)

    # 3. Biometric Device with User's Specified IP and Port (182.188.40.187:8080)
    cursor.execute("SELECT COUNT(*) as cnt FROM biometric_devices")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("""
            INSERT INTO biometric_devices (name, ip_address, port, protocol, device_model, auto_sync, sync_interval_sec, last_status)
            VALUES ('Multani Main Biometric Machine', '182.188.40.187', 8080, 'auto', 'ZK / Biometric TCP Device', 1, 60, 'Ready / Configured')
        """)

    # 4. Default Employees (Only seeded if table completely empty)
    # Real staff from Multani Traders are managed directly
    cursor.execute("SELECT COUNT(*) as cnt FROM employees")
    if cursor.fetchone()["cnt"] == 0:
        pass # Keep empty for user's real imports

    # 5. Generate sample attendance punch logs for the last 14 days
    cursor.execute("SELECT COUNT(*) as cnt FROM raw_attendance_logs")
    if cursor.fetchone()["cnt"] == 0:
        today = date.today()
        # Create punches for last 14 days
        for day_offset in range(14, -1, -1):
            curr_date = today - timedelta(days=day_offset)
            d_str = curr_date.strftime("%Y-%m-%d")
            weekday = curr_date.weekday() # 6 is Sunday

            if weekday == 6:
                continue # Sunday is weekend

            # Employee 101: Always on time (08:52 In, 18:05 Out)
            cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-In', 'simulator')", ("101", f"{d_str} 08:52:14"))
            cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-Out', 'simulator')", ("101", f"{d_str} 18:04:30"))

            # Employee 102: Overtime worker (08:48 In, 19:45 Out -> 1.75h OT)
            cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-In', 'simulator')", ("102", f"{d_str} 08:48:00"))
            cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-Out', 'simulator')", ("102", f"{d_str} 19:45:22"))

            # Employee 103: Sometimes late (09:28 In, 18:00 Out)
            if day_offset % 3 == 0:
                cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-In', 'simulator')", ("103", f"{d_str} 09:28:10"))
                cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-Out', 'simulator')", ("103", f"{d_str} 18:01:15"))
            else:
                cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-In', 'simulator')", ("103", f"{d_str} 08:55:00"))
                cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-Out', 'simulator')", ("103", f"{d_str} 18:05:00"))

            # Employee 104: On time
            cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-In', 'simulator')", ("104", f"{d_str} 08:50:33"))
            cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-Out', 'simulator')", ("104", f"{d_str} 18:10:00"))

            # Employee 105: Misses 2 days (absent demo)
            if day_offset not in [3, 8]:
                cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-In', 'simulator')", ("105", f"{d_str} 09:02:11"))
                cursor.execute("INSERT OR IGNORE INTO raw_attendance_logs (biometric_id, punch_time, punch_type, source) VALUES (?, ?, 'Check-Out', 'simulator')", ("105", f"{d_str} 18:00:45"))

    conn.commit()
    conn.close()

    # Process attendance for the last 14 days
    today = date.today()
    start_d = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    end_d = today.strftime("%Y-%m-%d")
    process_attendance_range(start_d, end_d)

    # Generate current month payroll
    current_month = today.strftime("%Y-%m")
    calculate_monthly_payroll(current_month)
    print("Seed data loaded and processed successfully.")

if __name__ == "__main__":
    seed_all()
