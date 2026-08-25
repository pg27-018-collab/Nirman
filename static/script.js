// Frontend logic for WhatsApp Birthday Dashboard

let statusPollInterval = null;
let currentSession = localStorage.getItem("whatsapp_session") || "";
let activeTab = "today";
let birthdayRecords = [];
let filteredRecords = [];
let currentPage = 1;
let pageSize = 15;

document.addEventListener("DOMContentLoaded", () => {
  // Initial Loads
  loadSessions().then(() => {
    loadStatus();
    loadBirthdays();
    loadHistory();
  });
  loadConfig();
  
  // Setup Event Listeners
  setupUploader();
  setupConfigForm();
  setupActionButtons();
  setupTabs();
  setupTableControls();
  
  // Start general status polling (every 10 seconds)
  setInterval(loadStatus, 10000);
});

// Toast Helper
function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  
  const icon = type === "success" ? "✅" : "❌";
  toast.innerHTML = `<span>${icon}</span> <div>${message}</div>`;
  
  container.appendChild(toast);
  
  // Slide out and remove
  setTimeout(() => {
    toast.style.animation = "slideIn 0.3s reverse forwards";
    toast.addEventListener("animationend", () => {
      toast.remove();
    });
  }, 4000);
}

// Load System Status
async function loadStatus() {
  try {
    const res = await fetch(`/api/status?session=${currentSession}&t=${Date.now()}`);
    const data = await res.json();
    
    // Check if authenticated to show blocker or dashboard
    const connectionBlocker = document.getElementById("connectionBlocker");
    const dashboardApp = document.getElementById("dashboardApp");
    
    if (data.whatsapp_authenticated) {
      if (connectionBlocker) connectionBlocker.style.display = "none";
      if (dashboardApp) dashboardApp.style.display = "block";
    } else {
      if (connectionBlocker) connectionBlocker.style.display = "flex";
      if (dashboardApp) dashboardApp.style.display = "none";
    }
    
    // Header Status Badge
    const headerStatus = document.getElementById("whatsappHeaderStatus");
    if (data.whatsapp_authenticated) {
      headerStatus.className = "status-badge active";
      headerStatus.innerHTML = '<span class="badge-dot"></span> WhatsApp Connected';
    } else {
      headerStatus.className = "status-badge inactive";
      headerStatus.innerHTML = '<span class="badge-dot"></span> WhatsApp Disconnected';
    }
    
    // Stats Cards
    document.getElementById("statTotalStudents").innerText = data.total_students;
    document.getElementById("statBirthdaysToday").innerText = data.birthdays_count;
    document.getElementById("statBirthdaysTomorrow").innerText = data.birthdays_tomorrow_count;
    document.getElementById("statSentToday").innerText = data.sent_today_count;
    document.getElementById("statPending").innerText = data.pending_count;
    
    // Setup login button text based on status
    const loginBtn = document.getElementById("loginBtn");
    if (data.whatsapp_authenticated) {
      loginBtn.innerHTML = "🔄 Refresh WhatsApp Authentication";
    } else {
      loginBtn.innerHTML = "🔑 Connect / Login to WhatsApp";
    }
    
    // File status hint
    const excelHint = document.getElementById("excelStatusHint");
    if (data.excel_exists) {
      excelHint.innerText = `Spreadsheet loaded: ${data.excel_path}`;
      excelHint.style.color = "var(--text-success)";
    } else {
      excelHint.innerText = "No spreadsheet uploaded yet.";
      excelHint.style.color = "var(--text-critical)";
    }
    
    // Fetch configs to map active selected values
    const configRes = await fetch("/api/config");
    const configData = await configRes.json();
    
    // Populate column mappings selectors dynamically
    const colName = document.getElementById("col_name");
    const colPhone = document.getElementById("col_phone");
    const colBday = document.getElementById("col_birthday");
    
    if (colName && colPhone && colBday) {
      const prevName = colName.value || configData.columns?.name;
      const prevPhone = colPhone.value || configData.columns?.phone;
      const prevBday = colBday.value || configData.columns?.birthday;
      
      colName.innerHTML = "";
      colPhone.innerHTML = "";
      colBday.innerHTML = "";
      
      if (data.headers && data.headers.length > 0) {
        data.headers.forEach(h => {
          colName.add(new Option(h, h));
          colPhone.add(new Option(h, h));
          colBday.add(new Option(h, h));
        });
        
        colName.value = prevName && data.headers.includes(prevName) ? prevName : configData.columns?.name || data.headers[0];
        colPhone.value = prevPhone && data.headers.includes(prevPhone) ? prevPhone : configData.columns?.phone || data.headers[0];
        colBday.value = prevBday && data.headers.includes(prevBday) ? prevBday : configData.columns?.birthday || data.headers[0];
      }
    }
    
  } catch (err) {
    console.error("Error loading status:", err);
  }
}

