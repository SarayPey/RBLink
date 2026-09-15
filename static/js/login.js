document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('loginForm');
  const errorMessage = document.getElementById('errorMessage');

  if (!loginForm) return;

  const session = JSON.parse(localStorage.getItem('rblink_session') || 'null');
  if (session && session.isLoggedIn) {
    window.location.href = 'index.html';
    return;
  }

  loginForm.addEventListener('submit', (event) => {
    event.preventDefault();
    errorMessage.textContent = '';

    const email = document.getElementById('email').value.trim().toLowerCase();
    const password = document.getElementById('password').value.trim();

    if (!email || !password) {
      errorMessage.textContent = 'Por favor, completa todos los campos.';
      return;
    }

    const users = JSON.parse(localStorage.getItem('rblink_users') || '[]');
    const user = Array.isArray(users)
      ? users.find((item) => item && item.email && item.email.toLowerCase() === email && item.password === password)
      : null;

    if (!user) {
      errorMessage.textContent = 'Correo o contraseña incorrectos.';
      return;
    }

    localStorage.setItem('rblink_session', JSON.stringify({
      isLoggedIn: true,
      name: user.name,
      email: user.email,
      role: user.role
    }));

    window.location.href = 'index.html';
  });
});
