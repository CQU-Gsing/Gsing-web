document.addEventListener("DOMContentLoaded", () => {
  const tabs = document.querySelectorAll("[data-auth-tab]");
  const panels = document.querySelectorAll("[data-auth-panel]");
  const activate = (name) => {
    tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.authTab === name));
    panels.forEach((panel) => { panel.hidden = panel.dataset.authPanel !== name; });
  };
  tabs.forEach((tab) => tab.addEventListener("click", () => activate(tab.dataset.authTab)));
  if (new URLSearchParams(location.search).get("mode") === "code") activate("code");

  const password = document.getElementById("password");
  const strengthBar = document.getElementById("strengthBar");
  if (password && strengthBar) password.addEventListener("input", () => {
    const value = password.value;
    let score = value.length >= 8 ? 1 : 0;
    if (/[A-Za-z]/.test(value) && /\d/.test(value)) score += 1;
    if (/[^A-Za-z0-9]/.test(value) || value.length >= 12) score += 1;
    strengthBar.className = `strength-bar ${["", "weak", "medium", "strong"][score]}`;
  });

  document.querySelectorAll("[data-send-code]").forEach((button) => {
    button.addEventListener("click", async () => {
      const form = button.closest("form");
      const email = form.querySelector("[data-email]").value.trim();
      const message = document.querySelector("[data-code-message]");
      if (!email || !email.includes("@")) { message.textContent = "请输入有效的邮箱地址"; message.className = "code-message error"; return; }
      button.disabled = true; button.textContent = "发送中…";
      try {
        const response = await fetch("/api/email-code", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, purpose: button.dataset.purpose }) });
        const data = await response.json();
        message.textContent = data.message; message.className = `code-message ${data.ok ? "success" : "error"}`;
        if (!data.ok) { button.disabled = false; button.textContent = "发送验证码"; return; }
        let seconds = 60; button.textContent = `重新发送 (${seconds}s)`;
        const timer = setInterval(() => { seconds -= 1; button.textContent = `重新发送 (${seconds}s)`; if (seconds <= 0) { clearInterval(timer); button.disabled = false; button.textContent = "发送验证码"; } }, 1000);
      } catch (_) { message.textContent = "网络错误，请稍后重试"; message.className = "code-message error"; button.disabled = false; button.textContent = "发送验证码"; }
    });
  });
});