// Load Birthdays Table
async function loadBirthdays() {
  try {
    const selectedMonth = document.getElementById("monthSelect") ? document.getElementById("monthSelect").value : new Date().getMonth() + 1;
    const res = await fetch(`/api/birthdays?session=${currentSession}&day=${activeTab}&month=${selectedMonth}`);
    const data = await res.json();
    
    birthdayRecords = data.birthdays || [];
    currentPage = 1;
    applyTableFilterAndRender();
    
  } catch (err) {
    console.error("Error loading birthdays:", err);
  }
}

// Load Configuration Settings
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    
    document.getElementById("excel_path").value = data.excel_path || "students.xlsx";
    document.getElementById("default_country_code").value = data.default_country_code || "+91";
    document.getElementById("message_template").value = data.message_template || "";
    document.getElementById("min_delay_seconds").value = data.min_delay_seconds || 15;
    document.getElementById("max_delay_seconds").value = data.max_delay_seconds || 30;
    
    // Automated daily sending
    const autoSending = document.getElementById("automated_sending");
    const schedTime = document.getElementById("scheduled_time");
    const schedGroup = document.getElementById("scheduledTimeGroup");
    
    if (autoSending && schedTime && schedGroup) {
      autoSending.checked = data.automated_sending || false;
      schedTime.value = data.scheduled_time || "09:00";
      schedGroup.style.display = data.automated_sending ? "block" : "none";
    }
    
  } catch (err) {
    console.error("Error loading config:", err);
  }
}

// Save Configuration Settings
async function setupConfigForm() {
  const form = document.getElementById("configForm");
  const autoSending = document.getElementById("automated_sending");
  const schedGroup = document.getElementById("scheduledTimeGroup");
  
  if (autoSending && schedGroup) {
    autoSending.addEventListener("change", (e) => {
      schedGroup.style.display = e.target.checked ? "block" : "none";
    });
  }
  
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const payload = {
      excel_path: document.getElementById("excel_path").value,
      default_country_code: document.getElementById("default_country_code").value,
      message_template: document.getElementById("message_template").value,
      min_delay_seconds: parseInt(document.getElementById("min_delay_seconds").value),
      max_delay_seconds: parseInt(document.getElementById("max_delay_seconds").value),
      columns: {
        name: document.getElementById("col_name").value,
        phone: document.getElementById("col_phone").value,
        birthday: document.getElementById("col_birthday").value
      },
      automated_sending: document.getElementById("automated_sending").checked,
      scheduled_time: document.getElementById("scheduled_time").value
    };
    
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      showToast(data.message || "Settings updated!");
      loadStatus(); // Reload stats if file path changed
      loadBirthdays();
    } catch (err) {
      showToast("Error updating settings", "error");
    }
  });
}

// Drag and drop Uploader Setup
function setupUploader() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  
  dropzone.addEventListener("click", () => fileInput.click());
  
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
  
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });
  
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });
  
  fileInput.addEventListener("change", (e) => {
    if (fileInput.files.length > 0) {
      handleFileUpload(fileInput.files[0]);
    }
  });
}

