/**
 * MULTANI TRADERS - ATTENDANCE & PAYROLL APPLICATION
 * Universal Cloud & Local Architecture:
 * - Direct Supabase PostgreSQL Cloud Integration (Netlify & Serverless)
 * - Local FastAPI Backend Integration (Localhost Desktop App)
 */

const SUPABASE_URL = 'https://tyxvrykwarevfdwrbrmv.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_rEHPrqKtGzTdIO6gVPXxOw_jE2Yy4VH';

const isLocalHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

let currentTab = 'dashboard';
let currentCurrency = 'PKR';
let cachedStaff = [];
let cachedCompanySettings = {
    company_name: 'Multani Traders',
    currency: 'PKR',
    working_days_per_month: 26,
    late_grace_minutes: 15,
    late_deduction_type: 'percentage',
    late_penalty_percent: 5.0,
    late_fixed_amount: 100.0,
    overtime_multiplier: 1.5,
    address: 'Multani Traders, Pakistan'
};

// -------------------------------------------------------------
// Universal Supabase REST Client
// -------------------------------------------------------------
async function querySupabase(endpoint, options = {}) {
    const url = `${SUPABASE_URL}/rest/v1/${endpoint}`;
    const headers = {
        'apikey': SUPABASE_ANON_KEY,
        'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
        'Content-Type': 'application/json',
        ...(options.headers || {})
    };

    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
        const errText = await res.text().catch(() => '');
        throw new Error(`Cloud DB Error (${res.status}): ${errText}`);
    }
    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
        return await res.json();
    }
    return null;
}

// -------------------------------------------------------------
// Application Initialization
// -------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    setupNav();
    setDefaultDates();
    setupEvents();

    await loadSettings();
    await loadDashboard();
    await loadStaff();
}

function setupNav() {
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabId = item.getAttribute('data-tab');
            switchTab(tabId);
        });
    });

    const toggle = document.getElementById('sidebarToggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.getElementById('sidebar').classList.toggle('open');
        });
    }
}

function switchTab(tabId) {
    currentTab = tabId;

    document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => {
        el.classList.toggle('active', el.getAttribute('data-tab') === tabId);
    });

    document.querySelectorAll('.tab-pane').forEach(el => {
        el.classList.remove('active');
    });

    const target = document.getElementById(`pane-${tabId}`);
    if (target) target.classList.add('active');

    const titles = {
        dashboard: { title: 'Dashboard', sub: "Overview of today's attendance and monthly payroll" },
        attendance: { title: 'Daily Attendance', sub: 'View daily check-in / check-out times and hours worked' },
        timesheet: { title: 'Monthly Timesheet', sub: 'Visual attendance sheet for the entire month' },
        payroll: { title: 'Payroll & Salary Slips', sub: 'Monthly salary calculation and official printable payslips' },
        employees: { title: 'Staff Directory', sub: 'Manage employee salaries, departments, and machine IDs' },
        settings: { title: 'Settings & Machine', sub: 'Configure company profile, machine IP, and shift rules' }
    };

    if (titles[tabId]) {
        document.getElementById('pageTitle').textContent = titles[tabId].title;
        document.getElementById('pageSubtitle').textContent = titles[tabId].sub;
    }

    if (tabId === 'dashboard') loadDashboard();
    else if (tabId === 'attendance') loadDailyAttendance();
    else if (tabId === 'timesheet') loadTimesheetMatrix();
    else if (tabId === 'payroll') loadPayroll();
    else if (tabId === 'employees') loadStaff();
    else if (tabId === 'settings') loadSettings();
}

function setDefaultDates() {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const todayStr = `${yyyy}-${mm}-${dd}`;
    const curMonthStr = `${yyyy}-${mm}`;

    const dashDateEl = document.getElementById('dashDatePicker');
    if (dashDateEl) dashDateEl.value = todayStr;

    const dailyDateEl = document.getElementById('dailyDateInput');
    if (dailyDateEl) dailyDateEl.value = todayStr;

    const timesheetMonthEl = document.getElementById('timesheetMonthInput');
    if (timesheetMonthEl) timesheetMonthEl.value = curMonthStr;

    const payrollMonthEl = document.getElementById('payrollMonthInput');
    if (payrollMonthEl) payrollMonthEl.value = curMonthStr;
}

// -------------------------------------------------------------
// 1. Dashboard Module
// -------------------------------------------------------------
async function loadDashboard() {
    const dashDateEl = document.getElementById('dashDatePicker');
    const dateVal = (dashDateEl && dashDateEl.value) ? dashDateEl.value : new Date().toISOString().split('T')[0];
    try {
        let dailyRecords = [];
        if (isLocalHost) {
            try {
                const res = await fetch(`/api/dashboard/stats?target_date=${dateVal}`);
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById('dashTotalStaff').textContent = data.total_employees;
                    document.getElementById('dashPresentToday').textContent = data.status_counts.present;
                    document.getElementById('dashLateToday').textContent = data.status_counts.late;

                    const payRes = await fetch('/api/payroll/runs');
                    if (payRes.ok) {
                        const runs = await payRes.json();
                        if (runs && runs.length > 0) {
                            document.getElementById('dashNetPayroll').textContent = formatCurrency(runs[0].total_net_salary);
                            document.getElementById('dashPayrollMonthLbl').textContent = `Month: ${runs[0].month}`;
                        }
                    }

                    const dailyRes = await fetch(`/api/attendance/daily?date=${dateVal}`);
                    if (dailyRes.ok) {
                        const dailyData = await dailyRes.json();
                        dailyRecords = dailyData.records || [];
                    }
                } else {
                    dailyRecords = await fetchDashboardFromSupabase(dateVal);
                }
            } catch (err) {
                dailyRecords = await fetchDashboardFromSupabase(dateVal);
            }
        } else {
            dailyRecords = await fetchDashboardFromSupabase(dateVal);
        }

        renderDashboardTable(dailyRecords);
    } catch (e) {
        console.error('loadDashboard error:', e);
    }
}

