/**
 * Notification system — SSE push (no polling).
 */

import { api } from './api.js';
import { debugLog, debugError, debugWarn, serverLog } from './debug-flags.js';

let sse = null;
let notificationsAbortController = null;

export function cancelNotificationsFetch(reason = 'manual') {
    if (!notificationsAbortController) return;
    try {
        notificationsAbortController.abort();
    } catch (_e) {}
    notificationsAbortController = null;
    debugWarn('NOTIFICATIONS', `notifications fetch aborted (${reason})`);
    serverLog('warn', '[NOTIFICATIONS] fetch aborted', { reason });
    // #region agent log
    fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'notifications.js:cancelNotificationsFetch',message:'notifications fetch aborted',data:{reason},timestamp:Date.now(),runId:'frontend-logout',hypothesisId:'H_LOGOUT'})}).catch(()=>{});
    // #endregion
}

/**
 * Fetch notifications and update UI
 */
export async function loadNotifications() {
    try {
        if (notificationsAbortController) {
            cancelNotificationsFetch('superseded');
        }
        notificationsAbortController = new AbortController();
        const startedAt = performance.now();
        const hangTimer = setTimeout(() => {
            debugWarn('HANG', 'notifications load pending after 5s');
        }, 5000);
        const result = await api('/api/notifications', { signal: notificationsAbortController.signal });
        clearTimeout(hangTimer);
        debugLog('HANG', `notifications load ok (${Math.round(performance.now() - startedAt)}ms)`);
        debugLog('NOTIFICATIONS', 'Loaded notifications:', result.notifications.length);

        const undismissed = result.notifications.filter((n) => !n.dismissed);

        if (undismissed.length > 0) {
            showNotificationBanner(undismissed[0], undismissed.length);
        } else {
            hideNotificationBanner();
        }

        return result.notifications;
    } catch (e) {
        if (e?.name === 'AbortError') {
            debugWarn('NOTIFICATIONS', 'notifications load aborted');
            return [];
        }
        debugError('NOTIFICATIONS', 'Failed to load:', e);
        debugError('HANG', 'notifications load failed', e?.message || e);
        return [];
    } finally {
        notificationsAbortController = null;
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
    serverLog('info', '[SSE] notifications stream created', { url: '/api/notifications/stream' });
    sse.addEventListener('open', () => {
        debugLog('HANG', 'notifications SSE open');
        debugLog('NOTIFICATIONS', 'SSE connected');
        serverLog('info', '[SSE] notifications open');
        loadNotifications();
    });
    sse.addEventListener('notifications', () => {
        loadNotifications();
    });
    sse.addEventListener('error', (event) => {
        debugWarn('NOTIFICATIONS', 'SSE connection error');
        debugWarn('HANG', 'notifications SSE error');
        serverLog('error', '[SSE] notifications error', {
            readyState: sse?.readyState,
            type: event?.type,
        });
    });
}

/**
 * Close notification SSE.
 */
export function stopNotificationStream() {
    if (sse) {
        sse.close();
        sse = null;
        debugLog('HANG', 'notifications SSE closed');
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