async function handleFileUpload(file) {
  const formData = new FormData();
  formData.append("file", file);
  
  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    
    if (res.ok) {
      showToast(data.message);
      loadStatus();
      loadBirthdays();
      loadHistory();
    } else {
      showToast(data.error || "Upload failed", "error");
    }
  } catch (err) {
    showToast("Error uploading file", "error");
  }
}

// Action Buttons: Run wishes, Scan QR
function setupActionButtons() {
  const loginBtn = document.getElementById("loginBtn");
  const sendBtn = document.getElementById("sendBtn");
  const deleteBtn = document.getElementById("deleteSessionBtn");
  const blockerConnectBtn = document.getElementById("blockerConnectBtn");
  
  if (blockerConnectBtn) {
    blockerConnectBtn.addEventListener("click", async () => {
      const blockerPhoneInput = document.getElementById("blockerPhone");
      const phone = blockerPhoneInput.value.trim();
      
      if (!phone) {
        showToast("Please enter a phone number or profile name to connect!", "error");
        return;
      }
      
      currentSession = phone;
      
      try {
        const res = await fetch("/api/login-whatsapp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_phone: phone, headless: true })
        });
        const data = await res.json();
        
        if (res.ok) {
          showToast("WhatsApp connection started. Scan QR code below!");
          startJobPolling();
        } else {
          showToast(data.error || "Failed to start WhatsApp connection", "error");
        }
      } catch (err) {
        showToast("Server connection error", "error");
      }
    });
  }
  
  loginBtn.addEventListener("click", async () => {
    const newSessionInput = document.getElementById("newSessionPhone");
    let sessionToUse = newSessionInput.value.trim();
    
    if (sessionToUse === "") {
      showToast("Please enter a phone number or profile name to link account!", "error");
      return;
    }
    
    try {
      const res = await fetch("/api/login-whatsapp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_phone: sessionToUse, headless: true })
      });
      const data = await res.json();
      
      if (res.ok) {
        showToast("WhatsApp connection started. Scan the QR code below!");
        newSessionInput.value = ""; // Clear input
        currentSession = sessionToUse; // Switch selection to this profile
        
        // Reload session list and switch view
        await loadSessions();
        document.getElementById("sessionSelect").value = currentSession;
        loadStatus();
        loadBirthdays();
        
        startJobPolling();
      } else {
        showToast(data.error || "Failed to launch login", "error");
      }
    } catch (err) {
      showToast("Server communication error", "error");
    }
  });
  
  sendBtn.addEventListener("click", async () => {
    if (!currentSession) {
      showToast("Please connect or select a WhatsApp account first!", "error");
      return;
    }
    
    const forceSend = document.getElementById("forceSendCheck").checked;
    try {
      const res = await fetch("/api/send-wishes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_phone: currentSession, force: forceSend })
      });
      const data = await res.json();
      
      if (res.ok) {
        showToast("Birthday wishing automation job started!");
        startJobPolling();
      } else {
        showToast(data.error || "Failed to start sending job", "error");
      }
    } catch (err) {
      showToast("Server communication error", "error");
    }
  });

  deleteBtn.addEventListener("click", async () => {
    if (!currentSession) {
      showToast("No connected profile to delete.", "error");
      return;
    }
    
    const confirmation = confirm(`Are you sure you want to remove the profile "${currentSession}"?\nThis will log out the user and delete all cache files.`);
    if (!confirmation) return;
    
    try {
      const res = await fetch("/api/delete-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_phone: currentSession })
      });
      const data = await res.json();
      
      if (res.ok) {
        showToast(data.message || "Profile deleted successfully.");
        currentSession = ""; // Reset current session
        await loadSessions();
        loadStatus();
        loadBirthdays();
      } else {
        showToast(data.error || "Failed to delete profile", "error");
      }
    } catch (err) {
      showToast("Server communication error", "error");
    }
  });
  
  // Bind change event to update the active profile and reload data
  const selectEl = document.getElementById("sessionSelect");
  if (selectEl) {
    selectEl.addEventListener("change", (e) => {
      currentSession = e.target.value;
      localStorage.setItem("whatsapp_session", currentSession);
      loadStatus();
      loadBirthdays();
    });
  }
}