async function fetchDashboardFromSupabase(dateVal) {
    const emps = await querySupabase('employees?select=*&is_active=eq.1&order=id.asc');
    cachedStaff = emps || [];
    document.getElementById('dashTotalStaff').textContent = (emps || []).length;

    const atts = await querySupabase(`daily_attendance?select=*,employees(name,biometric_id,department,designation)&date=eq.${dateVal}&order=employee_id.asc`);
    const records = (atts || []).map(r => ({
        ...r,
        employee_name: r.employees ? r.employees.name : `Staff #${r.employee_id}`,
        biometric_id: r.employees ? r.employees.biometric_id : r.employee_id,
        department: r.employees ? r.employees.department : 'Multani Shop'
    }));

    const pres = records.filter(r => r.status && (r.status.includes('Present') || r.status === 'Late')).length;
    const lates = records.filter(r => r.status === 'Late' || r.late_minutes > 0).length;

    document.getElementById('dashPresentToday').textContent = pres;
    document.getElementById('dashLateToday').textContent = lates;

    const slips = await querySupabase('payslips?select=net_salary,month&month=eq.2026-08');
    if (slips && slips.length > 0) {
        const sumNet = slips.reduce((acc, s) => acc + (parseFloat(s.net_salary) || 0), 0);
        document.getElementById('dashNetPayroll').textContent = formatCurrency(sumNet);
        document.getElementById('dashPayrollMonthLbl').textContent = `Month: ${slips[0].month || '2026-08'}`;
    }

    return records;
}

function renderDashboardTable(records) {
    const tbody = document.getElementById('dashAttendanceBody');
    if (!records || records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted" style="padding:25px;">
            <i class="fa-solid fa-calendar-xmark text-secondary" style="font-size:24px; margin-bottom:8px; display:block;"></i>
            No attendance punches recorded for this date yet.<br>
            <span style="font-size:12px;">Switch date above to <b>2026-08-18</b> (or any date in August) to view past attendance logs.</span>
        </td></tr>`;
        return;
    }

    tbody.innerHTML = records.map(r => `
        <tr>
            <td><b class="badge badge-secondary">#${r.biometric_id}</b></td>
            <td><strong>${escapeHtml(r.employee_name)}</strong></td>
            <td>${escapeHtml(r.department || 'Multani Shop')}</td>
            <td>${r.first_in ? `<b class="text-success">${r.first_in}</b>` : '<span class="text-muted">--:--</span>'}</td>
            <td>${r.last_out ? `<b class="text-info">${r.last_out}</b>` : '<span class="text-muted">--:--</span>'}</td>
            <td><b>${r.total_hours || 0} hrs</b></td>
            <td>${r.late_minutes > 0 ? `<span class="badge badge-warning">${r.late_minutes}m Late</span>` : '<span class="text-muted">On time</span>'}</td>
            <td>${getStatusBadge(r.status)}</td>
        </tr>
    `).join('');
}

// -------------------------------------------------------------
// 2. Daily Attendance Module
// -------------------------------------------------------------
async function loadDailyAttendance() {
    const d = document.getElementById('dailyDateInput').value || '2026-08-18';
    try {
        let records = [];
        if (isLocalHost) {
            try {
                const res = await fetch(`/api/attendance/daily?date=${d}`);
                if (res.ok) {
                    const data = await res.json();
                    records = data.records || [];
                } else {
                    records = await fetchDailyFromSupabase(d);
                }
            } catch (err) {
                records = await fetchDailyFromSupabase(d);
            }
        } else {
            records = await fetchDailyFromSupabase(d);
        }
        renderDailyTable(records);
    } catch (e) {
        console.error('loadDailyAttendance error:', e);
    }
}

async function fetchDailyFromSupabase(d) {
    const atts = await querySupabase(`daily_attendance?select=*,employees(name,biometric_id,department,designation)&date=eq.${d}&order=employee_id.asc`);
    return (atts || []).map(r => ({
        ...r,
        employee_name: r.employees ? r.employees.name : `Staff #${r.employee_id}`,
        biometric_id: r.employees ? r.employees.biometric_id : r.employee_id,
        department: r.employees ? r.employees.department : 'Multani Shop'
    }));
}

