"""
Database Schema and Helper for Multani Attendance & Payroll System
"""
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "payroll_attendance.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Company Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS company_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL DEFAULT 'Multani Enterprises',
        currency TEXT NOT NULL DEFAULT 'PKR',
        working_days_per_month INTEGER NOT NULL DEFAULT 26,
        overtime_multiplier REAL NOT NULL DEFAULT 1.5,
        late_grace_minutes INTEGER NOT NULL DEFAULT 15,
        late_penalty_days REAL NOT NULL DEFAULT 0.33, -- e.g. 3 lates = 1 day salary deduction
        late_threshold_count INTEGER NOT NULL DEFAULT 3,
        late_deduction_type TEXT NOT NULL DEFAULT 'percentage', -- 'percentage', 'fixed_amount', 'threshold_days', 'none'
        late_penalty_percent REAL NOT NULL DEFAULT 5.0, -- e.g. 5% of daily salary per late day
        late_fixed_amount REAL NOT NULL DEFAULT 100.0, -- e.g. PKR 100 per late day
        auto_sync_interval_seconds INTEGER NOT NULL DEFAULT 60,
        address TEXT DEFAULT 'Multan, Pakistan',
        phone TEXT DEFAULT '+92 300 1234567',
        email TEXT DEFAULT 'info@multanienterprises.com',
        logo_url TEXT DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Migration for settings table
    sett_cols = [c[1] for c in cursor.execute("PRAGMA table_info(company_settings)").fetchall()]
    if "late_deduction_type" not in sett_cols:
        cursor.execute("ALTER TABLE company_settings ADD COLUMN late_deduction_type TEXT DEFAULT 'percentage'")
    if "late_penalty_percent" not in sett_cols:
        cursor.execute("ALTER TABLE company_settings ADD COLUMN late_penalty_percent REAL DEFAULT 5.0")
    if "late_fixed_amount" not in sett_cols:
        cursor.execute("ALTER TABLE company_settings ADD COLUMN late_fixed_amount REAL DEFAULT 100.0")

    # 2. Shifts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_time TEXT NOT NULL DEFAULT '09:00',
        end_time TEXT NOT NULL DEFAULT '18:00',
        grace_minutes INTEGER NOT NULL DEFAULT 15,
        half_day_hours REAL NOT NULL DEFAULT 4.0,
        full_day_hours REAL NOT NULL DEFAULT 8.0,
        min_overtime_minutes INTEGER NOT NULL DEFAULT 30,
        work_days TEXT NOT NULL DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 3. Biometric Devices
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS biometric_devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ip_address TEXT NOT NULL,
        port INTEGER NOT NULL DEFAULT 8080,
        protocol TEXT NOT NULL DEFAULT 'auto', -- 'hikvision_isapi', 'tcp_zk', 'adms_http', 'auto'
        username TEXT DEFAULT 'admin',
        password TEXT DEFAULT '',
        device_model TEXT DEFAULT 'Hikvision / Biometric Terminal',
        auto_sync INTEGER DEFAULT 1,
        sync_interval_sec INTEGER DEFAULT 60,
        last_sync_time TIMESTAMP,
        last_status TEXT DEFAULT 'Ready',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 4. Employees
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        biometric_id TEXT UNIQUE NOT NULL, -- User ID on the biometric fingerprint machine
        name TEXT NOT NULL,
        department TEXT DEFAULT 'General',
        designation TEXT DEFAULT 'Staff',
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        joining_date TEXT DEFAULT '',
        shift_id INTEGER REFERENCES shifts(id),
        salary_type TEXT DEFAULT 'Monthly', -- 'Monthly', 'Daily', 'Hourly'
        basic_salary REAL NOT NULL DEFAULT 35000.0,
        housing_allowance REAL DEFAULT 0.0,
        transport_allowance REAL DEFAULT 0.0,
        medical_allowance REAL DEFAULT 0.0,
        other_allowance REAL DEFAULT 0.0,
        tax_deduction_rate REAL DEFAULT 0.0, -- Percentage
        start_time TEXT DEFAULT '09:00',
        end_time TEXT DEFAULT '18:00',
        grace_minutes INTEGER DEFAULT 15,
        work_hours REAL DEFAULT 8.0,
        work_days TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat',
        off_day TEXT DEFAULT 'Sun',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Migration for individual schedule columns if table already exists
    emp_cols = [c[1] for c in cursor.execute("PRAGMA table_info(employees)").fetchall()]
    if "start_time" not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN start_time TEXT DEFAULT '09:00'")
    if "end_time" not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN end_time TEXT DEFAULT '18:00'")
    if "grace_minutes" not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN grace_minutes INTEGER DEFAULT 15")
    if "work_hours" not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN work_hours REAL DEFAULT 8.0")
    if "work_days" not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN work_days TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat'")
    if "off_day" not in emp_cols:
        cursor.execute("ALTER TABLE employees ADD COLUMN off_day TEXT DEFAULT 'Sun'")

    # 5. Raw Attendance Punch Logs (from Biometric Machine / ADMS / USB Import)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS raw_attendance_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        biometric_id TEXT NOT NULL,
        punch_time TIMESTAMP NOT NULL,
        punch_type TEXT DEFAULT 'Auto', -- 'Check-In', 'Check-Out', 'Auto', 'Break-Out', 'Break-In'
        device_id INTEGER REFERENCES biometric_devices(id),
        source TEXT DEFAULT 'biometric_sync', -- 'biometric_sync', 'adms_push', 'manual_import', 'manual_entry'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(biometric_id, punch_time) ON CONFLICT IGNORE
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_logs_user_time ON raw_attendance_logs(biometric_id, punch_time)")

    # 6. Processed Daily Attendance
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL REFERENCES employees(id),
        date TEXT NOT NULL, -- 'YYYY-MM-DD'
        first_in TEXT,      -- 'HH:MM:SS'
        last_out TEXT,      -- 'HH:MM:SS'
        all_punches TEXT,   -- JSON array of all punch timestamps
        total_hours REAL DEFAULT 0.0,
        regular_hours REAL DEFAULT 0.0,
        overtime_hours REAL DEFAULT 0.0,
        late_minutes INTEGER DEFAULT 0,
        early_leave_minutes INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Present', -- 'Present', 'Late', 'Half Day', 'Early Leave', 'Absent', 'Leave', 'Holiday', 'Weekly Off'
        is_manual_override INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(employee_id, date) ON CONFLICT REPLACE
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_att_emp_date ON daily_attendance(employee_id, date)")

    # 7. Leaves
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leaves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL REFERENCES employees(id),
        leave_type TEXT NOT NULL DEFAULT 'Casual', -- 'Casual', 'Sick', 'Annual', 'Unpaid'
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        days_count REAL NOT NULL DEFAULT 1.0,
        reason TEXT DEFAULT '',
        status TEXT DEFAULT 'Approved', -- 'Approved', 'Pending', 'Rejected'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 8. Payroll Runs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payroll_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        month TEXT UNIQUE NOT NULL, -- 'YYYY-MM'
        total_employees INTEGER DEFAULT 0,
        total_gross_salary REAL DEFAULT 0.0,
        total_deductions REAL DEFAULT 0.0,
        total_net_salary REAL DEFAULT 0.0,
        status TEXT DEFAULT 'Generated', -- 'Draft', 'Generated', 'Finalized', 'Paid'
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 9. Individual Employee Payslips
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payslips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payroll_run_id INTEGER REFERENCES payroll_runs(id) ON DELETE CASCADE,
        employee_id INTEGER NOT NULL REFERENCES employees(id),
        month TEXT NOT NULL, -- 'YYYY-MM'
        basic_salary REAL NOT NULL,
        housing_allowance REAL DEFAULT 0.0,
        transport_allowance REAL DEFAULT 0.0,
        medical_allowance REAL DEFAULT 0.0,
        other_allowance REAL DEFAULT 0.0,
        overtime_hours REAL DEFAULT 0.0,
        overtime_pay REAL DEFAULT 0.0,
        bonus REAL DEFAULT 0.0,
        gross_salary REAL NOT NULL,
        
        -- Deductions
        total_present_days REAL DEFAULT 0.0,
        total_absent_days REAL DEFAULT 0.0,
        total_late_days INTEGER DEFAULT 0,
        total_leave_days REAL DEFAULT 0.0,
        absent_deduction REAL DEFAULT 0.0,
        late_deduction REAL DEFAULT 0.0,
        tax_deduction REAL DEFAULT 0.0,
        other_deduction REAL DEFAULT 0.0,
        total_deductions REAL DEFAULT 0.0,
        
        net_salary REAL NOT NULL,
        payment_status TEXT DEFAULT 'Unpaid', -- 'Unpaid', 'Paid'
        payment_date TEXT,
        payment_method TEXT DEFAULT 'Cash', -- 'Cash', 'Bank Transfer', 'Cheque'
        remarks TEXT DEFAULT '',
        breakdown_json TEXT, -- Full detailed calculation metadata
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(employee_id, month) ON CONFLICT REPLACE
    )
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
