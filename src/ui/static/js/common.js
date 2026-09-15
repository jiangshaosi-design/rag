/* === Shared Utilities === */
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function scrollToBottom(el) {
  el.scrollTop = el.scrollHeight;
}
