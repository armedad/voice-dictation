/**
 * API utilities
 */

import { debugLog, debugError, debugWarn, serverLog } from './debug-flags.js';

let inFlightCount = 0;
let loginInFlightCount = 0;
let logoutInFlightCount = 0;
const inFlightRequests = new Map();

function ensureTabId() {
    if (typeof window === 'undefined') return 'server';
    if (window.__twimTabId) return window.__twimTabId;
    let stored = null;
    try {
        stored = sessionStorage.getItem('twim_tab_id');
    } catch (_e) {
        stored = null;
    }
    if (!stored) {
        stored = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
        try {
            sessionStorage.setItem('twim_tab_id', stored);
        } catch (_e) {
            // ignore
        }
    }
    window.__twimTabId = stored;
    return stored;
}

function updateInFlight(url, delta) {
    inFlightCount += delta;
    if (url.includes('/api/auth/login')) {
        loginInFlightCount += delta;
    }
    if (url.includes('/api/auth/logout')) {
        logoutInFlightCount += delta;
    }
    if (typeof window !== 'undefined') {
        window.__twimApiInFlight = {
            total: inFlightCount,
            login: loginInFlightCount,
            logout: logoutInFlightCount,
        };
    }
}

function refreshInFlightSnapshot() {
    if (typeof window === 'undefined') return;
    const now = performance.now();
    const byUrl = {};
    let oldestMs = 0;
    const sample = [];
    for (const [id, req] of inFlightRequests.entries()) {
        const ageMs = Math.round(now - req.startedAt);
        oldestMs = Math.max(oldestMs, ageMs);
        byUrl[req.url] = (byUrl[req.url] || 0) + 1;
        if (sample.length < 5) {
            sample.push({ id, url: req.url, method: req.method, ageMs });
        }
    }
    window.__twimApiInFlightDetails = {
        tabId: window.__twimTabId || null,
        total: inFlightCount,
        login: loginInFlightCount,
        logout: logoutInFlightCount,
        oldestMs,
        byUrl,
        sample,
    };
}

/**
 * Make an API request
 */
