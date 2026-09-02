-- =========================================================================
-- MULTANI TRADERS - SUPABASE POSTGRESQL DATABASE SCHEMA
-- Execute this script in your Supabase SQL Editor (https://supabase.com/dashboard)
-- =========================================================================

-- 1. Company Settings
CREATE TABLE IF NOT EXISTS company_settings (
    id SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL DEFAULT 'Multani Traders',
    currency TEXT NOT NULL DEFAULT 'PKR',
    working_days_per_month INTEGER NOT NULL DEFAULT 26,
    overtime_multiplier NUMERIC NOT NULL DEFAULT 1.5,
    late_grace_minutes INTEGER NOT NULL DEFAULT 15,
    late_deduction_type TEXT NOT NULL DEFAULT 'percentage', -- 'percentage', 'fixed_amount', 'threshold_days', 'none'
    late_penalty_percent NUMERIC NOT NULL DEFAULT 5.0,
    late_fixed_amount NUMERIC NOT NULL DEFAULT 100.0,
    late_penalty_days NUMERIC NOT NULL DEFAULT 1.0,
    late_threshold_count INTEGER NOT NULL DEFAULT 3,
    auto_sync_interval_seconds INTEGER NOT NULL DEFAULT 60,
    address TEXT DEFAULT 'Multani Shop, Pakistan',
    phone TEXT DEFAULT '+92 300 1234567',
    email TEXT DEFAULT 'info@multani.com',
    logo_url TEXT DEFAULT '',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Shifts
CREATE TABLE IF NOT EXISTS shifts (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    start_time TEXT NOT NULL DEFAULT '09:00',
    end_time TEXT NOT NULL DEFAULT '18:00',
    grace_minutes INTEGER NOT NULL DEFAULT 15,
    half_day_hours NUMERIC NOT NULL DEFAULT 4.0,
    full_day_hours NUMERIC NOT NULL DEFAULT 8.0,
    min_overtime_minutes INTEGER NOT NULL DEFAULT 30,
    work_days TEXT NOT NULL DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Biometric Devices
CREATE TABLE IF NOT EXISTS biometric_devices (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 8080,
    protocol TEXT NOT NULL DEFAULT 'auto',
    username TEXT DEFAULT 'admin',
    password TEXT DEFAULT '',
    device_model TEXT DEFAULT 'Hikvision / Biometric Terminal',
    auto_sync INTEGER DEFAULT 1,
    sync_interval_sec INTEGER DEFAULT 60,
    last_sync_time TIMESTAMP WITH TIME ZONE,
    last_status TEXT DEFAULT 'Ready',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Employees
CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    biometric_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    department TEXT DEFAULT 'Multani Shop',
    designation TEXT DEFAULT 'Staff',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    joining_date TEXT DEFAULT '',
    shift_id INTEGER REFERENCES shifts(id),
    salary_type TEXT DEFAULT 'Monthly',
    basic_salary NUMERIC NOT NULL DEFAULT 40000.0,
    housing_allowance NUMERIC DEFAULT 4800.0,
    transport_allowance NUMERIC DEFAULT 3200.0,
    medical_allowance NUMERIC DEFAULT 0.0,
    other_allowance NUMERIC DEFAULT 0.0,
    tax_deduction_rate NUMERIC DEFAULT 0.0,
    start_time TEXT DEFAULT '09:00',
    end_time TEXT DEFAULT '18:00',
    grace_minutes INTEGER DEFAULT 15,
    work_hours NUMERIC DEFAULT 8.0,
    work_days TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat',
    off_day TEXT DEFAULT 'Sun',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Raw Attendance Logs
CREATE TABLE IF NOT EXISTS raw_attendance_logs (
    id SERIAL PRIMARY KEY,
    biometric_id TEXT NOT NULL,
    punch_time TIMESTAMP WITH TIME ZONE NOT NULL,
    punch_type TEXT DEFAULT 'Auto',
    device_id INTEGER REFERENCES biometric_devices(id),
    source TEXT DEFAULT 'biometric_sync',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(biometric_id, punch_time)
);

-- 6. Daily Attendance Records
CREATE TABLE IF NOT EXISTS daily_attendance (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    date DATE NOT NULL,
    first_in TEXT,
    last_out TEXT,
    all_punches TEXT,
    total_hours NUMERIC DEFAULT 0.0,
    regular_hours NUMERIC DEFAULT 0.0,
    overtime_hours NUMERIC DEFAULT 0.0,
    late_minutes INTEGER DEFAULT 0,
    early_leave_minutes INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Absent',
    is_manual_override INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(employee_id, date)
);

-- 7. Leaves
CREATE TABLE IF NOT EXISTS leaves (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    leave_type TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'Approved',
    approved_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 8. Payroll Runs
CREATE TABLE IF NOT EXISTS payroll_runs (
    id SERIAL PRIMARY KEY,
    month TEXT UNIQUE NOT NULL,
    run_date DATE DEFAULT CURRENT_DATE,
    total_employees INTEGER DEFAULT 0,
    total_gross_salary NUMERIC DEFAULT 0.0,
    total_deductions NUMERIC DEFAULT 0.0,
    total_net_salary NUMERIC DEFAULT 0.0,
    status TEXT DEFAULT 'Draft',
    processed_by TEXT DEFAULT 'System',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 9. Payslips
CREATE TABLE IF NOT EXISTS payslips (
    id SERIAL PRIMARY KEY,
    payroll_run_id INTEGER REFERENCES payroll_runs(id),
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    month TEXT NOT NULL,
    basic_salary NUMERIC NOT NULL,
    housing_allowance NUMERIC DEFAULT 0.0,
    transport_allowance NUMERIC DEFAULT 0.0,
    medical_allowance NUMERIC DEFAULT 0.0,
    other_allowance NUMERIC DEFAULT 0.0,
    overtime_hours NUMERIC DEFAULT 0.0,
    overtime_pay NUMERIC DEFAULT 0.0,
    bonus NUMERIC DEFAULT 0.0,
    gross_salary NUMERIC NOT NULL,
    total_working_days NUMERIC DEFAULT 26.0,
    total_present_days NUMERIC DEFAULT 0.0,
    total_absent_days NUMERIC DEFAULT 0.0,
    total_late_days INTEGER DEFAULT 0,
    total_leave_days NUMERIC DEFAULT 0.0,
    total_holiday_days NUMERIC DEFAULT 0.0,
    absent_deduction NUMERIC DEFAULT 0.0,
    late_deduction NUMERIC DEFAULT 0.0,
    tax_deduction NUMERIC DEFAULT 0.0,
    other_deduction NUMERIC DEFAULT 0.0,
    total_deductions NUMERIC DEFAULT 0.0,
    net_salary NUMERIC NOT NULL,
    payment_status TEXT DEFAULT 'Unpaid',
    payment_date DATE,
    payment_method TEXT DEFAULT 'Cash',
    breakdown_json TEXT,
    remarks TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(employee_id, month)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_supa_raw_logs_user_time ON raw_attendance_logs(biometric_id, punch_time);
CREATE INDEX IF NOT EXISTS idx_supa_daily_att_date ON daily_attendance(date);
CREATE INDEX IF NOT EXISTS idx_supa_daily_att_emp ON daily_attendance(employee_id);
CREATE INDEX IF NOT EXISTS idx_supa_payslips_month ON payslips(month);

-- Disable RLS (Row Level Security) so your desktop software can read/write data seamlessly
ALTER TABLE company_settings DISABLE ROW LEVEL SECURITY;
ALTER TABLE shifts DISABLE ROW LEVEL SECURITY;
ALTER TABLE biometric_devices DISABLE ROW LEVEL SECURITY;
ALTER TABLE employees DISABLE ROW LEVEL SECURITY;
ALTER TABLE raw_attendance_logs DISABLE ROW LEVEL SECURITY;
ALTER TABLE daily_attendance DISABLE ROW LEVEL SECURITY;
ALTER TABLE leaves DISABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_runs DISABLE ROW LEVEL SECURITY;
ALTER TABLE payslips DISABLE ROW LEVEL SECURITY;

-- Insert Initial Company & Shift Data if empty
INSERT INTO company_settings (id, company_name, currency, address) 
VALUES (1, 'Multani Traders', 'PKR', 'Multani Shop, Pakistan') 
ON CONFLICT (id) DO NOTHING;

INSERT INTO shifts (id, name, start_time, end_time, grace_minutes, full_day_hours) 
VALUES (1, 'Standard Shop Shift', '09:00', '18:00', 15, 8.0) 
ON CONFLICT (id) DO NOTHING;
