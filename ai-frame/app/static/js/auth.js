/**
 * Authentication functionality
 */

import { api } from './api.js';
import { debugLog, debugError } from './debug-flags.js';

/**
 * Check if user is authenticated
 */
export async function checkAuth() {
    try {
        const result = await api('/api/auth/me');
        debugLog('AUTH', 'Auth check:', result);
        return result;
    } catch (e) {
        debugError('AUTH', 'Auth check failed:', e);
        return { logged_in: false };
    }
}

/**
 * Login user
 */
export async function login(username, password) {
    debugLog('AUTH', 'Attempting login for:', username);
    const result = await api('/api/auth/login', {
        method: 'POST',
        body: { username, password }
    });
    debugLog('AUTH', 'Login successful:', result.username);
    return result;
}

/**
 * Register new user
 */
export async function register(username, password, displayName) {
    debugLog('AUTH', 'Registering user:', username);
    const result = await api('/api/auth/register', {
        method: 'POST',
        body: { username, password, display_name: displayName }
    });
    debugLog('AUTH', 'Registration successful:', result.username);
    return result;
}

/**
 * Logout user
 */
export async function logout() {
    debugLog('AUTH', 'Logging out');
    await api('/api/auth/logout', { method: 'POST' });
}

/**
 * Check if any users exist
 */
export async function hasUsers() {
    const result = await api('/api/auth/has-users');
    return result.has_users;
}
