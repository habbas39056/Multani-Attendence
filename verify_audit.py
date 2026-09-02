import sqlite3

conn = sqlite3.connect("payroll_attendance.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT p.*, e.name as emp_name, e.biometric_id
    FROM payslips p
    JOIN employees e ON p.employee_id = e.id
    WHERE p.month = '2026-08'
    ORDER BY CAST(e.biometric_id AS INTEGER) ASC
""")
slips = cursor.fetchall()
print("=" * 115)
print(f"{'ID':<4} | {'Employee Name':<20} | {'Pres':<5} | {'Abs':<5} | {'Late':<5} | {'Basic':<9} | {'Gross':<9} | {'Abs Ded':<9} | {'Late Ded':<9} | {'Net Pay':<10}")
print("=" * 115)
for s in slips:
    bio = s["biometric_id"]
    name = s["emp_name"]
    pres = s["total_present_days"]
    abs_d = s["total_absent_days"]
    late = s["total_late_days"]
    basic = s["basic_salary"]
    gross = s["gross_salary"]
    abs_ded = s["absent_deduction"]
    late_ded = s["late_deduction"]
    net = s["net_salary"]
    print(f"{bio:<4} | {name:<20} | {pres:<5.1f} | {abs_d:<5.1f} | {late:<5} | PKR {basic:<5.0f} | PKR {gross:<5.0f} | PKR {abs_ded:<5.0f} | PKR {late_ded:<5.0f} | PKR {net:<6.0f}")
print("=" * 115)
conn.close()
