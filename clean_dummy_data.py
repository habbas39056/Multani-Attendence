"""
Script to remove all sample/dummy demo data from the database.
Leaves ONLY real imported Multani Traders staff and their punches.
"""
import sqlite3
from payroll_engine import calculate_monthly_payroll

def clean_data():
    conn = sqlite3.connect("payroll_attendance.db")
    cursor = conn.cursor()

    # Find dummy employees (101, 102, 103, 104, 105)
    cursor.execute("SELECT id, biometric_id, name FROM employees WHERE biometric_id IN ('101', '102', '103', '104', '105')")
    dummy_emps = cursor.fetchall()
    print("Dummy employees to remove:", dummy_emps)

    dummy_ids = [r[0] for r in dummy_emps]
    dummy_bio_ids = [r[1] for r in dummy_emps]

    if dummy_ids:
        placeholders = ",".join("?" for _ in dummy_ids)
        cursor.execute(f"DELETE FROM payslips WHERE employee_id IN ({placeholders})", dummy_ids)
        cursor.execute(f"DELETE FROM daily_attendance WHERE employee_id IN ({placeholders})", dummy_ids)
        cursor.execute(f"DELETE FROM leaves WHERE employee_id IN ({placeholders})", dummy_ids)
        cursor.execute(f"DELETE FROM employees WHERE id IN ({placeholders})", dummy_ids)

    if dummy_bio_ids:
        placeholders_bio = ",".join("?" for _ in dummy_bio_ids)
        cursor.execute(f"DELETE FROM raw_attendance_logs WHERE biometric_id IN ({placeholders_bio})", dummy_bio_ids)

    cursor.execute("DELETE FROM raw_attendance_logs WHERE source = 'simulator'")
    conn.commit()

    # List remaining employees
    cursor.execute("SELECT id, biometric_id, name, department FROM employees ORDER BY CAST(biometric_id AS INTEGER) ASC")
    real_emps = cursor.fetchall()
    print(f"\nRemaining REAL Employees ({len(real_emps)}):")
    for e in real_emps:
        print(f"  ID {e[1]}: {e[2]} ({e[3]})")

    conn.close()

    # Recalculate August 2026 and September 2026 payroll
    res_aug = calculate_monthly_payroll("2026-08")
    print("\nClean August 2026 Payroll:", res_aug)
    res_sep = calculate_monthly_payroll("2026-09")
    print("Clean September 2026 Payroll:", res_sep)

if __name__ == "__main__":
    clean_data()
