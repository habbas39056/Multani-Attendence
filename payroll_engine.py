"""
Payroll Calculation Engine for Multani Attendance & Payroll System
Computes monthly payroll, basic salary, allowances, overtime pay, absent deductions, late deductions, taxes, and net pay.
"""
import calendar
from datetime import datetime
import json
from database import get_db_connection

def calculate_monthly_payroll(month_str: str, bonus_map: dict = None, remarks_map: dict = None):
    """
    Generates or recalculates payroll for all active employees for the given month (format: 'YYYY-MM').
    Returns summary stats and payslip list.
    """
    if not bonus_map:
        bonus_map = {}
    if not remarks_map:
        remarks_map = {}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        year, month = map(int, month_str.split('-'))
        days_in_month = calendar.monthrange(year, month)[1]
    except Exception:
        conn.close()
        return {"error": "Invalid month format. Expected YYYY-MM"}

    # Fetch company settings
    cursor.execute("SELECT * FROM company_settings LIMIT 1")
    settings = cursor.fetchone()
    if not settings:
        # Default fallback
        working_days_std = 26
        ot_multiplier = 1.5
        late_deduction_type = "percentage"
        late_penalty_percent = 5.0
        late_fixed_amount = 100.0
        late_threshold = 3
        late_penalty_days = 1.0
    else:
        working_days_std = settings["working_days_per_month"] or 26
        ot_multiplier = settings["overtime_multiplier"] or 1.5
        late_deduction_type = settings["late_deduction_type"] or "percentage"
        late_penalty_percent = float(settings["late_penalty_percent"] if settings["late_penalty_percent"] is not None else 5.0)
        late_fixed_amount = float(settings["late_fixed_amount"] if settings["late_fixed_amount"] is not None else 100.0)
        late_threshold = settings["late_threshold_count"] if settings["late_threshold_count"] is not None else 3
        late_penalty_days = float(settings["late_penalty_days"] if settings["late_penalty_days"] is not None else 1.0)

    # Fetch all active employees
    cursor.execute("""
        SELECT e.*, s.name as shift_name, s.full_day_hours 
        FROM employees e
        LEFT JOIN shifts s ON e.shift_id = s.id
        WHERE e.is_active = 1
        ORDER BY e.id ASC
    """)
    employees = cursor.fetchall()

    if not employees:
        conn.close()
        return {"error": "No active employees found"}

    # Create / update payroll run record
    cursor.execute("""
        INSERT OR IGNORE INTO payroll_runs (month, status)
        VALUES (?, 'Draft')
    """, (month_str,))
    conn.commit()

    cursor.execute("SELECT id FROM payroll_runs WHERE month = ?", (month_str,))
    run_id = cursor.fetchone()["id"]

    total_gross = 0.0
    total_deductions_all = 0.0
    total_net = 0.0
    payslips_generated = []

    for emp in employees:
        emp_id = emp["id"]
        basic_salary = float(emp["basic_salary"] or 0.0)
        housing = float(emp["housing_allowance"] or 0.0)
        transport = float(emp["transport_allowance"] or 0.0)
        medical = float(emp["medical_allowance"] or 0.0)
        other_allowance = float(emp["other_allowance"] or 0.0)
        tax_rate = float(emp["tax_deduction_rate"] or 0.0)
        full_day_hrs = float(emp["full_day_hours"] or 8.0)
        bonus = float(bonus_map.get(str(emp_id), 0.0))
        remarks = remarks_map.get(str(emp_id), "")

        # Fetch attendance for this employee in this month
        cursor.execute("""
            SELECT date, status, total_hours, overtime_hours, late_minutes, early_leave_minutes 
            FROM daily_attendance 
            WHERE employee_id = ? AND date LIKE ?
        """, (emp_id, f"{month_str}%"))
        attendances = cursor.fetchall()

        present_days = 0.0
        absent_days = 0.0
        late_days = 0
        leave_days = 0.0
        holiday_off_days = 0.0
        total_ot_hours = 0.0
        total_late_minutes = 0

        for att in attendances:
            st = att["status"] or "Absent"
            ot = float(att["overtime_hours"] or 0.0)
            late_m = int(att["late_minutes"] or 0)
            total_ot_hours += ot
            total_late_minutes += late_m

            if st in ["Present", "Early Leave", "Holiday Present"]:
                present_days += 1.0
            elif st == "Late":
                present_days += 1.0
                late_days += 1
            elif st == "Half Day":
                present_days += 0.5
                absent_days += 0.5
            elif "Leave" in st:
                if "Unpaid" in st:
                    absent_days += 1.0
                else:
                    leave_days += 1.0
                    present_days += 1.0 # Paid leave
            elif st in ["Weekly Off", "Holiday"]:
                holiday_off_days += 1.0
            elif st == "Absent":
                absent_days += 1.0

        # Calculations
        # Standard Daily Rate = Basic Salary / Standard Working Days (e.g. 26)
        daily_rate = basic_salary / working_days_std if working_days_std > 0 else 0.0
        hourly_rate = daily_rate / full_day_hrs if full_day_hrs > 0 else 0.0

        # Overtime Pay
        overtime_pay = round(total_ot_hours * hourly_rate * ot_multiplier, 2)

        # Allowances
        total_allowances = housing + transport + medical + other_allowance

        # Deductions
        # 1. Absent Deduction
        absent_deduction = round(absent_days * daily_rate, 2)

        # 2. Late penalty deduction
        late_deduction = 0.0
        if late_days > 0:
            if late_deduction_type == "percentage":
                # Percentage of 1 day salary per late arrival (e.g. 5% of daily rate)
                late_deduction = round(late_days * daily_rate * (late_penalty_percent / 100.0), 2)
            elif late_deduction_type == "fixed_amount":
                # Fixed PKR amount per late day (e.g. PKR 100 per late day)
                late_deduction = round(late_days * late_fixed_amount, 2)
            elif late_deduction_type == "threshold_days":
                # X Late days = Y Days salary cut (e.g. 3 lates = 1 day salary cut)
                if late_threshold > 0 and late_days >= late_threshold:
                    penalty_units = late_days // late_threshold
                    late_deduction = round(penalty_units * late_penalty_days * daily_rate, 2)
            elif late_deduction_type == "none":
                late_deduction = 0.0

        # Gross Salary
        gross_salary = round(basic_salary + total_allowances + overtime_pay + bonus, 2)

        # 3. Tax Deduction
        tax_deduction = round((gross_salary * tax_rate) / 100.0, 2) if tax_rate > 0 else 0.0

        total_deductions = round(absent_deduction + late_deduction + tax_deduction, 2)
        net_salary = max(0.0, round(gross_salary - total_deductions, 2))

        # Detailed breakdown metadata
        breakdown = {
            "working_days_std": working_days_std,
            "days_in_month": days_in_month,
            "daily_rate": round(daily_rate, 2),
            "hourly_rate": round(hourly_rate, 2),
            "ot_multiplier": ot_multiplier,
            "present_days": present_days,
            "absent_days": absent_days,
            "late_days": late_days,
            "leave_days": leave_days,
            "holiday_off_days": holiday_off_days,
            "total_ot_hours": total_ot_hours,
            "total_late_minutes": total_late_minutes,
            "housing_allowance": housing,
            "transport_allowance": transport,
            "medical_allowance": medical,
            "other_allowance": other_allowance
        }

        cursor.execute("""
            INSERT OR REPLACE INTO payslips (
                payroll_run_id, employee_id, month, basic_salary, housing_allowance, 
                transport_allowance, medical_allowance, other_allowance, overtime_hours, 
                overtime_pay, bonus, gross_salary, total_present_days, total_absent_days, 
                total_late_days, total_leave_days, absent_deduction, late_deduction, 
                tax_deduction, other_deduction, total_deductions, net_salary, 
                remarks, breakdown_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            run_id, emp_id, month_str, basic_salary, housing,
            transport, medical, other_allowance, total_ot_hours,
            overtime_pay, bonus, gross_salary, present_days, absent_days,
            late_days, leave_days, absent_deduction, late_deduction,
            tax_deduction, 0.0, total_deductions, net_salary,
            remarks, json.dumps(breakdown)
        ))

        total_gross += gross_salary
        total_deductions_all += total_deductions
        total_net += net_salary
        payslips_generated.append(emp_id)

    # Update payroll run summary
    cursor.execute("""
        UPDATE payroll_runs 
        SET total_employees = ?, total_gross_salary = ?, total_deductions = ?, total_net_salary = ?, status = 'Generated'
        WHERE id = ?
    """, (len(payslips_generated), round(total_gross, 2), round(total_deductions_all, 2), round(total_net, 2), run_id))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "month": month_str,
        "payroll_run_id": run_id,
        "total_employees": len(payslips_generated),
        "total_gross": round(total_gross, 2),
        "total_deductions": round(total_deductions_all, 2),
        "total_net": round(total_net, 2)
    }

def get_payslip_details(payslip_id: int):
    """Retrieves complete payslip details with company settings and employee profile."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM company_settings LIMIT 1")
    settings = cursor.fetchone()

    cursor.execute("""
        SELECT p.*, e.name as employee_name, e.biometric_id, e.department, e.designation, 
               e.phone, e.email, e.joining_date, s.name as shift_name
        FROM payslips p
        JOIN employees e ON p.employee_id = e.id
        LEFT JOIN shifts s ON e.shift_id = s.id
        WHERE p.id = ?
    """, (payslip_id,))
    payslip = cursor.fetchone()

    conn.close()

    if not payslip:
        return None

    res = dict(payslip)
    if res.get("breakdown_json"):
        try:
            res["breakdown"] = json.loads(res["breakdown_json"])
        except Exception:
            res["breakdown"] = {}

    res["company"] = dict(settings) if settings else {}
    return res
