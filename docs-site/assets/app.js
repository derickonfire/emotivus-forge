for (const node of document.querySelectorAll('[data-year]')) node.textContent = new Date().getFullYear();
const menuButton = document.querySelector('[data-menu-toggle]');
const menu = document.querySelector('[data-nav-links]');
if (menuButton && menu) {
  menuButton.addEventListener('click', () => {
    const open = menu.classList.toggle('open');
    menuButton.setAttribute('aria-expanded', String(open));
  });
  for (const link of menu.querySelectorAll('a')) link.addEventListener('click', () => {
    menu.classList.remove('open');
    menuButton.setAttribute('aria-expanded', 'false');
  });
}
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    const value = button.getAttribute('data-copy') || '';
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(value);
      button.textContent = 'Copied';
    } catch {
      button.textContent = value;
    }
    window.setTimeout(() => { button.textContent = original; }, 1800);
  });
}
