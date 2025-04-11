document.addEventListener('DOMContentLoaded', () => {
    // Form validation for founder dashboard
    const startupForm = document.querySelector('#startup-form');
    if (startupForm) {
        startupForm.addEventListener('submit', (e) => {
            const funding = document.querySelector('#funding_needed').value;
            if (funding <= 0) {
                e.preventDefault();
                alert('Funding needed must be greater than zero.');
            }
        });
    }

    // Form validation for investment form
    const investForm = document.querySelector('#invest-form');
    if (investForm) {
        investForm.addEventListener('submit', (e) => {
            const amount = document.querySelector('#amount').value;
            if (amount <= 0) {
                e.preventDefault();
                alert('Investment amount must be greater than zero.');
            }
        });
    }

    // Smooth scroll for message container
    const messageContainer = document.querySelector('#message-container');
    if (messageContainer) {
        messageContainer.scrollTop = messageContainer.scrollHeight;
    }

    // Fade-in animation for cards
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        setTimeout(() => {
            card.style.transition = 'opacity 0.5s ease';
            card.style.opacity = '1';
        }, index * 100);
    });
});