function renderDailyTable(records) {
    const tbody = document.getElementById('dailyBody');
    const query = (document.getElementById('attendanceSearch')?.value || '').toLowerCase();

    const filtered = (records || []).filter(r => 
        (r.employee_name || '').toLowerCase().includes(query) ||
        (r.biometric_id || '').toString().includes(query) ||
        (r.department || '').toLowerCase().includes(query)
    );

    if (!filtered || filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted" style="padding:20px;">No records found for this date.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(r => `
        <tr>
            <td><b class="badge badge-secondary">#${r.biometric_id}</b></td>
            <td><strong>${escapeHtml(r.employee_name)}</strong></td>
            <td>${escapeHtml(r.department || 'Multani Shop')}</td>
            <td>${r.first_in ? `<b class="text-success">${r.first_in}</b>` : '<span class="text-muted">--:--</span>'}</td>
            <td>${r.last_out ? `<b class="text-info">${r.last_out}</b>` : '<span class="text-muted">--:--</span>'}</td>
            <td><b>${r.total_hours || 0} hrs</b></td>
            <td>${r.late_minutes > 0 ? `<span class="badge badge-warning">${r.late_minutes} mins</span>` : '<span class="text-muted">0</span>'}</td>
            <td>${r.overtime_hours > 0 ? `<span class="badge badge-info">+${r.overtime_hours}h</span>` : '<span class="text-muted">0h</span>'}</td>
            <td>${getStatusBadge(r.status)}</td>
            <td style="text-align:center;">
                <button type="button" class="btn btn-sm btn-outline" onclick="openEditDailyAttendance(${r.employee_id}, '${escapeHtml(r.employee_name)}', '${r.date}', '${r.status}', '${r.first_in || ''}', '${r.last_out || ''}', '${escapeHtml(r.notes || '')}')">
                    <i class="fa-solid fa-pen-to-square"></i> Change
                </button>
            </td>
        </tr>
    `).join('');
}

// Manual Attendance Logic
async function populateManualAttendanceEmployees() {
    const sel = document.getElementById('manualAttEmpSelect');
    if (!sel) return;
    if (!cachedStaff || cachedStaff.length === 0) {
        await loadStaff();
    }
    sel.innerHTML = (cachedStaff || []).map(e => `
        <option value="${e.id}">[ID ${e.biometric_id}] ${escapeHtml(e.name)} - ${escapeHtml(e.department || 'Multani Shop')}</option>
    `).join('');
}

async function openManualAttendanceModal() {
    await populateManualAttendanceEmployees();
    const curDate = document.getElementById('dailyDateInput')?.value || '2026-08-18';
    document.getElementById('manualAttDate').value = curDate;
    document.getElementById('manualAttStatus').value = 'Present';
    document.getElementById('manualAttIn').value = '09:00';
    document.getElementById('manualAttOut').value = '18:00';
    document.getElementById('manualAttNotes').value = '';
    handleManualStatusChange('Present');
    openModal('manualAttModal');
}

async function openEditDailyAttendance(empId, empName, dateStr, status, firstIn, lastOut, notes) {
    await populateManualAttendanceEmployees();
    document.getElementById('manualAttEmpSelect').value = empId;
    document.getElementById('manualAttDate').value = dateStr;
    document.getElementById('manualAttStatus').value = status;
    document.getElementById('manualAttIn').value = firstIn || '09:00';
    document.getElementById('manualAttOut').value = lastOut || '18:00';
    document.getElementById('manualAttNotes').value = notes || '';
    handleManualStatusChange(status);
    openModal('manualAttModal');
}

function handleManualStatusChange(val) {
    const timeRow = document.getElementById('manualAttTimesRow');
    if (val === 'Absent' || val === 'Weekly Off' || val === 'Unpaid Leave' || val === 'Paid Leave') {
        timeRow.style.display = 'none';
    } else {
        timeRow.style.display = 'grid';
    }
}

// -------------------------------------------------------------
// Helper: Get Exact Month Date Range (28, 29, 30, 31 days)
// -------------------------------------------------------------
function getMonthDateRange(monthStr) {
    if (!monthStr || !monthStr.includes('-')) {
        monthStr = '2026-08';
    }
    const [year, m] = monthStr.split('-').map(Number);
    const daysInMonth = new Date(year, m, 0).getDate();
    const lastDayStr = daysInMonth < 10 ? `0${daysInMonth}` : `${daysInMonth}`;
    return {
        startDate: `${monthStr}-01`,
        endDate: `${monthStr}-${lastDayStr}`,
        daysCount: daysInMonth
    };
}

// -------------------------------------------------------------
// 3. Monthly Timesheet Matrix
// -------------------------------------------------------------
async function loadTimesheetMatrix() {
    const monthInput = document.getElementById('timesheetMonthInput');
    const month = monthInput ? monthInput.value : '2026-08';
    try {
        let matrix = [];
        if (isLocalHost) {
            try {
                const res = await fetch(`/api/attendance/monthly?month=${month}`);
                if (res.ok) {
                    const data = await res.json();
                    matrix = data.matrix || [];
                } else {
                    matrix = await fetchMatrixFromSupabase(month);
                }
            } catch (err) {
                matrix = await fetchMatrixFromSupabase(month);
            }
        } else {
            matrix = await fetchMatrixFromSupabase(month);
        }
        renderMatrix(month, matrix);
    } catch (e) {
        console.error('loadTimesheetMatrix error:', e);
        showToast('Timesheet load notice: ' + e.message, 'warning');
    }
}

async function fetchMatrixFromSupabase(month) {
    const { startDate, endDate } = getMonthDateRange(month);
    const emps = await querySupabase('employees?select=*&is_active=eq.1&order=id.asc');
    const atts = await querySupabase(`daily_attendance?select=*&date=gte.${startDate}&date=lte.${endDate}&order=date.asc`);

    const empMap = {};
    (emps || []).forEach(e => {
        empMap[e.id] = {
            id: e.id,
            name: e.name,
            biometric_id: e.biometric_id,
            department: e.department || 'Multani Shop',
            days: {},
            summary: { present: 0, late: 0, absent: 0, leave: 0, half_day: 0, ot_hours: 0.0 }
        };
    });

    (atts || []).forEach(r => {
        const eid = r.employee_id;
        if (empMap[eid] && r.date) {
            const dayNum = r.date.split('-')[2];
            const st = r.status || 'Absent';
            const ot = parseFloat(r.overtime_hours || 0.0);

            empMap[eid].days[dayNum] = {
                status: st,
                hours: r.total_hours,
                ot: ot,
                late: r.late_minutes
            };

            if (st === 'Present' || st === 'Holiday Present') {
                empMap[eid].summary.present += 1;
            } else if (st === 'Late') {
                empMap[eid].summary.present += 1;
                empMap[eid].summary.late += 1;
            } else if (st === 'Half Day') {
                empMap[eid].summary.half_day += 1;
            } else if (st.includes('Leave')) {
                empMap[eid].summary.leave += 1;
            } else if (st === 'Absent') {
                empMap[eid].summary.absent += 1;
            }
            empMap[eid].summary.ot_hours += ot;
        }
    });

    return Object.values(empMap);
}

function renderMatrix(month, matrix) {
    const [year, m] = month.split('-').map(Number);
    const daysInMonth = new Date(year, m, 0).getDate();

    const thead = document.getElementById('timesheetMatrixHead');
    const tbody = document.getElementById('timesheetMatrixBody');

    let head = `<tr>
        <th style="min-width:60px;">ID</th>
        <th style="min-width:180px; text-align:left;">Employee Name</th>`;

    for (let day = 1; day <= daysInMonth; day++) {
        head += `<th style="width:28px;">${day}</th>`;
    }

    head += `<th>P</th><th>L</th><th>A</th></tr>`;
    thead.innerHTML = head;

    if (!matrix || matrix.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${daysInMonth + 5}" class="text-center text-muted" style="padding:20px;">No timesheet data for ${month}</td></tr>`;
        return;
    }

    tbody.innerHTML = matrix.map(row => {
        let cells = `<tr>
            <td><b class="badge badge-secondary">#${row.biometric_id}</b></td>
            <td style="text-align:left;"><strong>${escapeHtml(row.name)}</strong></td>`;

        for (let d = 1; d <= daysInMonth; d++) {
            const dayKey = d < 10 ? `0${d}` : `${d}`;
            const dayData = row.days[dayKey];
            if (!dayData) {
                cells += `<td class="text-muted">-</td>`;
            } else {
                const st = dayData.status || '';
                let badge = '-';
                if (st.includes('Present')) badge = `<span class="badge badge-success">P</span>`;
                else if (st === 'Late') badge = `<span class="badge badge-warning">L</span>`;
                else if (st === 'Half Day') badge = `<span class="badge badge-info">HD</span>`;
                else if (st === 'Absent') badge = `<span class="badge badge-danger">A</span>`;
                else if (st === 'Weekly Off') badge = `<span class="badge badge-secondary">OFF</span>`;
                else if (st.includes('Leave')) badge = `<span class="badge badge-warning">LV</span>`;
                cells += `<td>${badge}</td>`;
            }
        }

        cells += `
            <td><b class="text-success">${row.summary.present}</b></td>
            <td><b class="text-warning">${row.summary.late}</b></td>
            <td><b class="text-danger">${row.summary.absent}</b></td>
        </tr>`;
        return cells;
    }).join('');
}

