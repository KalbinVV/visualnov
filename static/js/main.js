// Общий файл для всех страниц

// Функция для форматирования даты
function formatDate(dateString) {
  const date = new Date(dateString);
  return date.toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
}

// Функция для показа уведомлений
function showNotification(message, type = 'info') {
  // Создание уведомления
  const notification = document.createElement('div');
  notification.className = `notification notification-${type}`;
  notification.textContent = message;

  // Добавление в документ
  document.body.appendChild(notification);

  // Автоматическое удаление через 3 секунды
  setTimeout(() => {
    notification.style.opacity = '0';
    notification.style.transform = 'translateY(-20px)';
    setTimeout(() => {
      notification.remove();
    }, 300);
  }, 3000);
}

// Защита от выхода со страницы с формой
function preventFormExit(formId) {
  let formChanged = false;

  if (formId) {
    const form = document.getElementById(formId);
    if (form) {
      form.addEventListener('input', () => {
        formChanged = true;
      });
    }
  }

  window.addEventListener('beforeunload', (e) => {
    if (formChanged) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', function() {
  console.log('Любовный симулятор загружен ✨');
});