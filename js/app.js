/**
 * MULTANI TRADERS - ATTENDANCE & PAYROLL APPLICATION
 * Clean, Simple, & User-Friendly Client Logic (Supports Local Server & Direct Supabase Cloud on Netlify)
 */

const SUPABASE_URL = 'https://tyxvrykwarevfdwrbrmv.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_rEHPrqKtGzTdIO6gVPXxOw_jE2Yy4VH';
let supaClient = null;

if (window.supabase) {
    try {
        supaClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    } catch (e) {
        console.error('Supabase init error:', e);
    }
}

const isLocalHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

let currentTab = 'dashboard';
let currentCurrency = 'PKR';
let cachedStaff = [];

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

// -------------------------------------------------------------
// Navigation & Tabs
// -------------------------------------------------------------
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
    const today = new Date().toISOString().split('T')[0];
    const defaultMonth = '2026-08'; // Default to August where real records are imported

    document.getElementById('dashDatePicker').value = today;
    document.getElementById('dailyDateInput').value = '2026-08-18';
    document.getElementById('timesheetMonthInput').value = defaultMonth;
    document.getElementById('payrollMonthInput').value = defaultMonth;
}

// -------------------------------------------------------------
// 1. Dashboard Module
// -------------------------------------------------------------
async function loadDashboard() {
    const dateVal = document.getElementById('dashDatePicker').value;
    try {
        const res = await fetch(`/api/dashboard/stats?target_date=${dateVal}`);
        const data = await res.json();

        document.getElementById('dashTotalStaff').textContent = data.total_employees;
        document.getElementById('dashPresentToday').textContent = data.status_counts.present;
        document.getElementById('dashLateToday').textContent = data.status_counts.late;

        // Payroll teaser
        const payRes = await fetch('/api/payroll/runs');
        const runs = await payRes.json();
        if (runs && runs.length > 0) {
            document.getElementById('dashNetPayroll').textContent = formatCurrency(runs[0].total_net_salary);
            document.getElementById('dashPayrollMonthLbl').textContent = `Month: ${runs[0].month}`;
        }

        // Daily table
        const dailyRes = await fetch(`/api/attendance/daily?date=${dateVal}`);
        const dailyData = await dailyRes.json();
        renderDashboardTable(dailyData.records || []);
    } catch (e) {
        console.error(e);
    }
}

function renderDashboardTable(records) {
    const tbody = document.getElementById('dashAttendanceBody');
    if (!records || records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted" style="padding:20px;">No attendance logs found for this date.</td></tr>`;
        return;
    }

    tbody.innerHTML = records.map(r => `
        <tr>
            <td><b class="badge badge-secondary">#${r.biometric_id}</b></td>
            <td><strong>${escapeHtml(r.employee_name)}</strong></td>
            <td>${escapeHtml(r.department || 'Multani Shop')}</td>
            <td>${r.first_in ? `<b class="text-success">${r.first_in}</b>` : '<span class="text-muted">--:--</span>'}</td>
            <td>${r.last_out ? `<b class="text-info">${r.last_out}</b>` : '<span class="text-muted">--:--</span>'}</td>
            <td><b>${r.total_hours} hrs</b></td>
            <td>${r.late_minutes > 0 ? `<span class="badge badge-warning">${r.late_minutes}m Late</span>` : '<span class="text-muted">On time</span>'}</td>
            <td>${getStatusBadge(r.status)}</td>
        </tr>
    `).join('');
}

// -------------------------------------------------------------
// 2. Daily Attendance Module
// -------------------------------------------------------------
async function loadDailyAttendance() {
    const d = document.getElementById('dailyDateInput').value;
    try {
        const res = await fetch(`/api/attendance/daily?date=${d}`);
        const data = await res.json();
        renderDailyTable(data.records || []);
    } catch (e) {
        console.error(e);
    }
}

