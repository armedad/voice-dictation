/**
 * Authentication functionality
 */

import { api } from './api.js';
import { debugLog, debugError, serverLog } from './debug-flags.js';

/**
 * Check if user is authenticated
 */
export async function checkAuth() {
    try {
        debugLog('HANG', 'auth check start');
        const result = await api('/api/auth/me');
        debugLog('AUTH', 'Auth check:', result);
        debugLog('HANG', 'auth check done');
        return result;
    } catch (e) {
        debugError('AUTH', 'Auth check failed:', e);
        debugError('HANG', 'auth check failed', e?.message || e);
        return { logged_in: false };
    }
}

/**
 * Login user
 */
export async function login(username, password) {
    debugLog('AUTH', 'Attempting login for:', username);
    debugLog('HANG', 'login start');
    const result = await api('/api/auth/login', {
        method: 'POST',
        body: { username, password }
    });
    debugLog('AUTH', 'Login successful:', result.username);
    debugLog('HANG', 'login done');
    return result;
}

/**
 * Register new user
 */
export async function register(username, password, displayName) {
    debugLog('AUTH', 'Registering user:', username);
    debugLog('HANG', 'register start');
    const result = await api('/api/auth/register', {
        method: 'POST',
        body: { username, password, display_name: displayName }
    });
    debugLog('AUTH', 'Registration successful:', result.username);
    debugLog('HANG', 'register done');
    return result;
}

/**
 * Logout user
 */
export async function logout() {
    debugLog('AUTH', 'Logging out');
    debugLog('HANG', 'logout start');
    // #region agent log
    fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'auth.js:logout',message:'logout start',data:{visibility:document.visibilityState,activeElement:document.activeElement?.id||document.activeElement?.tagName||null,onLine:navigator.onLine,apiInFlight:window.__twimApiInFlight||null},timestamp:Date.now(),runId:'frontend-logout',hypothesisId:'H_LOGOUT'})}).catch(()=>{});
    // #endregion
    serverLog('info', '[LOGOUT] logout called', {
        visibility: document.visibilityState,
        activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
        onLine: navigator.onLine,
        apiInFlight: window.__twimApiInFlight || null,
    });
    await api('/api/auth/logout', { method: 'POST' });
    debugLog('HANG', 'logout done');
    // #region agent log
    fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'auth.js:logout',message:'logout done',data:{visibility:document.visibilityState,apiInFlight:window.__twimApiInFlight||null},timestamp:Date.now(),runId:'frontend-logout',hypothesisId:'H_LOGOUT'})}).catch(()=>{});
    // #endregion
    serverLog('info', '[LOGOUT] logout done', {
        visibility: document.visibilityState,
        apiInFlight: window.__twimApiInFlight || null,
    });
}

/**
 * Check if any users exist
 */
export async function hasUsers() {
    debugLog('HANG', 'has-users start');
    const result = await api('/api/auth/has-users');
    debugLog('HANG', 'has-users done');
    return result.has_users;
}
