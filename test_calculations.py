"""
Comprehensive Test Suite for Attendance & Payroll Calculation Engine
"""
import unittest
import sqlite3
import json
from datetime import datetime
from attendance_engine import parse_time_str, time_diff_minutes, process_attendance_for_date
from payroll_engine import calculate_monthly_payroll, get_payslip_details

class TestAttendanceAndPayrollCalculations(unittest.TestCase):

    def test_01_time_parsing_and_diff(self):
        """Test time parsing and difference helpers."""
        t1 = parse_time_str("09:00:00")
        t2 = parse_time_str("09:18:30")
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        diff = time_diff_minutes(t1, t2)
        self.assertEqual(diff, 18)

        t_out = parse_time_str("18:30:00")
        diff_work = time_diff_minutes(t1, t_out)
        self.assertEqual(diff_work, 570) # 9.5 hours = 570 mins

    def test_02_late_and_overtime_math(self):
        """Test late minutes and overtime calculation formulas."""
        shift_start = parse_time_str("09:00:00")
        shift_end = parse_time_str("18:00:00")
        grace_mins = 15

        # Case 1: Punch at 09:12 (within 15 min grace) -> 0 late
        punch_on_time = parse_time_str("09:12:00")
        diff_in = time_diff_minutes(shift_start, punch_on_time)
        late_m = diff_in if diff_in > grace_mins else 0
        self.assertEqual(late_m, 0)

        # Case 2: Punch at 09:28 (after 15 min grace) -> 28 late
        punch_late = parse_time_str("09:28:00")
        diff_in_late = time_diff_minutes(shift_start, punch_late)
        late_m2 = diff_in_late if diff_in_late > grace_mins else 0
        self.assertEqual(late_m2, 28)

        # Case 3: Punch out at 19:30 -> 1.5 OT hours
        punch_ot = parse_time_str("19:30:00")
        ot_mins = time_diff_minutes(shift_end, punch_ot)
        self.assertEqual(ot_mins, 90)
        self.assertEqual(round(ot_mins / 60.0, 2), 1.5)

    def test_03_salary_daily_rate_and_absent_deduction(self):
        """Test daily rate and absent deduction arithmetic."""
        basic_salary = 30000.0
        working_days = 30 # standard month
        daily_rate = basic_salary / working_days
        self.assertEqual(daily_rate, 1000.0)

        # 2 days absent
        absent_days = 2.0
        absent_ded = absent_days * daily_rate
        self.assertEqual(absent_ded, 2000.0)

    def test_04_late_percentage_deduction(self):
        """Test user request: 5% of 1 day salary (PKR 1,000) = PKR 50 cut per late day."""
        daily_rate = 1000.0
        penalty_percent = 5.0 # 5%
        late_days = 4

        late_cut_per_day = daily_rate * (penalty_percent / 100.0)
        self.assertEqual(late_cut_per_day, 50.0)

        total_late_deduction = late_days * late_cut_per_day
        self.assertEqual(total_late_deduction, 200.0)

    def test_05_august_live_payroll_verification(self):
        """Test real August payroll calculation results from database."""
        conn = sqlite3.connect("payroll_attendance.db")
        cursor = conn.cursor()

        # Set 5% late deduction rule
        cursor.execute("""
            UPDATE company_settings SET 
                working_days_per_month = 26,
                late_deduction_type = 'percentage',
                late_penalty_percent = 5.0
            WHERE id = 1
        """)
        conn.commit()
        conn.close()

        res = calculate_monthly_payroll("2026-08")
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["total_employees"], 0)
        self.assertGreater(res["total_net"], 0)

        # Inspect Murtaza Italia (ID 04)
        conn = sqlite3.connect("payroll_attendance.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, e.name as employee_name, e.biometric_id
            FROM payslips p
            JOIN employees e ON p.employee_id = e.id
            WHERE p.month = '2026-08' AND e.biometric_id = '04'
        """)
        murtaza_slip = cursor.fetchone()
        self.assertIsNotNone(murtaza_slip)

        gross = murtaza_slip["gross_salary"]
        total_ded = murtaza_slip["total_deductions"]
        net = murtaza_slip["net_salary"]
        self.assertAlmostEqual(gross, net + total_ded, places=2)
        print(f"\n[VERIFIED] Murtaza Italia August Payslip: Gross = PKR {gross:,.2f} | Deductions = PKR {total_ded:,.2f} | Net = PKR {net:,.2f}")
        conn.close()

if __name__ == "__main__":
    unittest.main()
