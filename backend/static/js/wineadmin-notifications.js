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
        let visibleCount = 0;
        menu.querySelectorAll('.wine-notification-row').forEach(function (row) {
            const state = row.dataset.notificationState;
            const visible = currentFilter === 'all'
                || (currentFilter === 'unread' && state === 'unread')
                || (currentFilter === 'read' && state === 'read')
                || (currentFilter === 'message' && row.dataset.notificationKind === 'message');
            row.hidden = !visible;
            if (visible) visibleCount += 1;
        });
        menu.querySelectorAll('[data-notification-filter]').forEach(function (button) {
            button.setAttribute(
                'aria-pressed',
                String(button.dataset.notificationFilter === currentFilter)
            );
        });
        const filteredEmpty = menu.querySelector('.wine-notifications-filter-empty');
        const hasRows = Boolean(menu.querySelector('.wine-notification-row'));
        if (hasRows && visibleCount === 0) {
            if (!filteredEmpty) {
                const message = document.createElement('p');
                message.className = 'wine-notifications-empty wine-notifications-filter-empty';
                message.textContent = currentFilter === 'message'
                    ? 'Aucun message client.'
                    : currentFilter === 'unread'
                        ? 'Aucune notification non lue.'
                        : 'Aucune notification lue.';
                const error = menu.querySelector('.wine-notifications-error');
                menu.insertBefore(message, error);
            }
        } else if (filteredEmpty) {
            filteredEmpty.remove();
        }
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

    function actionButton(action, icon, label) {
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.notificationAction = action;
        button.title = label;
        button.setAttribute('aria-label', label);
        const glyph = document.createElement('i');
        glyph.className = 'fas ' + icon;
        glyph.setAttribute('aria-hidden', 'true');
        button.appendChild(glyph);
        return button;
    }

    function renderNotifications(items) {
        const error = menu.querySelector('.wine-notifications-error');
        const empty = document.getElementById('wine-notifications-empty');
        let list = document.getElementById('wine-notifications-list');
        if (!items.length) {
            if (list) list.remove();
            if (!empty) {
                const message = document.createElement('p');
                message.id = 'wine-notifications-empty';
                message.className = 'wine-notifications-empty';
                const icon = document.createElement('i');
                icon.className = 'fas fa-circle-check';
                icon.setAttribute('aria-hidden', 'true');
                message.append(icon, document.createTextNode(' Aucune notification pour le moment.'));
                menu.insertBefore(message, error);
            }
            return;
        }

        if (empty) empty.remove();
        if (!list) {
            list = document.createElement('ul');
            list.id = 'wine-notifications-list';
            list.className = 'wine-notifications-list';
            menu.insertBefore(list, error);
        }

        list.replaceChildren();
        items.forEach(function (item) {
            const row = document.createElement('li');
            const unread = item.non_lue === true;
            row.className = 'wine-notification-row' + (unread ? ' is-unread' : '');
            row.dataset.notificationKey = item.key;
            row.dataset.notificationKind = item.category || '';
            row.dataset.notificationState = unread ? 'unread' : 'read';

            const card = document.createElement('div');
            card.className = 'wine-notification-item is-' + item.level;
            const icon = document.createElement('span');
            icon.className = 'wine-notification-icon';
            const glyph = document.createElement('i');
            glyph.className = 'fas ' + item.icon;
            glyph.setAttribute('aria-hidden', 'true');
            icon.appendChild(glyph);

            const copy = document.createElement('span');
            copy.className = 'wine-notification-copy';
            const title = document.createElement('a');
            title.textContent = item.title;
            if (typeof item.url === 'string' && item.url.startsWith('/') && !item.url.startsWith('//')) {
                title.href = item.url;
            }
            const summary = document.createElement('span');
            summary.textContent = item.summary;
            copy.append(title, summary);

            if (item.action_label && title.href) {
                const reply = document.createElement('a');
                reply.className = 'wine-notification-reply';
                reply.href = title.href;
                const replyIcon = document.createElement('i');
                replyIcon.className = 'fas fa-reply';
                replyIcon.setAttribute('aria-hidden', 'true');
                reply.append(replyIcon, document.createTextNode(' ' + item.action_label));
                copy.appendChild(reply);
            }

            const actions = document.createElement('div');
            actions.className = 'wine-notification-actions';
            actions.append(
                actionButton(
                    unread ? 'read' : 'unread',
                    unread ? 'fa-check' : 'fa-envelope',
                    unread ? 'Marquer comme lue' : 'Marquer comme non lue'
                ),
                actionButton('dismiss', 'fa-trash-can', 'Masquer cette notification')
            );
            card.append(icon, copy, actions);
            row.appendChild(card);
            list.appendChild(row);
        });
        applyFilter();
    }

    let refreshInProgress = false;
    async function refreshNotifications() {
        if (refreshInProgress) return;
        refreshInProgress = true;
        const button = menu.querySelector('[data-notification-refresh]');
        const error = menu.querySelector('.wine-notifications-error');
        if (button) {
            button.disabled = true;
            button.classList.add('is-refreshing');
        }
        try {
            const response = await fetch(menu.dataset.actionUrl, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const result = await response.json();
            if (!response.ok || !result.success || !Array.isArray(result.items)) {
                throw new Error(result.error || 'Impossible d’actualiser les notifications.');
            }
            renderNotifications(result.items);
            updateUnreadCount(result.unread_count);
            if (error) error.hidden = true;
        } catch (requestError) {
            if (error) {
                error.textContent = requestError.message || 'Impossible d’actualiser les notifications.';
                error.hidden = false;
            }
        } finally {
            refreshInProgress = false;
            if (button) {
                button.disabled = false;
                button.classList.remove('is-refreshing');
            }
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

            if (Array.isArray(result.items)) {
                renderNotifications(result.items);
            }
            updateUnreadCount(result.unread_count);
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
        if (opening) refreshNotifications();
    });

    menu.addEventListener('click', function (event) {
        const target = event.target instanceof Element ? event.target : null;
        if (!target) return;
        const refresh = target.closest('[data-notification-refresh]');
        if (refresh) {
            refreshNotifications();
            return;
        }
        const filter = target.closest('[data-notification-filter]');
        if (filter) {
            currentFilter = filter.dataset.notificationFilter;
            applyFilter();
            return;
        }
        const action = target.closest('[data-notification-action]');
        if (action) performAction(action);
    });

    window.setInterval(function () {
        if (document.visibilityState === 'visible' && !document.hidden) refreshNotifications();
    }, 60000);

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
