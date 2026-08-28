// ============================================================
// SkillSwap — Auth logic
// Uses browser localStorage so the whole flow works without a
// backend yet. When you build the Flask + MySQL API from the
// synopsis, swap the localStorage calls below for fetch() calls
// to your endpoints — the form markup stays the same.
// ============================================================

function getUsers() {
  return JSON.parse(localStorage.getItem("skillswap_users") || "[]");
}

function saveUsers(users) {
  localStorage.setItem("skillswap_users", JSON.stringify(users));
}

function showAlert(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
}

// ---- Register ----
const registerForm = document.getElementById("registerForm");
if (registerForm) {
  registerForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const name = document.getElementById("name").value.trim();
    const email = document.getElementById("email").value.trim().toLowerCase();
    const password = document.getElementById("password").value;

    const users = getUsers();

    if (users.some((u) => u.email === email)) {
      showAlert("errorMsg", "An account with this email already exists.");
      return;
    }

    users.push({ name, email, password });
    saveUsers(users);

    showAlert("successMsg", "Account created! Redirecting to login...");
    setTimeout(() => {
      window.location.href = "login";
    }, 1100);
  });
}

// ---- Login ----
const loginForm = document.getElementById("loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const email = document.getElementById("email").value.trim().toLowerCase();
    const password = document.getElementById("password").value;

    const users = getUsers();
    const match = users.find((u) => u.email === email && u.password === password);

    if (!match) {
      showAlert("errorMsg", "Invalid email or password.");
      return;
    }

    localStorage.setItem("skillswap_current_user", JSON.stringify(match));
    window.location.href = "dashboard";
  });
}

// ---- Dashboard ----
const logoutBtn = document.getElementById("logoutBtn");
if (logoutBtn) {
  const current = JSON.parse(localStorage.getItem("skillswap_current_user") || "null");

  if (!current) {
    window.location.href = "login";
  } else {
    const firstName = current.name.split(" ")[0];
    document.getElementById("userName").textContent = firstName;
    document.getElementById("profileName").textContent = current.name;
    document.getElementById("profileEmail").textContent = current.email;
    document.getElementById("avatarLetter").textContent = firstName.charAt(0).toUpperCase();
  }

  logoutBtn.addEventListener("click", function () {
    localStorage.removeItem("skillswap_current_user");
    window.location.href = "login";
  });
}