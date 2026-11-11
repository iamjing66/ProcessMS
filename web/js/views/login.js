/**
 * 登录视图：账号密码登录，错误内联提示，token 由 auth.js 写入 sessionStorage
 */
import { login } from "../auth.js";
import { escapeHtml } from "../format.js";

let bound = false;

export function render(container, context = {}) {
  const form = container.querySelector("#login-form");
  const usernameInput = container.querySelector("#login-username");
  const passwordInput = container.querySelector("#login-password");
  const submitButton = container.querySelector("#login-submit");
  const errorBox = container.querySelector("#login-error");

  if (!form || !usernameInput || !passwordInput || !submitButton) return;

  const showError = (message) => {
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.hidden = !message;
  };

  showError("");
  if (!bound) {
    bound = true;
    setTimeout(() => usernameInput.focus(), 50);
  }

  form.onsubmit = async (event) => {
    event.preventDefault();
    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    if (!username) {
      showError("请输入用户名");
      usernameInput.focus();
      return;
    }
    if (!password) {
      showError("请输入密码");
      passwordInput.focus();
      return;
    }

    showError("");
    const originalText = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.textContent = "登录中…";

    try {
      await login(username, password);
      passwordInput.value = "";
      context.onLoggedIn?.();
    } catch (error) {
      showError(error && error.message ? error.message : "登录失败，请稍后重试");
      passwordInput.select();
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalText;
    }
  };
}