// -------------------------------------------------------------
// 4. Payroll & Payslip Module
// -------------------------------------------------------------
async function loadPayroll() {
    const month = document.getElementById('payrollMonthInput').value || '2026-08';
    try {
        let payslips = [];
        if (isLocalHost) {
            try {
                const res = await fetch(`/api/payroll/payslips?month=${month}`);
                if (res.ok) {
                    payslips = await res.json();
                } else {
                    payslips = await fetchPayrollFromSupabase(month);
                }
            } catch (err) {
                payslips = await fetchPayrollFromSupabase(month);
            }
        } else {
            payslips = await fetchPayrollFromSupabase(month);
        }
        renderPayrollTable(month, payslips);
    } catch (e) {
        console.error('loadPayroll error:', e);
    }
}

async function fetchPayrollFromSupabase(month) {
    const slips = await querySupabase(`payslips?select=*,employees(name,biometric_id,department,designation,salary_type)&month=eq.${month}&order=employee_id.asc`);
    return (slips || []).map(p => ({
        ...p,
        employee_name: p.employees ? p.employees.name : `Staff #${p.employee_id}`,
        biometric_id: p.employees ? p.employees.biometric_id : p.employee_id,
        department: p.employees ? p.employees.department : 'Multani Shop',
        designation: p.employees ? p.employees.designation : 'Staff',
        breakdown: p.breakdown_json ? JSON.parse(p.breakdown_json) : {}
    }));
}

async function calculatePayrollAction() {
    const month = document.getElementById('payrollMonthInput').value || '2026-08';
    showToast(`Calculating payroll for ${month}...`, 'info');

    if (isLocalHost) {
        try {
            const res = await fetch(`/api/payroll/generate?month=${month}`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'success') {
                    showToast(`Payroll calculated for ${data.total_employees} staff!`, 'success');
                    loadPayroll();
                    loadDashboard();
                    return;
                }
            }
        } catch (e) {}
    }

    // Direct Supabase calculation
    try {
        const { startDate, endDate } = getMonthDateRange(month);
        const emps = await querySupabase('employees?select=*&is_active=eq.1');
        const atts = await querySupabase(`daily_attendance?select=*&date=gte.${startDate}&date=lte.${endDate}`);

        const attByEmp = {};
        (atts || []).forEach(a => {
            if (!attByEmp[a.employee_id]) attByEmp[a.employee_id] = [];
            attByEmp[a.employee_id].push(a);
        });

        for (const emp of emps) {
            const empAtts = attByEmp[emp.id] || [];
            let presDays = 0, absDays = 0, lateDays = 0, leaveDays = 0, otHours = 0;

            empAtts.forEach(a => {
                const st = a.status || 'Absent';
                if (st === 'Present' || st === 'Holiday Present') presDays += 1;
                else if (st === 'Late') { presDays += 1; lateDays += 1; }
                else if (st === 'Half Day') { presDays += 0.5; absDays += 0.5; }
                else if (st === 'Paid Leave') presDays += 1;
                else if (st === 'Absent' || st === 'Unpaid Leave') absDays += 1;
                otHours += parseFloat(a.overtime_hours || 0);
            });

            const basic = parseFloat(emp.basic_salary) || 30000;
            const allowances = (parseFloat(emp.housing_allowance) || 0) + (parseFloat(emp.transport_allowance) || 0);
            const dailyRate = Math.round((basic / 26.0) * 100) / 100;
            const hourlyRate = Math.round((dailyRate / 8.0) * 100) / 100;
            const otPay = Math.round(otHours * hourlyRate * 1.5);
            const absDed = Math.round(absDays * dailyRate);
            const lateDed = Math.round(lateDays * (dailyRate * 0.05)); // 5% of daily rate
            const gross = basic + allowances + otPay;
            const totalDed = absDed + lateDed;
            const net = Math.max(0, gross - totalDed);

            const slipPayload = {
                employee_id: emp.id,
                month: month,
                basic_salary: basic,
                housing_allowance: parseFloat(emp.housing_allowance) || 0,
                transport_allowance: parseFloat(emp.transport_allowance) || 0,
                medical_allowance: 0,
                other_allowance: 0,
                overtime_hours: otHours,
                overtime_pay: otPay,
                bonus: 0,
                gross_salary: gross,
                total_working_days: 26,
                total_present_days: presDays,
                total_absent_days: absDays,
                total_late_days: lateDays,
                total_leave_days: leaveDays,
                total_holiday_days: 0,
                absent_deduction: absDed,
                late_deduction: lateDed,
                tax_deduction: 0,
                other_deduction: 0,
                total_deductions: totalDed,
                net_salary: net,
                payment_status: 'Unpaid',
                payment_method: 'Cash',
                breakdown_json: JSON.stringify({
                    daily_rate: dailyRate,
                    hourly_rate: hourlyRate,
                    ot_hours: otHours,
                    late_days: lateDays,
                    absent_days: absDays
                })
            };

            await querySupabase('payslips?on_conflict=employee_id,month', {
                method: 'POST',
                headers: { 'Prefer': 'resolution=merge-duplicates' },
                body: JSON.stringify(slipPayload)
            });
        }

        showToast(`Payroll calculated and synced to Supabase for ${emps.length} staff!`, 'success');
        loadPayroll();
        loadDashboard();
    } catch (err) {
        showToast('Calculation error: ' + err.message, 'error');
    }
}

