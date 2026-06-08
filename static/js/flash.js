document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('flash-container');
    if (!container) return;
    // Fecha ao clicar no “×”
    container.addEventListener('click', e => {
        if (e.target.classList.contains('flash-close')) {
            const flash = e.target.closest('.flash');
            flash?.remove();
        }
    });
    // Auto‑dismiss após N milissegundos (default 5000)
    const AUTO_DISMISS_MS = 5000;
    const flashes = container.querySelectorAll('.flash');
    flashes.forEach(flash => {
        setTimeout(() => flash.remove(), AUTO_DISMISS_MS);
    });
});