// Polling background thread status
function startJobPolling() {
  if (statusPollInterval) clearInterval(statusPollInterval);
  
  // Open console panel if collapsed
  document.getElementById("consolePanel").style.display = "block";
  
  // Disable actions
  setActionsDisabled(true);
  
  statusPollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/job-status?t=${Date.now()}`);
      const job = await res.json();
      
      updateConsoleLogs(job.logs);
      
      if (job.status === "idle" || job.login_detected) {
        clearInterval(statusPollInterval);
        statusPollInterval = null;
        setActionsDisabled(false);
        if (job.login_detected) {
          showToast("WhatsApp login successful! Dashboard unlocked.");
        } else {
          showToast("Process completed.");
        }
        
        // Hide QR Code Containers on completion
        const qrContainer = document.getElementById("qrCodeContainer");
        const blockerQrContainer = document.getElementById("blockerQrCodeContainer");
        if (qrContainer) qrContainer.style.display = "none";
        if (blockerQrContainer) blockerQrContainer.style.display = "none";
        
        // Reload all data
        loadSessions().then(() => {
          loadStatus();
          loadBirthdays();
          loadHistory();
        });
      } else {
        // Update button text to reflect work
        if (job.status === "running_login") {
          document.getElementById("loginBtn").innerHTML = `<span class="spinner"></span> Logging In...`;
          
          // Poll QR code status from server
          try {
            const qrRes = await fetch(`/api/qr-status?session=${currentSession}&t=${Date.now()}`);
            const qrData = await qrRes.json();
            
            const qrContainer = document.getElementById("qrCodeContainer");
            const qrImg = document.getElementById("qrCodeImg");
            
            const blockerQrContainer = document.getElementById("blockerQrCodeContainer");
            const blockerQrImg = document.getElementById("blockerQrImage");
            
            if (qrData.qr_available) {
              if (qrImg) qrImg.src = qrData.qr_url;
              if (qrContainer) qrContainer.style.display = "block";
              
              if (blockerQrImg) blockerQrImg.src = qrData.qr_url;
              if (blockerQrContainer) blockerQrContainer.style.display = "block";
            } else {
              if (qrContainer) qrContainer.style.display = "none";
              if (blockerQrContainer) blockerQrContainer.style.display = "none";
            }
          } catch (qrErr) {
            console.error("Error polling QR code:", qrErr);
          }
        } else if (job.status === "running_send") {
          const qrContainer = document.getElementById("qrCodeContainer");
          const blockerQrContainer = document.getElementById("blockerQrCodeContainer");
          if (qrContainer) qrContainer.style.display = "none";
          if (blockerQrContainer) blockerQrContainer.style.display = "none";
          
          const countStr = job.total_count ? `(${job.success_count + job.failed_count}/${job.total_count})` : "";
          document.getElementById("sendBtn").innerHTML = `<span class="spinner"></span> Sending ${countStr}...`;
        }
      }
    } catch (err) {
      console.error("Polling error:", err);
    }
  }, 1000);
}

function setActionsDisabled(disabled) {
  const loginBtn = document.getElementById("loginBtn");
  const sendBtn = document.getElementById("sendBtn");
  const uploadZone = document.getElementById("dropzone");
  const configBtn = document.getElementById("saveConfigBtn");
  
  loginBtn.disabled = disabled;
  sendBtn.disabled = disabled;
  configBtn.disabled = disabled;
  
  if (disabled) {
    uploadZone.style.pointerEvents = "none";
    uploadZone.style.opacity = "0.5";
  } else {
    uploadZone.style.pointerEvents = "auto";
    uploadZone.style.opacity = "1";
    // Reset buttons texts
    loadStatus();
    document.getElementById("sendBtn").innerHTML = `🚀 Run Birthday Wishes Automation`;
  }
}

function updateConsoleLogs(logs) {
  const consoleEl = document.getElementById("consoleLogs");
  consoleEl.innerHTML = "";
  
  logs.forEach(log => {
    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.innerText = log;
    consoleEl.appendChild(entry);
  });
  
  // Auto scroll
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

// Load Sending History Log
async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const records = await res.json();
    
    const tbody = document.getElementById("historyTableBody");
    tbody.innerHTML = "";
    
    if (records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No sending records logged yet.</td></tr>`;
      return;
    }
    
    // Sort records descending by timestamp (newest first)
    records.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    records.forEach(r => {
      const tr = document.createElement("tr");
      
      let statusClass = "pending";
      let statusText = "Pending";
      if (r.status === "success") {
        statusClass = "sent";
        statusText = "Success";
      } else if (r.status === "invalid_number") {
        statusClass = "failed";
        statusText = "Invalid Number";
      }
      
      tr.innerHTML = `
        <td>${r.timestamp}</td>
        <td class="user-cell">${r.name}</td>
        <td>${r.phone}</td>
        <td><span class="status-indicator ${statusClass}">${statusText}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading history:", err);
  }
}

// Load WhatsApp sessions list
async function loadSessions() {
  try {
    const res = await fetch("/api/sessions");
    const sessions = await res.json();
    
    const select = document.getElementById("sessionSelect");
    select.innerHTML = "";
    
    if (sessions.length === 0) {
      currentSession = "";
      const opt = document.createElement("option");
      opt.value = "";
      opt.innerText = "No connected accounts";
      select.appendChild(opt);
      return;
    }
    
    sessions.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.innerText = `Account: ${s}`;
      select.appendChild(opt);
    });
    
    // Select the current session if valid, else first available
    if (sessions.includes(currentSession)) {
      select.value = currentSession;
    } else {
      currentSession = sessions[0];
      select.value = currentSession;
    }
    localStorage.setItem("whatsapp_session", currentSession);
  } catch (err) {
    console.error("Error loading sessions:", err);
  }
}

// Setup Today/Tomorrow/Month/All toggles
function setupTabs() {
  const tabToday = document.getElementById("tabToday");
  const tabTomorrow = document.getElementById("tabTomorrow");
  const tabMonth = document.getElementById("tabMonth");
  const tabAll = document.getElementById("tabAll");
  const monthSelector = document.getElementById("monthSelectorContainer");
  const monthSelect = document.getElementById("monthSelect");
  
  // Set default selected month based on current date (1-indexed month)
  if (monthSelect) {
    const currentMonthNum = new Date().getMonth() + 1;
    monthSelect.value = currentMonthNum.toString();
    
    monthSelect.addEventListener("change", () => {
      loadBirthdays();
    });
  }
  
  if (tabToday && tabTomorrow && tabMonth && tabAll) {
    tabToday.addEventListener("click", () => {
      activeTab = "today";
      tabToday.classList.add("active");
      tabTomorrow.classList.remove("active");
      tabMonth.classList.remove("active");
      tabAll.classList.remove("active");
      if (monthSelector) monthSelector.style.display = "none";
      loadBirthdays();
    });
    
    tabTomorrow.addEventListener("click", () => {
      activeTab = "tomorrow";
      tabTomorrow.classList.add("active");
      tabToday.classList.remove("active");
      tabMonth.classList.remove("active");
      tabAll.classList.remove("active");
      if (monthSelector) monthSelector.style.display = "none";
      loadBirthdays();
    });
    
    tabMonth.addEventListener("click", () => {
      activeTab = "month";
      tabMonth.classList.add("active");
      tabToday.classList.remove("active");
      tabTomorrow.classList.remove("active");
      tabAll.classList.remove("active");
      if (monthSelector) monthSelector.style.display = "flex";
      loadBirthdays();
    });
    
    tabAll.addEventListener("click", () => {
      activeTab = "all";
      tabAll.classList.add("active");
      tabToday.classList.remove("active");
      tabTomorrow.classList.remove("active");
      tabMonth.classList.remove("active");
      if (monthSelector) monthSelector.style.display = "none";
      loadBirthdays();
    });
  }
}

// Filter birthday table records client-side and render current page slice
function applyTableFilterAndRender() {
  const tbody = document.getElementById("birthdayTableBody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  const queryInput = document.getElementById("tableSearchInput");
  const query = queryInput ? queryInput.value.trim().toLowerCase() : "";
  
  filteredRecords = birthdayRecords.filter(b => {
    return (b.name || "").toLowerCase().includes(query) || 
           (b.phone || "").toLowerCase().includes(query) || 
           String(b.row || "").includes(query) ||
           (b.birthday || "").toLowerCase().includes(query) ||
           (b.status || "").toLowerCase().includes(query);
  });
  
  const totalRecords = filteredRecords.length;
  
  if (totalRecords === 0) {
    let dayText = "today";
    if (activeTab === "tomorrow") {
      dayText = "tomorrow";
    } else if (activeTab === "month") {
      const monthSelect = document.getElementById("monthSelect");
      const monthName = monthSelect ? monthSelect.options[monthSelect.selectedIndex].text : "this month";
      dayText = monthName;
    } else if (activeTab === "all") {
      dayText = "all directory records";
    }
    
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">🎉 No birthdays found for ${dayText}!</td></tr>`;
    
    // Update pagination controls to disabled/empty state
    const infoText = document.getElementById("tableInfoText");
    if (infoText) infoText.innerText = "Showing 0 to 0 of 0 students";
    
    const prevBtn = document.getElementById("prevPageBtn");
    const nextBtn = document.getElementById("nextPageBtn");
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    return;
  }
  
  // Calculate paging indexes
  const maxPage = Math.ceil(totalRecords / pageSize);
  if (currentPage > maxPage) currentPage = maxPage;
  if (currentPage < 1) currentPage = 1;
  
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, totalRecords);
  
  const pageSlice = filteredRecords.slice(startIndex, endIndex);
  
  pageSlice.forEach(b => {
    const tr = document.createElement("tr");
    
    let statusClass = "pending";
    let statusText = "Pending";
    if (b.status === "sent") {
      statusClass = "sent";
      statusText = "Sent";
    } else if (b.status === "failed") {
      statusClass = "failed";
      statusText = "Failed";
    } else if (b.status === "upcoming") {
      statusClass = "upcoming";
      statusText = "Upcoming";
    } else if (b.status === "passed") {
      statusClass = "passed";
      statusText = "Passed";
    }
    
    tr.innerHTML = `
      <td class="user-cell">${b.name}</td>
      <td>${b.phone}</td>
      <td>${b.birthday}</td>
      <td><span class="status-indicator ${statusClass}">${statusText}</span></td>
      <td>Row ${b.row}</td>
    `;
    tbody.appendChild(tr);
  });
  
  // Update Info Text and buttons
  const infoText = document.getElementById("tableInfoText");
  if (infoText) {
    infoText.innerText = `Showing ${startIndex + 1} to ${endIndex} of ${totalRecords} student(s)`;
  }
  
  const prevBtn = document.getElementById("prevPageBtn");
  const nextBtn = document.getElementById("nextPageBtn");
  
  if (prevBtn) prevBtn.disabled = (currentPage === 1);
  if (nextBtn) nextBtn.disabled = (endIndex >= totalRecords);
}

// Bind listeners for search and paging controls
function setupTableControls() {
  const searchInput = document.getElementById("tableSearchInput");
  const pageSizeSelect = document.getElementById("pageSizeSelect");
  const prevBtn = document.getElementById("prevPageBtn");
  const nextBtn = document.getElementById("nextPageBtn");
  
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      currentPage = 1;
      applyTableFilterAndRender();
    });
  }
  
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener("change", (e) => {
      pageSize = parseInt(e.target.value);
      currentPage = 1;
      applyTableFilterAndRender();
    });
  }
  
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        applyTableFilterAndRender();
      }
    });
  }
  
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      if ((currentPage * pageSize) < filteredRecords.length) {
        currentPage++;
        applyTableFilterAndRender();
      }
    });
  }
}
