/**
 * API utilities
 */

import { debugLog, debugError } from './debug-flags.js';

// #region agent log
/** @param {Record<string, unknown>} data */
function _agentApiDbg(data) {
    fetch('http://127.0.0.1:7650/ingest/1f0f68f7-585d-47f3-bf1e-99ae25aa7de0', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '55f014' },
        body: JSON.stringify({
            sessionId: '55f014',
            timestamp: Date.now(),
            ...data,
        }),
    }).catch(() => {});
}
// #endregion

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
        // #region agent log
        if (isSettingsPatch) {
            _agentApiDbg({
                location: 'api.js:pre-fetch',
                message: 'about to fetch PATCH /api/settings',
                hypothesisId: 'H2',
                data: { t: Date.now() },
            });
        }
        // #endregion
        const response = await fetch(url, config);
        // #region agent log
        if (isSettingsPatch) {
            _agentApiDbg({
                location: 'api.js:post-fetch',
                message: 'fetch returned (headers received)',
                hypothesisId: 'H2',
                data: { status: response.status, ok: response.ok, t: Date.now() },
            });
        }
        // #endregion

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            // #region agent log
            if (isSettingsPatch) {
                _agentApiDbg({
                    location: 'api.js:response-not-ok',
                    message: 'PATCH /api/settings failed',
                    hypothesisId: 'H2',
                    data: {
                        status: response.status,
                        detail:
                            typeof error.detail === 'string'
                                ? error.detail
                                : JSON.stringify(error.detail || error).slice(0, 500),
                    },
                });
            }
            // #endregion
            throw new Error(error.detail || error.message || 'Request failed');
        }

        // #region agent log
        if (isSettingsPatch) {
            _agentApiDbg({
                location: 'api.js:response-ok',
                message: 'PATCH /api/settings ok (before body json)',
                hypothesisId: 'H2',
                data: { status: response.status },
            });
        }
        // #endregion

        const bodyJson = await response.json();
        // #region agent log
        if (isSettingsPatch) {
            _agentApiDbg({
                location: 'api.js:post-json',
                message: 'PATCH /api/settings body parsed',
                hypothesisId: 'H2',
                data: {
                    hasToggle: Object.prototype.hasOwnProperty.call(bodyJson, 'dictation_hotkey_toggle'),
                },
            });
        }
        // #endregion
        return bodyJson;
    } catch (e) {
        debugError('API', `Error: ${e.message}`);
        // #region agent log
        if (isSettingsPatch) {
            _agentApiDbg({
                location: 'api.js:catch',
                message: 'PATCH /api/settings network or throw',
                hypothesisId: 'H2',
                data: { errMessage: (e && e.message) || String(e) },
            });
        }
        // #endregion
        throw e;
    }
}