function renderDailyTable(records) {
    const tbody = document.getElementById('dailyBody');
    const query = (document.getElementById('attendanceSearch')?.value || '').toLowerCase();

    const filtered = records.filter(r => 
        (r.employee_name || '').toLowerCase().includes(query) ||
        (r.biometric_id || '').includes(query) ||
        (r.department || '').toLowerCase().includes(query)
    );

    if (!filtered || filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted" style="padding:20px;">No records for this date.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(r => `
        <tr>
            <td><b class="badge badge-secondary">#${r.biometric_id}</b></td>
            <td><strong>${escapeHtml(r.employee_name)}</strong></td>
            <td>${escapeHtml(r.department || 'Multani Shop')}</td>
            <td>${r.first_in ? `<b class="text-success">${r.first_in}</b>` : '<span class="text-muted">--:--</span>'}</td>
            <td>${r.last_out ? `<b class="text-info">${r.last_out}</b>` : '<span class="text-muted">--:--</span>'}</td>
            <td><b>${r.total_hours} hrs</b></td>
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
    try {
        const res = await fetch('/api/employees');
        const emps = await res.json();
        sel.innerHTML = emps.map(e => `
            <option value="${e.id}">[ID ${e.biometric_id}] ${escapeHtml(e.name)} - ${escapeHtml(e.department || 'Multani Shop')}</option>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

async function openManualAttendanceModal() {
    await populateManualAttendanceEmployees();
    const curDate = document.getElementById('dailyDateInput')?.value || new Date().toISOString().split('T')[0];
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
    if (val === 'Absent' || val === 'Weekly Off' || val === 'Unpaid Leave') {
        timeRow.style.display = 'none';
    } else {
        timeRow.style.display = 'grid';
    }
}

// -------------------------------------------------------------
// 3. Monthly Timesheet Matrix
// -------------------------------------------------------------
async function loadTimesheetMatrix() {
    const month = document.getElementById('timesheetMonthInput').value;
    try {
        const res = await fetch(`/api/attendance/monthly?month=${month}`);
        const data = await res.json();
        renderMatrix(month, data.matrix || []);
    } catch (e) {
        console.error(e);
    }
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
                const st = dayData.status;
                let badge = '-';
                if (st.includes('Present')) badge = `<span class="badge badge-success">P</span>`;
                else if (st === 'Late') badge = `<span class="badge badge-warning">L</span>`;
                else if (st === 'Half Day') badge = `<span class="badge badge-info">HD</span>`;
                else if (st === 'Absent') badge = `<span class="badge badge-danger">A</span>`;
                else if (st === 'Weekly Off') badge = `<span class="badge badge-secondary">OFF</span>`;
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
    const month = document.getElementById('payrollMonthInput').value;
    try {
        const res = await fetch(`/api/payroll/payslips?month=${month}`);
        const payslips = await res.json();
        renderPayrollTable(month, payslips);
    } catch (e) {
        console.error(e);
    }
}

async function calculatePayrollAction() {
    const month = document.getElementById('payrollMonthInput').value;
    showToast(`Calculating payroll for ${month}...`, 'info');
    try {
        const res = await fetch(`/api/payroll/generate?month=${month}`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`Payroll generated for ${data.total_employees} staff members!`, 'success');
            loadPayroll();
            loadDashboard();
        }
    } catch (e) {
        showToast('Calculation error: ' + e.message, 'error');
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
        sumGross += p.gross_salary;
        sumDeductions += p.total_deductions;
        sumNet += p.net_salary;

        const allowances = (p.housing_allowance || 0) + (p.transport_allowance || 0);

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
        const res = await fetch(`/api/payroll/payslip/${payslipId}`);
        const p = await res.json();
        if (!p) return;

        const comp = p.company || {};
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
        document.getElementById('slipBonus').textContent = formatCurrency(p.bonus);
        document.getElementById('slipGross').textContent = formatCurrency(p.gross_salary);

        // Deductions
        document.getElementById('slipDedAbs').textContent = formatCurrency(p.absent_deduction);
        document.getElementById('slipDedLate').textContent = formatCurrency(p.late_deduction);
        document.getElementById('slipDedOther').textContent = formatCurrency(p.tax_deduction + (p.other_deduction || 0));
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
        const res = await fetch('/api/employees');
        const staff = await res.json();
        cachedStaff = staff;

        const tbody = document.getElementById('staffBody');
        const query = (document.getElementById('staffSearch')?.value || '').toLowerCase();

        const filtered = staff.filter(s =>
            (s.name || '').toLowerCase().includes(query) ||
            (s.biometric_id || '').includes(query) ||
            (s.department || '').toLowerCase().includes(query)
        );

        if (!filtered || filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:20px;">No staff registered.</td></tr>`;
            return;
        }

        tbody.innerHTML = filtered.map(s => {
            const allowances = (s.housing_allowance || 0) + (s.transport_allowance || 0);
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
    } catch (e) {
        console.error(e);
    }
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
    document.getElementById('staffAllowances').value = (s.housing_allowance || 0) + (s.transport_allowance || 0);
    openModal('staffModal');
}

async function deleteStaff(staffId) {
    if (!confirm('Remove this staff member?')) return;
    try {
        await fetch(`/api/employees/${staffId}`, { method: 'DELETE' });
        showToast('Staff removed', 'success');
        loadStaff();
    } catch (e) {
        showToast('Error removing staff', 'error');
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
        const res = await fetch('/api/settings');
        const s = await res.json();
        if (s && s.company_name) {
            currentCurrency = s.currency || 'PKR';
            document.getElementById('brandCompanyName').textContent = s.company_name;
            document.getElementById('setCompanyName').value = s.company_name;
            document.getElementById('setCurrency').value = s.currency;
            document.getElementById('setPhone').value = s.phone || '';
            document.getElementById('setAddress').value = s.address || '';
            document.getElementById('setWorkingDays').value = s.working_days_per_month || 26;
            document.getElementById('setOtMultiplier').value = s.overtime_multiplier || 1.5;
            document.getElementById('setLateGrace').value = s.late_grace_minutes || 15;
            
            const dedType = s.late_deduction_type || 'percentage';
            document.getElementById('setLateDeductionType').value = dedType;
            document.getElementById('setLatePenaltyPercent').value = s.late_penalty_percent !== undefined ? s.late_penalty_percent : 5.0;
            document.getElementById('setLateFixedAmount').value = s.late_fixed_amount !== undefined ? s.late_fixed_amount : 100;
            document.getElementById('setLateThreshold').value = s.late_threshold_count !== undefined ? s.late_threshold_count : 3;

            toggleLateDeductionType(dedType);
        }

        // Load Shift details
        const shiftRes = await fetch('/api/shifts');
        const shifts = await shiftRes.json();
        if (shifts && shifts.length > 0) {
            const sh = shifts[0];
            document.getElementById('setShiftStart').value = sh.start_time || '09:00';
            document.getElementById('setShiftEnd').value = sh.end_time || '18:00';
            document.getElementById('setShiftHours').value = sh.full_day_hours || 8.0;
            document.getElementById('setLateGrace').value = sh.grace_minutes || 15;
        }

        const devRes = await fetch('/api/devices');
        const devs = await devRes.json();
        if (devs && devs.length > 0) {
            document.getElementById('setDevIp').value = devs[0].ip_address;
            document.getElementById('setDevPort').value = devs[0].port;
            document.getElementById('setDevUser').value = devs[0].username || 'admin';
            document.getElementById('setDevPass').value = devs[0].password || '';
        }
    } catch (e) {
        console.error(e);
    }
}

async function saveSettingsAction() {
    const payload = {
        company_name: document.getElementById('setCompanyName').value.trim(),
        currency: document.getElementById('setCurrency').value.trim(),
        phone: document.getElementById('setPhone').value.trim(),
        address: document.getElementById('setAddress').value.trim(),
        working_days_per_month: parseInt(document.getElementById('setWorkingDays').value) || 26,
        overtime_multiplier: parseFloat(document.getElementById('setOtMultiplier').value) || 1.5,
        late_grace_minutes: parseInt(document.getElementById('setLateGrace').value) || 15,
        late_deduction_type: document.getElementById('setLateDeductionType').value || 'percentage',
        late_penalty_percent: parseFloat(document.getElementById('setLatePenaltyPercent').value) || 5.0,
        late_fixed_amount: parseFloat(document.getElementById('setLateFixedAmount').value) || 100.0,
        late_threshold_count: parseInt(document.getElementById('setLateThreshold').value) || 3,
        late_penalty_days: 1.0
    };

    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        // Save Shift Timings
        const shiftPayload = {
            name: 'Standard Shift',
            start_time: document.getElementById('setShiftStart').value || '09:00',
            end_time: document.getElementById('setShiftEnd').value || '18:00',
            full_day_hours: parseFloat(document.getElementById('setShiftHours').value) || 8.0,
            grace_minutes: parseInt(document.getElementById('setLateGrace').value) || 15
        };

        await fetch('/api/shifts/1', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(shiftPayload)
        });

        // Update Device
        const devPayload = {
            name: 'Main Fingerprint Machine',
            ip_address: document.getElementById('setDevIp').value.trim(),
            port: parseInt(document.getElementById('setDevPort').value) || 8080,
            username: document.getElementById('setDevUser').value.trim(),
            password: document.getElementById('setDevPass').value.trim(),
            protocol: 'auto'
        };

        await fetch('/api/devices/1', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(devPayload)
        });

        showToast('Settings, Shift timings & Supabase saved successfully!', 'success');
        loadSettings();
    } catch (e) {
        showToast('Error saving: ' + e.message, 'error');
    }
}

