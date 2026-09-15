document.addEventListener('DOMContentLoaded', () => {
  const registerForm = document.getElementById('registerForm');
  const errorMessage = document.getElementById('errorMessage');
  const successMessage = document.getElementById('successMessage');

  if (!registerForm) return;

  const readUsers = () => {
    try {
      const savedUsers = JSON.parse(localStorage.getItem('rblink_users') || '[]');
      return Array.isArray(savedUsers) ? savedUsers : [];
    } catch (error) {
      return [];
    }
  };

  const session = JSON.parse(localStorage.getItem('rblink_session') || 'null');
  if (session && session.isLoggedIn) {
    window.location.href = 'index.html';
    return;
  }

  registerForm.addEventListener('submit', (event) => {
    event.preventDefault();
    errorMessage.textContent = '';
    successMessage.textContent = '';

    const fullName = document.getElementById('fullName').value.trim();
    const email = document.getElementById('email').value.trim().toLowerCase();
    const role = document.getElementById('role').value;
    const password = document.getElementById('password').value.trim();
    const confirmPassword = document.getElementById('confirmPassword').value.trim();

    if (!fullName || !email || !role || !password || !confirmPassword) {
      errorMessage.textContent = 'Por favor, completa todos los campos.';
      return;
    }

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(email)) {
      errorMessage.textContent = 'Ingresa un correo institucional válido.';
      return;
    }

    if (password.length < 6) {
      errorMessage.textContent = 'La contraseña debe tener al menos 6 caracteres.';
      return;
    }

    if (password !== confirmPassword) {
      errorMessage.textContent = 'Las contraseñas no coinciden.';
      return;
    }

    const users = readUsers();
    const emailAlreadyExists = users.some((user) => user && typeof user.email === 'string' && user.email.toLowerCase() === email);

    if (emailAlreadyExists) {
      errorMessage.textContent = 'Este correo ya está registrado.';
      return;
    }

    users.push({
      name: fullName,
      email,
      role,
      password
    });

    localStorage.setItem('rblink_users', JSON.stringify(users));
    registerForm.reset();
    successMessage.textContent = 'Usuario registrado correctamente. Redirigiendo al inicio de sesión...';

    setTimeout(() => {
      window.location.href = 'login.html';
    }, 1200);
  });
});
