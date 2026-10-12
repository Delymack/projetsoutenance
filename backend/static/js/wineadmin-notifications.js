(function () {
    'use strict';

    const root = document.getElementById('wine-notifications');
    if (!root) return;

    const trigger = document.getElementById('wine-notifications-trigger');
    const menu = document.getElementById('wine-notifications-menu');
    if (!trigger || !menu) return;

    let currentFilter = 'all';

    function closeMenu() {
        menu.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        root.classList.remove('show');
    }

    function applyFilter() {
        menu.querySelectorAll('.wine-notification-row').forEach(function (row) {
            const state = row.dataset.notificationState;
            row.hidden = currentFilter !== 'all' && state !== currentFilter;
        });
        menu.querySelectorAll('[data-notification-filter]').forEach(function (button) {
            button.setAttribute(
                'aria-pressed',
                String(button.dataset.notificationFilter === currentFilter)
            );
        });
    }

    function updateUnreadCount(count) {
        let badge = document.getElementById('wine-notifications-count');
        if (count > 0 && !badge) {
            badge = document.createElement('span');
            badge.id = 'wine-notifications-count';
            badge.className = 'wine-notifications-count';
            badge.setAttribute('aria-hidden', 'true');
            trigger.appendChild(badge);
        }
        if (badge) {
            badge.textContent = count > 99 ? '99+' : String(count);
            badge.hidden = count === 0;
        }
        trigger.setAttribute('aria-label', 'Notifications : ' + count + ' non lue(s)');
        const label = menu.querySelector('.wine-notifications-unread-label');
        if (label) label.textContent = count + ' non lue' + (count === 1 ? '' : 's');
        const markAll = menu.querySelector('[data-notification-action="read_all"]');
        if (markAll) markAll.hidden = count === 0;
    }

    function showEmptyMessage() {
        const list = document.getElementById('wine-notifications-list');
        if (!list || list.querySelector('.wine-notification-row')) return;
        list.remove();
        const empty = document.createElement('p');
        empty.id = 'wine-notifications-empty';
        empty.className = 'wine-notifications-empty';
        empty.innerHTML = '<i class="fas fa-circle-check" aria-hidden="true"></i> Aucune notification pour le moment.';
        menu.appendChild(empty);
    }

    function updateRowState(row, state) {
        row.dataset.notificationState = state;
        row.classList.toggle('is-unread', state === 'unread');
        const stateButton = row.querySelector('[data-notification-action="read"], [data-notification-action="unread"]');
        if (stateButton) {
            const unread = state === 'unread';
            stateButton.dataset.notificationAction = unread ? 'read' : 'unread';
            stateButton.title = unread ? 'Marquer comme lue' : 'Marquer comme non lue';
            stateButton.setAttribute('aria-label', stateButton.title);
            const icon = stateButton.querySelector('i');
            if (icon) icon.className = 'fas ' + (unread ? 'fa-check' : 'fa-envelope');
        }
    }

    async function performAction(button) {
        const action = button.dataset.notificationAction;
        const row = button.closest('.wine-notification-row');
        const token = menu.querySelector('[name="csrfmiddlewaretoken"]');
        const error = menu.querySelector('.wine-notifications-error');
        if (!token) {
            error.textContent = 'La protection de la session est indisponible. Rechargez la page.';
            error.hidden = false;
            return;
        }

        button.disabled = true;
        error.hidden = true;
        try {
            const response = await fetch(menu.dataset.actionUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': token.value,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    action: action,
                    key: row ? row.dataset.notificationKey : undefined
                })
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || 'Impossible de mettre à jour la notification.');
            }

            if (action === 'dismiss' && row) {
                row.remove();
            } else if (action === 'read_all') {
                const states = new Map(result.items.map(function (item) {
                    return [item.key, item.etat];
                }));
                menu.querySelectorAll('.wine-notification-row').forEach(function (item) {
                    if (states.has(item.dataset.notificationKey)) {
                        updateRowState(item, states.get(item.dataset.notificationKey) === 'NON_LUE' ? 'unread' : 'read');
                    }
                });
            } else if (row) {
                updateRowState(row, action === 'read' ? 'read' : 'unread');
            }
            updateUnreadCount(result.unread_count);
            applyFilter();
            showEmptyMessage();
        } catch (requestError) {
            error.textContent = requestError.message || 'Une erreur est survenue. Réessayez.';
            error.hidden = false;
        } finally {
            button.disabled = false;
        }
    }

    trigger.addEventListener('click', function () {
        const opening = menu.hidden;
        menu.hidden = !opening;
        trigger.setAttribute('aria-expanded', String(opening));
        root.classList.toggle('show', opening);
    });

    menu.addEventListener('click', function (event) {
        const filter = event.target.closest('[data-notification-filter]');
        if (filter) {
            currentFilter = filter.dataset.notificationFilter;
            applyFilter();
            return;
        }
        const action = event.target.closest('[data-notification-action]');
        if (action) performAction(action);
    });

    document.addEventListener('click', function (event) {
        if (!root.contains(event.target)) closeMenu();
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !menu.hidden) {
            closeMenu();
            trigger.focus();
        }
    });

    applyFilter();
})();
