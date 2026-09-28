(() => {
  'use strict';

  const form = document.getElementById('auth-form');
  const signin = document.getElementById('signin-tab');
  const signup = document.getElementById('signup-tab');
  const nameField = document.getElementById('name-field');
  const confirmField = document.getElementById('confirm-field');
  const forgot = document.getElementById('forgot');
  const passwordHint = document.getElementById('password-hint');
  const password = document.getElementById('password');
  const notice = document.getElementById('notice');
  const submitButton = form.querySelector('button[type="submit"]');
  const submitLabel = document.getElementById('submit-label');
  let mode = 'signin';

  function setMode(next) {
    mode = next;
    const creating = mode === 'signup';
    signin.classList.toggle('active', !creating);
    signup.classList.toggle('active', creating);
    signin.setAttribute('aria-selected', String(!creating));
    signup.setAttribute('aria-selected', String(creating));
    nameField.hidden = !creating;
    confirmField.hidden = !creating;
    forgot.hidden = creating;
    passwordHint.hidden = !creating;
    password.autocomplete = creating ? 'new-password' : 'current-password';
    document.getElementById('form-title').textContent =
      creating ? 'Create your account' : 'Log in to your account';
    document.getElementById('form-subtitle').textContent =
      creating ? 'Join the KCG College aerospace community.' : 'Continue your aerospace research.';
    submitLabel.textContent = creating ? 'Create account' : 'Log in';
    notice.hidden = true;
    notice.textContent = '';
  }

  signin.addEventListener('click', () => setMode('signin'));
  signup.addEventListener('click', () => setMode('signup'));

  document.getElementById('toggle-password').addEventListener('click', event => {
    const visible = password.type === 'password';
    password.type = visible ? 'text' : 'password';
    event.currentTarget.textContent = visible ? 'Hide' : 'Show';
    event.currentTarget.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
  });

  function showNotice(message, error = false) {
    notice.textContent = message;
    notice.classList.toggle('error', error);
    notice.hidden = false;
  }

  forgot.addEventListener('click', () => {
    showNotice('Password recovery is not available yet. Please contact the AVARIX administrator.');
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitButton.disabled) return;

    const email = document.getElementById('email').value.trim().toLowerCase();
    const name = document.getElementById('full-name').value.trim();
    const confirmPassword = document.getElementById('confirm-password').value;
    const creating = mode === 'signup';

    if (!/^[^\s@]+@kcgcollege\.com$/i.test(email)) {
      showNotice('Please use a valid @kcgcollege.com email address.', true);
      return;
    }
    if (creating && (!name || name.length > 120)) {
      showNotice('Please enter your name (1–120 characters).', true);
      return;
    }
    if (password.value.length < (creating ? 8 : 1)) {
      showNotice(creating ? 'Password must contain at least 8 characters.' : 'Enter your password.', true);
      return;
    }
    if (password.value.length > 1024) {
      showNotice('Password is too long.', true);
      return;
    }
    if (creating && password.value !== confirmPassword) {
      showNotice('The passwords do not match.', true);
      return;
    }

    submitButton.disabled = true;
    submitLabel.textContent = creating ? 'Creating account…' : 'Logging in…';
    notice.hidden = true;

    try {
      const endpoint = creating ? '/api/auth/signup' : '/api/auth/login';
      const payload = creating
        ? { name, email, password: password.value }
        : { email, password: password.value };

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload)
      });

      let data = {};
      try { data = await response.json(); } catch (_) {}

      if (!response.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : 'Unable to complete your request. Please try again.';
        showNotice(detail, true);
        return;
      }

      // The backend sets the signed avarix_session cookie on successful login/signup.
      window.location.replace('/app');
    } catch (error) {
      showNotice('Could not connect to AVARIX. Check your internet connection and try again.', true);
    } finally {
      submitButton.disabled = false;
      submitLabel.textContent = mode === 'signup' ? 'Create account' : 'Log in';
    }
  });

  setMode('signin');
})();
