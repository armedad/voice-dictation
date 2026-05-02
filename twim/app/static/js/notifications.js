/**
 * Notification system — SSE push (no polling).
 */

import { api } from './api.js';
import { debugLog, debugError, debugWarn } from './debug-flags.js';

let sse = null;

/**
 * Fetch notifications and update UI
 */
export async function loadNotifications() {
    try {
        const result = await api('/api/notifications');
        debugLog('NOTIFICATIONS', 'Loaded notifications:', result.notifications.length);

        const undismissed = result.notifications.filter((n) => !n.dismissed);

        if (undismissed.length > 0) {
            showNotificationBanner(undismissed[0], undismissed.length);
        } else {
            hideNotificationBanner();
        }

        return result.notifications;
    } catch (e) {
        debugError('NOTIFICATIONS', 'Failed to load:', e);
        return [];
    }
}

/**
 * Show notification banner
 */
function showNotificationBanner(notification, totalCount) {
    const banner = document.getElementById('notification-banner');
    const message = document.getElementById('notification-message');
    const count = document.getElementById('notification-count');
    const dismissAll = document.getElementById('notification-dismiss-all');

    if (!banner || !message) return;

    banner.dataset.notificationId = notification.id;
    message.textContent = notification.message;

    if (totalCount > 1) {
        count.textContent = `(+${totalCount - 1} more)`;
        count.style.display = '';
        dismissAll.style.display = '';
    } else {
        count.style.display = 'none';
        dismissAll.style.display = 'none';
    }

    banner.classList.add('show');
}

/**
 * Hide notification banner
 */
export function hideNotificationBanner() {
    const banner = document.getElementById('notification-banner');
    if (banner) {
        banner.classList.remove('show');
    }
}

/**
 * Dismiss a notification
 */
export async function dismissNotification(notificationId) {
    try {
        await api(`/api/notifications/${notificationId}/dismiss`, { method: 'POST' });
        debugLog('NOTIFICATIONS', 'Dismissed:', notificationId);
        await loadNotifications();
    } catch (e) {
        debugError('NOTIFICATIONS', 'Failed to dismiss:', e);
    }
}

/**
 * Dismiss all notifications
 */
export async function dismissAllNotifications() {
    try {
        await api('/api/notifications/dismiss-all', { method: 'POST' });
        debugLog('NOTIFICATIONS', 'Dismissed all');
        await loadNotifications();
    } catch (e) {
        debugError('NOTIFICATIONS', 'Failed to dismiss all:', e);
    }
}

/**
 * Subscribe to server push for notification changes.
 */
export function startNotificationStream() {
    if (sse) return;

    sse = new EventSource('/api/notifications/stream');
    sse.addEventListener('open', () => {
        debugLog('NOTIFICATIONS', 'SSE connected');
        loadNotifications();
    });
    sse.addEventListener('notifications', () => {
        loadNotifications();
    });
    sse.addEventListener('error', () => {
        debugWarn('NOTIFICATIONS', 'SSE connection error');
    });
}

/**
 * Close notification SSE.
 */
export function stopNotificationStream() {
    if (sse) {
        sse.close();
        sse = null;
        debugLog('NOTIFICATIONS', 'SSE closed');
    }
}

/**
 * Initialize notification event listeners
 */
export function initNotifications() {
    const dismissBtn = document.getElementById('notification-dismiss');
    const dismissAllBtn = document.getElementById('notification-dismiss-all');
    const banner = document.getElementById('notification-banner');

    if (dismissBtn) {
        dismissBtn.addEventListener('click', async () => {
            const notifId = banner?.dataset?.notificationId;
            if (notifId) {
                await dismissNotification(notifId);
            }
        });
    }

    if (dismissAllBtn) {
        dismissAllBtn.addEventListener('click', async () => {
            await dismissAllNotifications();
        });
    }
}
