// Frontend logic for WhatsApp Birthday Dashboard

let statusPollInterval = null;
let currentSession = "Default";
let activeTab = "today";

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
    const res = await fetch(`/api/status?session=${currentSession}`);
    const data = await res.json();
    
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
    
    const tbody = document.getElementById("birthdayTableBody");
    tbody.innerHTML = "";
    
    if (data.birthdays.length === 0) {
      let dayText = "today";
      if (activeTab === "tomorrow") {
        dayText = "tomorrow";
      } else if (activeTab === "month") {
        const monthSelect = document.getElementById("monthSelect");
        const monthName = monthSelect ? monthSelect.options[monthSelect.selectedIndex].text : "this month";
        dayText = monthName;
      }
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">🎉 No birthdays found for ${dayText}!</td></tr>`;
      return;
    }
    
    data.birthdays.forEach(b => {
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
    
    document.getElementById("col_name").value = data.columns?.name || "Name";
    document.getElementById("col_phone").value = data.columns?.phone || "Phone";
    document.getElementById("col_birthday").value = data.columns?.birthday || "Birthday";
    
  } catch (err) {
    console.error("Error loading config:", err);
  }
}

// Save Configuration Settings
async function setupConfigForm() {
  const form = document.getElementById("configForm");
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
      }
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
  
  loginBtn.addEventListener("click", async () => {
    const newSessionInput = document.getElementById("newSessionPhone");
    let sessionToUse = newSessionInput.value.trim();
    
    if (sessionToUse === "") {
      const promptPhone = prompt("Enter a phone number or profile name to connect a new user:\n(Or leave blank to re-login/re-scan for the currently selected profile)");
      if (promptPhone === null) return; // User clicked Cancel
      if (promptPhone.trim() !== "") {
        sessionToUse = promptPhone.trim();
      } else {
        sessionToUse = currentSession;
      }
    }
    
    try {
      const res = await fetch("/api/login-whatsapp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_phone: sessionToUse })
      });
      const data = await res.json();
      
      if (res.ok) {
        showToast("WhatsApp Browser Opened. Scan QR Code!");
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
    const forceSend = document.getElementById("forceSendCheck").checked;
    try {
      const res = await fetch("/api/send-wishes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          force: forceSend,
          session_phone: currentSession
        })
      });
      const data = await res.json();
      
      if (res.ok) {
        showToast("Wishing process initiated!");
        startJobPolling();
      } else {
        showToast(data.error || "Failed to start sending", "error");
      }
    } catch (err) {
      showToast("Server communication error", "error");
    }
  });

  deleteBtn.addEventListener("click", async () => {
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
        currentSession = "Default"; // Reset to default session
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
      const res = await fetch("/api/job-status");
      const job = await res.json();
      
      updateConsoleLogs(job.logs);
      
      if (job.status === "idle") {
        clearInterval(statusPollInterval);
        statusPollInterval = null;
        setActionsDisabled(false);
        showToast("Process completed.");
        
        // Hide QR Code Container on completion
        document.getElementById("qrCodeContainer").style.display = "none";
        
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
            const qrRes = await fetch(`/api/qr-status?session=${currentSession}`);
            const qrData = await qrRes.json();
            const qrContainer = document.getElementById("qrCodeContainer");
            const qrImg = document.getElementById("qrCodeImg");
            
            if (qrData.qr_available) {
              qrImg.src = qrData.qr_url;
              qrContainer.style.display = "block";
            } else {
              qrContainer.style.display = "none";
            }
          } catch (qrErr) {
            console.error("Error polling QR code:", qrErr);
          }
        } else if (job.status === "running_send") {
          document.getElementById("qrCodeContainer").style.display = "none"; // Ensure QR is hidden
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
    
    // Ensure Default is always an option
    if (!sessions.includes("Default")) {
      sessions.unshift("Default");
    }
    
    sessions.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.innerText = s === "Default" ? "Default Account" : `Account: ${s}`;
      select.appendChild(opt);
    });
    
    // Select the current session
    select.value = currentSession;
  } catch (err) {
    console.error("Error loading sessions:", err);
  }
}

// Setup Today/Tomorrow/Month toggles
function setupTabs() {
  const tabToday = document.getElementById("tabToday");
  const tabTomorrow = document.getElementById("tabTomorrow");
  const tabMonth = document.getElementById("tabMonth");
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
  
  if (tabToday && tabTomorrow && tabMonth) {
    tabToday.addEventListener("click", () => {
      activeTab = "today";
      tabToday.classList.add("active");
      tabTomorrow.classList.remove("active");
      tabMonth.classList.remove("active");
      if (monthSelector) monthSelector.style.display = "none";
      loadBirthdays();
    });
    
    tabTomorrow.addEventListener("click", () => {
      activeTab = "tomorrow";
      tabTomorrow.classList.add("active");
      tabToday.classList.remove("active");
      tabMonth.classList.remove("active");
      if (monthSelector) monthSelector.style.display = "none";
      loadBirthdays();
    });
    
    tabMonth.addEventListener("click", () => {
      activeTab = "month";
      tabMonth.classList.add("active");
      tabToday.classList.remove("active");
      tabTomorrow.classList.remove("active");
      if (monthSelector) monthSelector.style.display = "flex";
      loadBirthdays();
    });
  }
}
