/**
 * API utilities
 */

import { debugLog, debugError } from './debug-flags.js';

/**
 * Make an API request
 */
export async function api(endpoint, options = {}) {
    const url = endpoint.startsWith('/') ? endpoint : `/api/${endpoint}`;
    
    const config = {
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        ...options
    };
    
    if (options.body && typeof options.body === 'object') {
        config.body = JSON.stringify(options.body);
    }
    
    debugLog('API', `${config.method || 'GET'} ${url}`);
    const method = config.method || 'GET';
    const isSettingsPatch = method === 'PATCH' && url === '/api/settings';

    try {
        if (isSettingsPatch) {
            debugLog('API', 'about to fetch PATCH /api/settings', { t: Date.now() });
        }
        const response = await fetch(url, config);
        if (isSettingsPatch) {
            debugLog('API', 'fetch returned (headers received)', {
                status: response.status,
                ok: response.ok,
                t: Date.now(),
            });
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            if (isSettingsPatch) {
                debugError('API', 'PATCH /api/settings failed', {
                    status: response.status,
                    detail:
                        typeof error.detail === 'string'
                            ? error.detail
                            : JSON.stringify(error.detail || error).slice(0, 500),
                });
            }
            throw new Error(error.detail || error.message || 'Request failed');
        }

        if (isSettingsPatch) {
            debugLog('API', 'PATCH /api/settings ok (before body json)', {
                status: response.status,
            });
        }

        const bodyJson = await response.json();
        if (isSettingsPatch) {
            debugLog('API', 'PATCH /api/settings body parsed', {
                hasToggle: Object.prototype.hasOwnProperty.call(bodyJson, 'dictation_hotkey_toggle'),
            });
        }
        return bodyJson;
    } catch (e) {
        debugError('API', `Error: ${e.message}`);
        if (isSettingsPatch) {
            debugError('API', 'PATCH /api/settings network or throw', {
                errMessage: (e && e.message) || String(e),
            });
        }
        throw e;
    }
}
