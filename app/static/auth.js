(() => {
  const form = document.getElementById('auth-form');
  const signin = document.getElementById('signin-tab');
  const signup = document.getElementById('signup-tab');
  const nameField = document.getElementById('name-field');
  const confirmField = document.getElementById('confirm-field');
  const forgot = document.getElementById('forgot');
  const passwordHint = document.getElementById('password-hint');
  const password = document.getElementById('password');
  const notice = document.getElementById('notice');
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
    document.getElementById('form-title').textContent = creating ? 'Create your account' : 'Log in to your account';
    document.getElementById('form-subtitle').textContent = creating ? 'Join the KCG College aerospace community.' : 'Continue your aerospace research.';
    document.getElementById('submit-label').textContent = creating ? 'Create account' : 'Log in';
    notice.hidden = true;
  }
  signin.addEventListener('click', () => setMode('signin'));
  signup.addEventListener('click', () => setMode('signup'));
  document.getElementById('toggle-password').addEventListener('click', e => {
    const visible = password.type === 'password';
    password.type = visible ? 'text' : 'password';
    e.currentTarget.textContent = visible ? 'Hide' : 'Show';
    e.currentTarget.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
  });
  function showNotice(message, error = false) {
    notice.textContent = message;
    notice.classList.toggle('error', error);
    notice.hidden = false;
  }
  forgot.addEventListener('click', () => showNotice('Password recovery will be available once account services are connected.'));
  form.addEventListener('submit', e => {
    e.preventDefault();
    const email = document.getElementById('email').value.trim();
    const domain = email.split('@').pop().toLowerCase();
    if (!/^[^\s@]+@kcgcollege\.com$/i.test(email)) {
      showNotice('Please use a valid @kcgcollege.com email address.', true); return;
    }
    if (password.value.length < (mode === 'signup' ? 8 : 1)) {
      showNotice(mode === 'signup' ? 'Password must contain at least 8 characters.' : 'Enter your password.', true); return;
    }
    if (mode === 'signup' && password.value !== document.getElementById('confirm-password').value) {
      showNotice('The passwords do not match.', true); return;
    }
    showNotice('The account interface is ready. Authentication needs to be connected to the AVARIX backend before sign-in or registration can work.');
  });
})();
