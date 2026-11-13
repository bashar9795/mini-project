
// ============================================================
// SkillSwap — Frontend JavaScript
// Authentication is handled by Flask + MySQL.
// Do NOT use localStorage for login or user authentication.
// ============================================================

function showAlert(id, msg) {
    const el = document.getElementById(id);

    if (!el) return;

    el.textContent = msg;
    el.classList.add("show");
}

// ============================================================
// REGISTER PAGE
// ============================================================

// Registration is submitted directly to Flask.
// Flask validates the data and saves the user in MySQL.
// Do not prevent the form's normal submission.

const registerForm = document.getElementById("registerForm");

if (registerForm) {
    registerForm.addEventListener("submit", function () {
        const password = document.getElementById("password");

        if (password && password.value.length < 6) {
            // Let HTML/Flask handle validation as appropriate.
            // No localStorage authentication is performed here.
        }
    });
}

// ============================================================
// LOGIN PAGE
// ============================================================

// Login is submitted directly to Flask.
// Flask checks the password and creates the session.
// Flask decides where to redirect after successful login.

const loginForm = document.getElementById("loginForm");

if (loginForm) {
    loginForm.addEventListener("submit", function () {
        // Do not call preventDefault().
        // Do not check credentials in JavaScript.
    });
}

// ============================================================
// DASHBOARD PAGE
// ============================================================

// User information should come from Flask/Jinja,
// not from browser localStorage.

const logoutBtn = document.getElementById("logoutBtn");

if (logoutBtn) {
    logoutBtn.addEventListener("click", function () {
        window.location.href = "/logout";
    });
}

// ============================================================
// PROFILE PAGE
// ============================================================

// Flask should populate profile fields using Jinja.
// Profile form submission must be handled by a Flask POST route.
// Do not load or save profile information using localStorage.

const profileForm = document.getElementById("profileForm");

if (profileForm) {
    profileForm.addEventListener("submit", function () {
        // Allow normal form submission to Flask.
        // Do not call preventDefault().
    });
}

// ============================================================
// COMMUNICATION WINDOW
// ============================================================

const chatThread = document.getElementById("chatThread");

function appendChatMessage(item) {
    const empty = document.getElementById("chatEmpty");
    if (empty) {
        empty.remove();
    }

    const article = document.createElement("article");
    article.className = "bubble" + (item.mine ? " mine" : "");

    if (item.body) {
        const text = document.createElement("p");
        text.textContent = item.body;
        article.appendChild(text);
    }

    if (item.file_name && item.file_url) {
        const link = document.createElement("a");
        link.href = item.file_url;
        link.textContent = item.file_name;
        if (item.is_image) {
            link.target = "_blank";
            link.rel = "noopener";
            const image = document.createElement("img");
            image.src = item.file_url;
            image.alt = item.file_name;
            link.textContent = "";
            link.appendChild(image);
        }
        article.appendChild(link);
    }

    const time = document.createElement("time");
    time.textContent = item.created_at || "";
    article.appendChild(time);
    chatThread.appendChild(article);
}

if (chatThread) {
    chatThread.scrollTop = chatThread.scrollHeight;
    const partnerId = chatThread.dataset.partnerId;

    window.setInterval(function () {
        const after = chatThread.dataset.after || "0";
        fetch("/chat/" + partnerId + "/updates?after=" + encodeURIComponent(after))
            .then(function (response) {
                if (!response.ok) {
                    return [];
                }
                return response.json();
            })
            .then(function (items) {
                if (!Array.isArray(items) || items.length === 0) {
                    return;
                }
                items.forEach(appendChatMessage);
                chatThread.dataset.after = String(items[items.length - 1].id);
                chatThread.scrollTop = chatThread.scrollHeight;
            })
            .catch(function () {
                // Keep the open conversation usable if a refresh fails.
            });
    }, 4000);
}