// -------------------------------------------------------------
// Events & File Upload
// -------------------------------------------------------------
function setupEvents() {
    // Top Action Buttons
    const fileInput = document.getElementById('universalFileInput');
    document.getElementById('topUploadBtn')?.addEventListener('click', () => fileInput.click());
    
    fileInput?.addEventListener('change', async (e) => {
        if (!e.target.files.length) return;
        const file = e.target.files[0];
        const formData = new FormData();
        formData.append('file', file);
        showToast('Importing attendance file...', 'info');

        try {
            const res = await fetch('/api/import-csv', { method: 'POST', body: formData });
            const data = await res.json();
            showToast(`Imported ${data.imported || 0} attendance records!`, 'success');
            loadDailyAttendance();
            loadDashboard();
        } catch (err) {
            showToast('Import failed: ' + err.message, 'error');
        }
        fileInput.value = '';
    });

    document.getElementById('topSyncBtn')?.addEventListener('click', async () => {
        showToast('Connecting to Fingerprint Machine...', 'info');
        try {
            const res = await fetch('/api/devices/1/sync', { method: 'POST' });
            let data = null;
            try {
                data = await res.json();
            } catch (jsonErr) {
                const txt = await res.text().catch(() => '');
                data = { success: false, message: txt || 'Device is currently unreachable or offline.' };
            }
            showToast(data.message || 'Sync completed', data.success ? 'success' : 'warning');
            loadDailyAttendance();
            loadDashboard();
        } catch (e) {
            showToast('Machine connection notice: ' + e.message, 'warning');
        }
    });

    // Date filters
    document.getElementById('dashDatePicker')?.addEventListener('change', loadDashboard);
    document.getElementById('dashRefreshBtn')?.addEventListener('click', loadDashboard);
    document.getElementById('dailyDateInput')?.addEventListener('change', loadDailyAttendance);
    document.getElementById('attendanceSearch')?.addEventListener('input', loadDailyAttendance);
    document.getElementById('staffSearch')?.addEventListener('input', loadStaff);
    document.getElementById('loadTimesheetBtn')?.addEventListener('click', loadTimesheetMatrix);
    document.getElementById('timesheetMonthInput')?.addEventListener('change', loadTimesheetMatrix);
    document.getElementById('payrollMonthInput')?.addEventListener('change', loadPayroll);
    document.getElementById('calculatePayrollBtn')?.addEventListener('click', calculatePayrollAction);
    document.getElementById('saveAllSettingsBtn')?.addEventListener('click', saveSettingsAction);
    document.getElementById('openAddStaffBtn')?.addEventListener('click', openAddStaff);
    document.getElementById('printSlipBtn')?.addEventListener('click', () => window.print());

    // Test Machine
    document.getElementById('testMachineBtn')?.addEventListener('click', async () => {
        showToast('Testing machine connection...', 'info');
        try {
            const res = await fetch('/api/devices/1/test', { method: 'POST' });
            const data = await res.json();
            showToast(data.message, data.success ? 'success' : 'error');
        } catch (e) {
            showToast('Test failed: ' + e.message, 'error');
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
            basic_salary: basic,
            housing_allowance: Math.round(allowances * 0.6),
            transport_allowance: Math.round(allowances * 0.4),
            salary_type: 'Monthly',
            shift_id: 1,
            start_time: document.getElementById('staffStartTime').value || '09:00',
            end_time: document.getElementById('staffEndTime').value || '18:00',
            work_hours: parseFloat(document.getElementById('staffWorkHours').value) || 8.0,
            grace_minutes: parseInt(document.getElementById('staffGraceMins').value) || 15,
            off_day: document.getElementById('staffWeeklyOff').value || 'Sun'
        };

        try {
            const url = staffId ? `/api/employees/${staffId}` : '/api/employees';
            const method = staffId ? 'PUT' : 'POST';
            await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            showToast(staffId ? 'Staff updated!' : 'Staff member added!', 'success');
            closeModal('staffModal');
            loadStaff();
        } catch (err) {
            showToast('Error: ' + err.message, 'error');
        }
    });

    // Manual Attendance Modal Open
    document.getElementById('openManualAttBtn')?.addEventListener('click', openManualAttendanceModal);

    // Manual Attendance Form Submit
    document.getElementById('manualAttForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const empId = parseInt(document.getElementById('manualAttEmpSelect').value);
        const dateVal = document.getElementById('manualAttDate').value;
        const statusVal = document.getElementById('manualAttStatus').value;
        const inVal = document.getElementById('manualAttIn').value;
        const outVal = document.getElementById('manualAttOut').value;
        const notesVal = document.getElementById('manualAttNotes').value.trim();

        const payload = {
            employee_id: empId,
            date: dateVal,
            status: statusVal,
            first_in: (statusVal === 'Absent' || statusVal === 'Weekly Off') ? null : inVal,
            last_out: (statusVal === 'Absent' || statusVal === 'Weekly Off') ? null : outVal,
            notes: notesVal
        };

        try {
            const res = await fetch('/api/attendance/manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            showToast(data.message || 'Attendance updated successfully!', 'success');
            closeModal('manualAttModal');
            loadDailyAttendance();
            loadDashboard();
            if (document.getElementById('timesheetMonthInput')?.value) {
                loadTimesheetMatrix();
            }
        } catch (err) {
            showToast('Error saving attendance: ' + err.message, 'error');
        }
    });
}