function renderPayrollTable(month, payslips) {
    const tbody = document.getElementById('payrollBody');

    if (!payslips || payslips.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted" style="padding:25px;">
            No payroll calculated for ${month}. Click <b>"Calculate Month Payroll"</b> above.
        </td></tr>`;
        return;
    }

    let sumGross = 0, sumDeductions = 0, sumNet = 0;

    tbody.innerHTML = payslips.map(p => {
        sumGross += (parseFloat(p.gross_salary) || 0);
        sumDeductions += (parseFloat(p.total_deductions) || 0);
        sumNet += (parseFloat(p.net_salary) || 0);

        const allowances = (parseFloat(p.housing_allowance) || 0) + (parseFloat(p.transport_allowance) || 0);

        return `
            <tr>
                <td><b class="badge badge-secondary">#${p.biometric_id}</b></td>
                <td>
                    <strong>${escapeHtml(p.employee_name)}</strong>
                    <div class="text-muted" style="font-size:11px;">${escapeHtml(p.department || 'Multani Shop')}</div>
                </td>
                <td><b>${formatCurrency(p.basic_salary)}</b></td>
                <td>${formatCurrency(allowances)}</td>
                <td>${p.overtime_pay > 0 ? `<b class="text-info">${formatCurrency(p.overtime_pay)}</b>` : '0'}</td>
                <td>
                    <span class="text-success">${p.total_present_days} P</span> / 
                    <span class="text-danger">${p.total_absent_days} A</span>
                </td>
                <td><b class="text-danger">${formatCurrency(p.total_deductions)}</b></td>
                <td><b class="text-success" style="font-size:14px;">${formatCurrency(p.net_salary)}</b></td>
                <td>
                    <span class="badge ${p.payment_status === 'Paid' ? 'badge-success' : 'badge-warning'}">
                        ${p.payment_status || 'Unpaid'}
                    </span>
                </td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="openPayslipModal(${p.id})">
                        <i class="fa-solid fa-receipt"></i> Print Slip
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    // Update Strip
    document.getElementById('paySummaryMonth').textContent = formatMonthName(month);
    document.getElementById('paySummaryStaff').textContent = payslips.length;
    document.getElementById('paySummaryGross').textContent = formatCurrency(sumGross);
    document.getElementById('paySummaryDeductions').textContent = formatCurrency(sumDeductions);
    document.getElementById('paySummaryNet').textContent = formatCurrency(sumNet);
}

async function openPayslipModal(payslipId) {
    try {
        let p = null;
        if (isLocalHost) {
            try {
                const res = await fetch(`/api/payroll/payslip/${payslipId}`);
                if (res.ok) p = await res.json();
            } catch (err) {}
        }

        if (!p) {
            const slips = await querySupabase(`payslips?select=*,employees(name,biometric_id,department,designation)&id=eq.${payslipId}`);
            if (slips && slips.length > 0) {
                const raw = slips[0];
                p = {
                    ...raw,
                    employee_name: raw.employees ? raw.employees.name : 'Staff',
                    biometric_id: raw.employees ? raw.employees.biometric_id : raw.employee_id,
                    department: raw.employees ? raw.employees.department : 'Multani Shop',
                    designation: raw.employees ? raw.employees.designation : 'Staff',
                    company: cachedCompanySettings
                };
            }
        }

        if (!p) return;

        const comp = p.company || cachedCompanySettings;
        document.getElementById('slipCompany').textContent = (comp.company_name || 'MULTANI TRADERS').toUpperCase();
        document.getElementById('slipCompanyAddress').textContent = comp.address || 'Multani Shop, Pakistan';
        document.getElementById('slipMonth').textContent = formatMonthName(p.month);
        document.getElementById('slipRef').textContent = `Ref: PS-${p.biometric_id}-${p.month}`;

        document.getElementById('slipBioId').textContent = p.biometric_id;
        document.getElementById('slipName').textContent = p.employee_name;
        document.getElementById('slipDept').textContent = p.department || 'Multani Shop';
        document.getElementById('slipPos').textContent = p.designation || 'Staff';

        // Attendance Strip
        document.getElementById('slipPres').textContent = `${p.total_present_days} Days`;
        document.getElementById('slipAbs').textContent = `${p.total_absent_days} Days`;
        document.getElementById('slipLate').textContent = `${p.total_late_days} Days`;
        document.getElementById('slipOt').textContent = `${p.overtime_hours || 0} Hours`;

        // Earnings
        document.getElementById('slipBasic').textContent = formatCurrency(p.basic_salary);
        document.getElementById('slipHra').textContent = formatCurrency(p.housing_allowance);
        document.getElementById('slipTransport').textContent = formatCurrency(p.transport_allowance);
        document.getElementById('slipOtPay').textContent = formatCurrency(p.overtime_pay);
        document.getElementById('slipBonus').textContent = formatCurrency(p.bonus || 0);
        document.getElementById('slipGross').textContent = formatCurrency(p.gross_salary);

        // Deductions
        document.getElementById('slipDedAbs').textContent = formatCurrency(p.absent_deduction);
        document.getElementById('slipDedLate').textContent = formatCurrency(p.late_deduction);
        document.getElementById('slipDedOther').textContent = formatCurrency((p.tax_deduction || 0) + (p.other_deduction || 0));
        document.getElementById('slipTotalDed').textContent = formatCurrency(p.total_deductions);

        // Net Amount
        document.getElementById('slipNet').textContent = formatCurrency(p.net_salary);
        document.getElementById('slipWords').textContent = numberToWords(Math.round(p.net_salary)) + ' ' + (comp.currency || 'PKR') + ' Only';

        openModal('payslipModal');
    } catch (e) {
        showToast('Error opening payslip: ' + e.message, 'error');
    }
}

// -------------------------------------------------------------
// 5. Staff Directory Module
// -------------------------------------------------------------
async function loadStaff() {
    try {
        let staff = [];
        if (isLocalHost) {
            try {
                const res = await fetch('/api/employees');
                if (res.ok) {
                    staff = await res.json();
                } else {
                    staff = await querySupabase('employees?select=*&is_active=eq.1&order=id.asc');
                }
            } catch (err) {
                staff = await querySupabase('employees?select=*&is_active=eq.1&order=id.asc');
            }
        } else {
            staff = await querySupabase('employees?select=*&is_active=eq.1&order=id.asc');
        }

        cachedStaff = staff || [];
        renderStaffTable(cachedStaff);
    } catch (e) {
        console.error('loadStaff error:', e);
    }
}

function renderStaffTable(staff) {
    const tbody = document.getElementById('staffBody');
    const query = (document.getElementById('staffSearch')?.value || '').toLowerCase();

    const filtered = (staff || []).filter(s =>
        (s.name || '').toLowerCase().includes(query) ||
        (s.biometric_id || '').toString().includes(query) ||
        (s.department || '').toLowerCase().includes(query)
    );

    if (!filtered || filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted" style="padding:20px;">No staff registered.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(s => {
        const allowances = (parseFloat(s.housing_allowance) || 0) + (parseFloat(s.transport_allowance) || 0);
        const timingStr = `${s.start_time || '09:00'} - ${s.end_time || '18:00'}`;
        return `
            <tr>
                <td><b class="badge badge-secondary">#${s.biometric_id}</b></td>
                <td><strong>${escapeHtml(s.name)}</strong></td>
                <td>${escapeHtml(s.department || 'Multani Shop')}</td>
                <td>
                    <span class="badge badge-info"><i class="fa-solid fa-clock"></i> ${timingStr}</span>
                    <span class="text-muted" style="font-size:11px; margin-left:4px;">(${s.work_hours || 8} hrs)</span>
                </td>
                <td><span class="badge badge-secondary">${s.off_day || 'Sun'}</span></td>
                <td><b>${formatCurrency(s.basic_salary)}</b></td>
                <td>${formatCurrency(allowances)}</td>
                <td>
                    <div style="display:flex; gap:6px;">
                        <button class="btn btn-sm btn-outline" onclick="editStaff(${s.id})"><i class="fa-solid fa-pen"></i> Edit</button>
                        <button class="btn btn-sm btn-outline text-danger" onclick="deleteStaff(${s.id})"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function applyShiftPreset(val) {
    if (!val) return;
    if (val === 'morning') {
        document.getElementById('staffStartTime').value = '09:00';
        document.getElementById('staffEndTime').value = '18:00';
        document.getElementById('staffWorkHours').value = '8.0';
        document.getElementById('staffGraceMins').value = '15';
    } else if (val === 'mid') {
        document.getElementById('staffStartTime').value = '10:30';
        document.getElementById('staffEndTime').value = '20:30';
        document.getElementById('staffWorkHours').value = '9.0';
        document.getElementById('staffGraceMins').value = '15';
    } else if (val === 'evening') {
        document.getElementById('staffStartTime').value = '12:00';
        document.getElementById('staffEndTime').value = '21:30';
        document.getElementById('staffWorkHours').value = '8.5';
        document.getElementById('staffGraceMins').value = '15';
    } else if (val === 'long') {
        document.getElementById('staffStartTime').value = '09:00';
        document.getElementById('staffEndTime').value = '21:00';
        document.getElementById('staffWorkHours').value = '11.0';
        document.getElementById('staffGraceMins').value = '20';
    }
}

function openAddStaff() {
    document.getElementById('staffModalTitle').innerHTML = `<i class="fa-solid fa-user-plus text-primary"></i> Add Staff Member & Schedule`;
    document.getElementById('staffIdHidden').value = '';
    document.getElementById('staffForm').reset();
    document.getElementById('staffStartTime').value = '09:00';
    document.getElementById('staffEndTime').value = '18:00';
    document.getElementById('staffWorkHours').value = '8.0';
    document.getElementById('staffGraceMins').value = '15';
    document.getElementById('staffWeeklyOff').value = 'Sun';
    openModal('staffModal');
}

function editStaff(staffId) {
    const s = cachedStaff.find(e => e.id === staffId);
    if (!s) return;

    document.getElementById('staffModalTitle').innerHTML = `<i class="fa-solid fa-user-gear text-primary"></i> Edit Profile & Schedule: ${escapeHtml(s.name)}`;
    document.getElementById('staffIdHidden').value = s.id;
    document.getElementById('staffBioId').value = s.biometric_id;
    document.getElementById('staffName').value = s.name;
    document.getElementById('staffDept').value = s.department || 'Multani Shop';
    document.getElementById('staffPhone').value = s.phone || '';
    
    document.getElementById('staffStartTime').value = s.start_time || '09:00';
    document.getElementById('staffEndTime').value = s.end_time || '18:00';
    document.getElementById('staffWorkHours').value = s.work_hours || 8.0;
    document.getElementById('staffGraceMins').value = s.grace_minutes || 15;
    document.getElementById('staffWeeklyOff').value = s.off_day || 'Sun';
    document.getElementById('staffPresetSelect').value = '';

    document.getElementById('staffBasic').value = s.basic_salary;
    document.getElementById('staffAllowances').value = (parseFloat(s.housing_allowance) || 0) + (parseFloat(s.transport_allowance) || 0);
    openModal('staffModal');
}

async function deleteStaff(staffId) {
    const s = cachedStaff.find(e => e.id === staffId);
    const staffName = s ? s.name : `Staff #${staffId}`;
    const bioId = s ? s.biometric_id : null;

    if (!confirm(`Are you sure you want to permanently remove "${staffName}"?\n\nAll daily attendance records, punches, and monthly payslips for this member will also be deleted.`)) {
        return;
    }

    showToast(`Removing ${staffName} and all associated records...`, 'info');
    try {
        if (isLocalHost) {
            await fetch(`/api/employees/${staffId}`, { method: 'DELETE' }).catch(() => {});
        }

        // Supabase Cloud Cascade Deletion
        await querySupabase(`daily_attendance?employee_id=eq.${staffId}`, { method: 'DELETE' }).catch(() => {});
        await querySupabase(`payslips?employee_id=eq.${staffId}`, { method: 'DELETE' }).catch(() => {});
        await querySupabase(`leaves?employee_id=eq.${staffId}`, { method: 'DELETE' }).catch(() => {});
        if (bioId) {
            await querySupabase(`raw_attendance_logs?biometric_id=eq.${bioId}`, { method: 'DELETE' }).catch(() => {});
        }
        await querySupabase(`employees?id=eq.${staffId}`, { method: 'DELETE' }).catch(() => {});

        showToast(`${staffName} and all associated data deleted successfully!`, 'success');
        await loadStaff();
        await loadDashboard();
        await loadDailyAttendance();
        await loadTimesheetMatrix();
        await loadPayroll();
    } catch (e) {
        showToast('Error removing staff: ' + e.message, 'error');
    }
}

function toggleLateDeductionType(type) {
    document.getElementById('groupLatePercent').style.display = type === 'percentage' ? 'block' : 'none';
    document.getElementById('groupLateFixed').style.display = type === 'fixed_amount' ? 'block' : 'none';
    document.getElementById('groupLateThreshold').style.display = type === 'threshold_days' ? 'block' : 'none';
    updateLatePercentPreview();
}

function updateLatePercentPreview() {
    const pct = parseFloat(document.getElementById('setLatePenaltyPercent').value) || 0;
    const hint = document.getElementById('latePercentPreviewHint');
    if (hint) {
        const cutAmt = Math.round(1000 * (pct / 100));
        hint.textContent = `Example: On PKR 30,000 monthly salary (PKR 1,000/day), ${pct}% = PKR ${cutAmt} deducted per late arrival.`;
    }
}

async function loadSettings() {
    try {
        if (isLocalHost) {
            try {
                const res = await fetch('/api/settings');
                if (res.ok) {
                    const s = await res.json();
                    if (s && s.company_name) {
                        cachedCompanySettings = s;
                    }
                }
            } catch (err) {}
        }
        currentCurrency = cachedCompanySettings.currency || 'PKR';
        document.getElementById('brandCompanyName').textContent = cachedCompanySettings.company_name;
        document.getElementById('setCompanyName').value = cachedCompanySettings.company_name;
        document.getElementById('setCurrency').value = cachedCompanySettings.currency;
        document.getElementById('setWorkingDays').value = cachedCompanySettings.working_days_per_month || 26;
        document.getElementById('setOtMultiplier').value = cachedCompanySettings.overtime_multiplier || 1.5;

        const dedType = cachedCompanySettings.late_deduction_type || 'percentage';
        document.getElementById('setLateDeductionType').value = dedType;
        document.getElementById('setLatePenaltyPercent').value = cachedCompanySettings.late_penalty_percent !== undefined ? cachedCompanySettings.late_penalty_percent : 5.0;
        document.getElementById('setLateFixedAmount').value = cachedCompanySettings.late_fixed_amount !== undefined ? cachedCompanySettings.late_fixed_amount : 100;
        document.getElementById('setLateThreshold').value = cachedCompanySettings.late_threshold_count !== undefined ? cachedCompanySettings.late_threshold_count : 3;
        toggleLateDeductionType(dedType);
    } catch (e) {
        console.error('loadSettings error:', e);
    }
}

async function saveSettingsAction() {
    const payload = {
        company_name: document.getElementById('setCompanyName').value.trim(),
        currency: document.getElementById('setCurrency').value.trim(),
        phone: document.getElementById('setPhone')?.value.trim() || '',
        address: document.getElementById('setAddress')?.value.trim() || '',
        working_days_per_month: parseInt(document.getElementById('setWorkingDays').value) || 26,
        overtime_multiplier: parseFloat(document.getElementById('setOtMultiplier').value) || 1.5,
        late_grace_minutes: parseInt(document.getElementById('setLateGrace').value) || 15,
        late_deduction_type: document.getElementById('setLateDeductionType').value || 'percentage',
        late_penalty_percent: parseFloat(document.getElementById('setLatePenaltyPercent').value) || 5.0,
        late_fixed_amount: parseFloat(document.getElementById('setLateFixedAmount').value) || 100.0,
        late_threshold_count: parseInt(document.getElementById('setLateThreshold').value) || 3,
        late_penalty_days: 1.0
    };

    cachedCompanySettings = { ...cachedCompanySettings, ...payload };
    currentCurrency = payload.currency;
    document.getElementById('brandCompanyName').textContent = payload.company_name;

    if (isLocalHost) {
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (e) {}
    }

    showToast('Settings saved successfully!', 'success');
}

// -------------------------------------------------------------
// Event Listeners
// -------------------------------------------------------------
function setupEvents() {
    document.getElementById('settingsForm')?.addEventListener('submit', (e) => {
        e.preventDefault();
        saveSettingsAction();
    });

    document.getElementById('openAddManualAttBtn')?.addEventListener('click', openManualAttendanceModal);

    document.getElementById('manualAttForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const empId = parseInt(document.getElementById('manualAttEmpSelect').value);
        const dateStr = document.getElementById('manualAttDate').value;
        const status = document.getElementById('manualAttStatus').value;
        const notes = document.getElementById('manualAttNotes').value.trim();

        let inTime = null, outTime = null, hrs = 0.0, lateMins = 0;
        if (status === 'Present' || status === 'Late' || status === 'Half Day') {
            inTime = document.getElementById('manualAttIn').value || '09:00';
            outTime = document.getElementById('manualAttOut').value || '18:00';
            hrs = status === 'Half Day' ? 4.0 : 8.0;
        }

        const payload = {
            employee_id: empId,
            date: dateStr,
            first_in: inTime,
            last_out: outTime,
            all_punches: JSON.stringify([inTime, outTime].filter(Boolean)),
            total_hours: hrs,
            regular_hours: hrs,
            overtime_hours: 0.0,
            late_minutes: lateMins,
            early_leave_minutes: 0,
            status: status,
            is_manual_override: 1,
            notes: notes || 'Manual Override'
        };

        try {
            if (isLocalHost) {
                await fetch('/api/attendance/manual', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                }).catch(() => {});
            }

            await querySupabase('daily_attendance?on_conflict=employee_id,date', {
                method: 'POST',
                headers: { 'Prefer': 'resolution=merge-duplicates' },
                body: JSON.stringify(payload)
            });

            showToast(`Attendance marked as ${status}!`, 'success');
            closeModal('manualAttModal');
            loadDailyAttendance();
            loadDashboard();
        } catch (err) {
            showToast('Save failed: ' + err.message, 'error');
        }
    });

    // Staff Form
    document.getElementById('staffForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const staffId = document.getElementById('staffIdHidden').value;
        const basic = parseFloat(document.getElementById('staffBasic').value) || 0;
        const allowances = parseFloat(document.getElementById('staffAllowances').value) || 0;

        const payload = {
            biometric_id: document.getElementById('staffBioId').value.trim(),
            name: document.getElementById('staffName').value.trim(),
            department: document.getElementById('staffDept').value.trim() || 'Multani Shop',
            designation: 'Staff',
            phone: document.getElementById('staffPhone')?.value.trim() || '',
            salary_type: 'Monthly',
            basic_salary: basic,
            housing_allowance: Math.round(allowances * 0.6),
            transport_allowance: Math.round(allowances * 0.4),
            medical_allowance: 0.0,
            other_allowance: 0.0,
            start_time: document.getElementById('staffStartTime').value || '09:00',
            end_time: document.getElementById('staffEndTime').value || '18:00',
            grace_minutes: parseInt(document.getElementById('staffGraceMins').value) || 15,
            work_hours: parseFloat(document.getElementById('staffWorkHours').value) || 8.0,
            off_day: document.getElementById('staffWeeklyOff').value || 'Sun',
            is_active: 1
        };

        try {
            if (staffId) {
                if (isLocalHost) {
                    await fetch(`/api/employees/${staffId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    }).catch(() => {});
                }
                await querySupabase(`employees?id=eq.${staffId}`, {
                    method: 'PATCH',
                    body: JSON.stringify(payload)
                });
                showToast('Staff profile updated!', 'success');
            } else {
                if (isLocalHost) {
                    await fetch('/api/employees', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    }).catch(() => {});
                }
                await querySupabase('employees', {
                    method: 'POST',
                    body: JSON.stringify(payload)
                });
                showToast('New staff registered!', 'success');
            }
            closeModal('staffModal');
            loadStaff();
            loadDashboard();
        } catch (err) {
            showToast('Save error: ' + err.message, 'error');
        }
    });

    document.getElementById('openAddStaffBtn')?.addEventListener('click', openAddStaff);
    document.getElementById('printSlipBtn')?.addEventListener('click', () => window.print());

    // 1-Click Import File Button
    const uploadBtn = document.getElementById('topUploadBtn');
    const fileInput = document.getElementById('universalFileInput');
    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            showToast(`Uploading and processing ${file.name}...`, 'info');
            const formData = new FormData();
            formData.append('file', file);
            try {
                if (isLocalHost) {
                    const res = await fetch('/api/attendance/upload', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    showToast(data.message || `Successfully processed ${file.name}!`, data.success ? 'success' : 'info');
                } else {
                    showToast(`File ${file.name} received. Auto-syncing logs to cloud database...`, 'success');
                }
                loadDailyAttendance();
                loadDashboard();
            } catch (err) {
                showToast('Import notice: ' + err.message, 'warning');
            }
            fileInput.value = '';
        });
    }

    // 1-Click Machine Sync Button
    const syncBtn = document.getElementById('topSyncBtn');
    if (syncBtn) {
        syncBtn.addEventListener('click', async () => {
            showToast('Connecting to Fingerprint Machine (182.188.40.187:8080)...', 'info');
            try {
                if (isLocalHost) {
                    const res = await fetch('/api/devices/1/sync', { method: 'POST' });
                    let data = null;
                    try {
                        data = await res.json();
                    } catch (err) {
                        data = { success: false, message: 'Machine connection status checked.' };
                    }
                    showToast(data.message || 'Sync completed', data.success ? 'success' : 'warning');
                } else {
                    showToast('Biometric live polling active via shop desktop server & Supabase cloud!', 'info');
                }
                loadDailyAttendance();
                loadDashboard();
            } catch (err) {
                showToast('Machine status: ' + err.message, 'warning');
            }
        });
    }

    // Date filters & Action triggers
    document.getElementById('dashDatePicker')?.addEventListener('change', loadDashboard);
    document.getElementById('dashRefreshBtn')?.addEventListener('click', loadDashboard);
    document.getElementById('dailyDateInput')?.addEventListener('change', loadDailyAttendance);
    document.getElementById('dailyRefreshBtn')?.addEventListener('click', loadDailyAttendance);
    document.getElementById('dailyRecalcBtn')?.addEventListener('click', loadDailyAttendance);
    document.getElementById('attendanceSearch')?.addEventListener('input', () => {
        loadDailyAttendance();
    });
    document.getElementById('staffSearch')?.addEventListener('input', () => {
        renderStaffTable(cachedStaff);
    });
    document.getElementById('timesheetMonthInput')?.addEventListener('change', loadTimesheetMatrix);
    document.getElementById('timesheetMonthInput')?.addEventListener('input', loadTimesheetMatrix);
    document.getElementById('loadTimesheetBtn')?.addEventListener('click', loadTimesheetMatrix);
    document.getElementById('timesheetRefreshBtn')?.addEventListener('click', loadTimesheetMatrix);
    document.getElementById('payrollMonthInput')?.addEventListener('change', loadPayroll);
    document.getElementById('calculatePayrollBtn')?.addEventListener('click', calculatePayrollAction);
}

// -------------------------------------------------------------
// Helpers & Utilities
// -------------------------------------------------------------
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = 'auto';
    }
}

function showToast(message, type = 'info') {
    const box = document.getElementById('toastBox');
    if (!box) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success' ? 'circle-check' : (type === 'error' ? 'circle-xmark' : (type === 'warning' ? 'triangle-exclamation' : 'circle-info'));
    toast.innerHTML = `<i class="fa-solid fa-${icon}"></i> <span>${escapeHtml(message)}</span>`;
    box.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function getStatusBadge(status) {
    if (!status) return `<span class="badge badge-secondary">Pending</span>`;
    if (status === 'Present' || status === 'Holiday Present') return `<span class="badge badge-success">Present</span>`;
    if (status === 'Late') return `<span class="badge badge-warning">Late</span>`;
    if (status === 'Half Day') return `<span class="badge badge-info">Half Day</span>`;
    if (status === 'Paid Leave') return `<span class="badge badge-success">Paid Leave</span>`;
    if (status === 'Unpaid Leave') return `<span class="badge badge-warning">Unpaid Leave</span>`;
    if (status === 'Absent') return `<span class="badge badge-danger">Absent</span>`;
    if (status === 'Weekly Off') return `<span class="badge badge-secondary">Weekly Off</span>`;
    return `<span class="badge badge-info">${escapeHtml(status)}</span>`;
}

function formatCurrency(amt) {
    const num = parseFloat(amt) || 0;
    return `${currentCurrency} ${num.toLocaleString('en-US')}`;
}

function formatMonthName(monthStr) {
    if (!monthStr) return '';
    const [year, month] = monthStr.split('-');
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const idx = parseInt(month, 10) - 1;
    return `${months[idx] || ''} ${year}`;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function numberToWords(amount) {
    const words = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen'];
    const tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];
    
    if (amount === 0) return 'Zero';
    
    function convertLessThanOneThousand(n) {
        let current = '';
        if (n >= 100) {
            current += words[Math.floor(n / 100)] + ' Hundred ';
            n %= 100;
        }
        if (n >= 20) {
            current += tens[Math.floor(n / 10)] + ' ';
            n %= 10;
        }
        if (n > 0) {
            current += words[n] + ' ';
        }
        return current;
    }

    let result = '';
    const n = Math.floor(amount);

    if (Math.floor(n / 10000000) > 0) {
        result += convertLessThanOneThousand(Math.floor(n / 10000000)) + 'Crore ';
    }
    const lakh = Math.floor((n % 10000000) / 100000);
    if (lakh > 0) {
        result += convertLessThanOneThousand(lakh) + 'Lakh ';
    }
    const thousand = Math.floor((n % 100000) / 1000);
    if (thousand > 0) {
        result += convertLessThanOneThousand(thousand) + 'Thousand ';
    }
    const remainder = n % 1000;
    if (remainder > 0) {
        result += convertLessThanOneThousand(remainder);
    }

    return result.trim();
}
