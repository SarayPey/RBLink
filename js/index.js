document.addEventListener('DOMContentLoaded', () => {
  const session = JSON.parse(localStorage.getItem('rblink_session') || 'null');
  const userGreeting = document.getElementById('userGreeting');
  const logoutBtn = document.getElementById('logoutBtn');

  if (!session || !session.isLoggedIn) {
    window.location.href = 'login.html';
    return;
  }

  if (userGreeting) {
    const roleLabel = session.role === 'admin' ? 'Administrador' : session.role === 'funcionario' ? 'Funcionario' : 'Estudiante';
    userGreeting.textContent = `Bienvenido, ${session.name || session.email} (${roleLabel})`;
  }

  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      localStorage.removeItem('rblink_session');
      window.location.href = 'login.html';
    });
  }
});
