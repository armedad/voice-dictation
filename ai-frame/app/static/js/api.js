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
    
    try {
        const response = await fetch(url, config);
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(error.detail || error.message || 'Request failed');
        }
        
        return await response.json();
    } catch (e) {
        debugError('API', `Error: ${e.message}`);
        throw e;
    }
}