export async function api(endpoint, options = {}) {
    const url = endpoint.startsWith('/') ? endpoint : `/api/${endpoint}`;
    const startedAt = performance.now();
    const method = options.method || 'GET';
    const isLogin = url.includes('/api/auth/login');
    const isLogout = url.includes('/api/auth/logout');
    const requestId = `${Date.now()}-${Math.round(performance.now())}`;
    const tabId = ensureTabId();
    inFlightRequests.set(requestId, { url, method, startedAt, tabId });
    const hangTimer = setTimeout(() => {
        debugWarn('HANG', `API ${method} ${url} still pending after 5s`);
        if (isLogin) {
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'login request pending 5s',data:{url,method,requestId,inFlightCount,loginInFlightCount,visibility:document.visibilityState,onLine:navigator.onLine},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_CONNPOOL'})}).catch(()=>{});
            // #endregion
            serverLog('warn', '[LOGIN] api pending 5s', {
                url,
                method,
                requestId,
                inFlightCount,
                loginInFlightCount,
                visibility: document.visibilityState,
                onLine: navigator.onLine,
            });
        }
        if (isLogout) {
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'logout request pending 5s',data:{url,method,requestId,inFlightCount,logoutInFlightCount,visibility:document.visibilityState,onLine:navigator.onLine,inFlightDetails:window.__twimApiInFlightDetails||null},timestamp:Date.now(),runId:'frontend-logout',hypothesisId:'H_LOGOUT'})}).catch(()=>{});
            // #endregion
            serverLog('warn', '[LOGOUT] api pending 5s', {
                url,
                method,
                requestId,
                inFlightCount,
                logoutInFlightCount,
                visibility: document.visibilityState,
                onLine: navigator.onLine,
                inFlightDetails: window.__twimApiInFlightDetails || null,
                tabId,
            });
        }
    }, 5000);
    
    const config = {
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-Twim-Tab-Id': tabId,
            ...options.headers
        },
        ...options
    };
    
    if (options.body && typeof options.body === 'object') {
        config.body = JSON.stringify(options.body);
    }
    
    debugLog('API', `${method} ${url}`);
    updateInFlight(url, 1);
    refreshInFlightSnapshot();
    if (isLogin) {
        serverLog('info', '[LOGIN] api request start', {
            method,
            url,
            origin: window.location.origin,
        });
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'login request start',data:{url,method,requestId,inFlightCount,loginInFlightCount,visibility:document.visibilityState,onLine:navigator.onLine},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_CONNPOOL'})}).catch(()=>{});
        // #endregion
    }
    if (isLogout) {
        serverLog('info', '[LOGOUT] api request start', {
            method,
            url,
            origin: window.location.origin,
            requestId,
            inFlightCount,
            logoutInFlightCount,
            visibility: document.visibilityState,
            inFlightDetails: window.__twimApiInFlightDetails || null,
            tabId,
        });
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'logout request start',data:{url,method,requestId,inFlightCount,logoutInFlightCount,visibility:document.visibilityState,onLine:navigator.onLine,inFlightDetails:window.__twimApiInFlightDetails||null},timestamp:Date.now(),runId:'frontend-logout',hypothesisId:'H_LOGOUT'})}).catch(()=>{});
        // #endregion
    }
    debugLog('HANG', `API ${method} ${url} start`);
    // #region agent log
    try {
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'api request start',data:{url,method,origin:window.location.origin},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_LOGIN'})}).catch(()=>{});
    } catch (_e) {}
    // #endregion
    
    try {
        const response = await fetch(url, config);
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(error.detail || error.message || 'Request failed');
        }
        
        const payload = await response.json();
        // #region agent log
        try {
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'api request success',data:{url,method,status:response.status},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_LOGIN'})}).catch(()=>{});
        } catch (_e) {}
        // #endregion
        debugLog(
            'HANG',
            `API ${method} ${url} done (${Math.round(performance.now() - startedAt)}ms)`
        );
        if (isLogin) {
            serverLog('info', '[LOGIN] api request ok', {
                method,
                url,
                status: response.status,
            });
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'login request success',data:{url,method,requestId,status:response.status,inFlightCount,loginInFlightCount},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_CONNPOOL'})}).catch(()=>{});
            // #endregion
        }
        if (isLogout) {
            serverLog('info', '[LOGOUT] api request ok', {
                method,
                url,
                status: response.status,
                requestId,
                inFlightCount,
                logoutInFlightCount,
                inFlightDetails: window.__twimApiInFlightDetails || null,
                tabId,
            });
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'logout request success',data:{url,method,requestId,status:response.status,inFlightCount,logoutInFlightCount,inFlightDetails:window.__twimApiInFlightDetails||null},timestamp:Date.now(),runId:'frontend-logout',hypothesisId:'H_LOGOUT'})}).catch(()=>{});
            // #endregion
        }
        return payload;
    } catch (e) {
        debugError('API', `Error: ${e.message}`);
        debugError(
            'HANG',
            `API ${method} ${url} failed (${Math.round(performance.now() - startedAt)}ms): ${
                e.message || e
            }`
        );
        // #region agent log
        try {
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'api request failed',data:{url,method,error:e?.message||String(e)},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_LOGIN'})}).catch(()=>{});
        } catch (_e) {}
        // #endregion
        if (isLogin) {
            serverLog('error', '[LOGIN] api request failed', {
                method,
                url,
                error: e?.message || String(e),
            });
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'login request failed',data:{url,method,requestId,error:e?.message||String(e),inFlightCount,loginInFlightCount,visibility:document.visibilityState},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_CONNPOOL'})}).catch(()=>{});
            // #endregion
        }
        if (isLogout) {
            serverLog('error', '[LOGOUT] api request failed', {
                method,
                url,
                error: e?.message || String(e),
                requestId,
                inFlightCount,
                logoutInFlightCount,
                visibility: document.visibilityState,
                inFlightDetails: window.__twimApiInFlightDetails || null,
                tabId,
            });
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'api.js:api',message:'logout request failed',data:{url,method,requestId,error:e?.message||String(e),inFlightCount,logoutInFlightCount,visibility:document.visibilityState,inFlightDetails:window.__twimApiInFlightDetails||null},timestamp:Date.now(),runId:'frontend-logout',hypothesisId:'H_LOGOUT'})}).catch(()=>{});
            // #endregion
        }
        throw e;
    } finally {
        inFlightRequests.delete(requestId);
        updateInFlight(url, -1);
        refreshInFlightSnapshot();
        clearTimeout(hangTimer);
    }
}