// -------------------------------------------------------------
// Helpers & Formatting
// -------------------------------------------------------------
function openModal(id) {
    document.getElementById(id)?.classList.add('active');
}

function closeModal(id) {
    document.getElementById(id)?.classList.remove('active');
}

function showToast(msg, type = 'info') {
    const box = document.getElementById('toastBox');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    box.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function getStatusBadge(st) {
    if (!st) return '<span class="badge badge-secondary">--</span>';
    if (st.includes('Present')) return '<span class="badge badge-success">Present</span>';
    if (st.includes('Late')) return '<span class="badge badge-warning">Late</span>';
    if (st === 'Half Day') return '<span class="badge badge-info">Half Day</span>';
    if (st === 'Absent') return '<span class="badge badge-danger">Absent</span>';
    if (st === 'Weekly Off') return '<span class="badge badge-secondary">Off</span>';
    return `<span class="badge badge-secondary">${escapeHtml(st)}</span>`;
}

function formatCurrency(val) {
    const num = Number(val) || 0;
    return `${currentCurrency} ${num.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatMonthName(monthStr) {
    if (!monthStr) return '';
    try {
        const [y, m] = monthStr.split('-');
        const date = new Date(y, parseInt(m) - 1, 1);
        return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }).toUpperCase();
    } catch (e) {
        return monthStr;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function numberToWords(num) {
    const a = ['', 'One ', 'Two ', 'Three ', 'Four ', 'Five ', 'Six ', 'Seven ', 'Eight ', 'Nine ', 'Ten ', 'Eleven ', 'Twelve ', 'Thirteen ', 'Fourteen ', 'Fifteen ', 'Sixteen ', 'Seventeen ', 'Eighteen ', 'Nineteen '];
    const b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];
    num = Math.floor(num);
    if (num === 0) return 'Zero';
    if (num < 0) return 'Negative ' + numberToWords(-num);

    function inWords(n) {
        let str = '';
        if (n >= 100000) { str += inWords(Math.floor(n / 100000)) + 'Lakh '; n %= 100000; }
        if (n >= 1000) { str += inWords(Math.floor(n / 1000)) + 'Thousand '; n %= 1000; }
        if (n >= 100) { str += inWords(Math.floor(n / 100)) + 'Hundred '; n %= 100; }
        if (n > 0) {
            if (n < 20) str += a[n];
            else str += b[Math.floor(n / 10)] + ' ' + a[n % 10];
        }
        return str;
    }
    return inWords(num).trim();
}
