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

    // Live Q&A functionality
    const qnaContainer = document.querySelector('#qna-container');
    if (qnaContainer) {
        const sessionId = qnaContainer.dataset.sessionId;
        const socket = io();

        socket.emit('join_session', { session_id: sessionId });

        socket.on('new_qna', (data) => {
            const qnaDiv = document.createElement('div');
            qnaDiv.className = 'qna-message';
            qnaDiv.style.marginBottom = '0.5rem';
            qnaDiv.style.display = 'flex';
            qnaDiv.style.justifyContent = data.is_answer ? 'flex-end' : 'flex-start';

            const bubble = document.createElement('div');
            bubble.className = `chat-bubble ${data.is_answer ? 'sent' : 'received'}`;
            bubble.innerHTML = `
                <p style="font-size: 0.875rem;"><strong>${data.username}</strong> (${data.timestamp})</p>
                <p>${data.content}</p>
            `;
            qnaDiv.appendChild(bubble);
            qnaContainer.appendChild(qnaDiv);
            qnaContainer.scrollTop = qnaContainer.scrollHeight;
        });

        const qnaForm = document.querySelector('#qna-form');
        if (qnaForm) {
            qnaForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const input = document.querySelector('#qna-input');
                const content = input.value.trim();
                if (content) {
                    const isAnswer = qnaForm.dataset.isFounder === 'true';
                    socket.emit('send_qna', {
                        session_id: sessionId,
                        content: content,
                        is_answer: isAnswer
                    });
                    input.value = '';
                }
            });
        }
    }
});