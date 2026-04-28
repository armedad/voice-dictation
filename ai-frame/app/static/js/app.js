/**
 * ai-frame - Main Application Entry Point
 */

import { debugLog, debugWarn, serverLog, debugError } from './debug-flags.js';
import { api } from './api.js';
import { checkAuth, login, register, logout, hasUsers } from './auth.js';
import {
    loadSettings,
    loadModels,
    loadSpeechModels,
    initSettings,
    refreshDictationInputDevices,
} from './settings.js';
import { initChat, createConversation } from './chat.js';
import { initNotifications, startNotificationStream, stopNotificationStream, cancelNotificationsFetch } from './notifications.js';
import { startDictationEvents, stopDictationEvents } from './dictation-events.js';
import {
    initContextTab,
    refreshDictationLastContext,
    syncContextTabFromSettings,
} from './context-tab.js';

// Log on module load
serverLog('info', '[APP] ai-frame loaded at ' + new Date().toISOString());

// App state
const state = {
    currentUser: null,
    isLoggedIn: false
};

/**
 * Show login screen
 */
function showLoginScreen() {
    debugLog('HANG', 'showLoginScreen');
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
    stopNotificationStream();
    stopDictationEvents();
}

/**
 * Show main app
 */
function showApp() {
    debugLog('HANG', 'showApp');
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    startNotificationStream();
    startDictationEvents();
}

/**
 * Update user display
 */
function updateUserDisplay() {
    const displayName = document.getElementById('user-display-name');
    if (displayName && state.currentUser) {
        displayName.textContent = state.currentUser.display_name || state.currentUser.username;
    }
}

/**
 * Handle login form
 */
async function handleLogin(e) {
    e.preventDefault();
    debugLog('HANG', 'Login submit');
    
    // #region agent log
    fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:handleLogin',message:'login handler entry',data:{visibility:document.visibilityState,activeElement:document.activeElement?.id||document.activeElement?.tagName||null,onLine:navigator.onLine,apiInFlight:window.__twimApiInFlight||null},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_CONNPOOL'})}).catch(()=>{});
    // #endregion
    serverLog('info', '[LOGIN] handler entry', {
        visibility: document.visibilityState,
        activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
        onLine: navigator.onLine,
        apiInFlight: window.__twimApiInFlight || null,
    });

    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    const loginBtn = document.getElementById('login-btn');
    const defaultLabel = loginBtn?.textContent || 'Log In';
    if (errorEl) errorEl.textContent = '';
    if (loginBtn) {
        loginBtn.disabled = true;
        loginBtn.textContent = 'Logging in...';
    }
    
    // #region agent log
    fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:handleLogin',message:'login submit',data:{host:window.location.host,origin:window.location.origin,usernameLen:username.length,hasPassword:password.length>0},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_LOGIN'})}).catch(()=>{});
    // #endregion
    serverLog('info', '[LOGIN] submit clicked', {
        host: window.location.host,
        origin: window.location.origin,
        usernameLen: username.length,
        hasPassword: password.length > 0,
    });
    try {
        const result = await Promise.race([
            login(username, password),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Login timed out')), 12000)
            ),
        ]);
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:handleLogin',message:'login success',data:{username:result?.username||null},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_LOGIN'})}).catch(()=>{});
        // #endregion
        state.currentUser = result;
        state.isLoggedIn = true;
        updateUserDisplay();
        try {
            await initializeApp();
            showApp();
            debugLog('HANG', 'app ready');
        } catch (err) {
            debugError('HANG', 'initializeApp failed after login', err?.message || err);
            throw err;
        }
    } catch (e) {
        debugError('HANG', 'login failed', e?.message || e);
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:handleLogin',message:'login failed timeout',data:{error:e?.message||String(e),apiInFlight:window.__twimApiInFlight||null,visibility:document.visibilityState},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_CONNPOOL'})}).catch(()=>{});
        // #endregion
        serverLog('error', '[LOGIN] login failed', {
            error: e?.message || String(e),
            apiInFlight: window.__twimApiInFlight || null,
            visibility: document.visibilityState,
        });
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:handleLogin',message:'login failed',data:{error:e?.message||String(e),host:window.location.host},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_LOGIN'})}).catch(()=>{});
        // #endregion
        errorEl.textContent = e.message || 'Login failed';
        if (loginBtn) {
            loginBtn.disabled = false;
            loginBtn.textContent = defaultLabel;
        }
    }
}

/**
 * Handle register form
 */
async function handleRegister(e) {
    e.preventDefault();
    debugLog('HANG', 'Register submit');
    
    const username = document.getElementById('register-username').value;
    const displayName = document.getElementById('register-display-name').value;
    const password = document.getElementById('register-password').value;
    const confirmPassword = document.getElementById('register-password-confirm').value;
    const errorEl = document.getElementById('login-error');
    const registerBtn = document.getElementById('register-btn');
    const defaultLabel = registerBtn?.textContent || 'Create Account';
    if (errorEl) errorEl.textContent = '';
    if (registerBtn) {
        registerBtn.disabled = true;
        registerBtn.textContent = 'Creating...';
    }
    
    if (password !== confirmPassword) {
        errorEl.textContent = 'Passwords do not match';
        if (registerBtn) {
            registerBtn.disabled = false;
            registerBtn.textContent = defaultLabel;
        }
        return;
    }
    
    try {
        const result = await Promise.race([
            register(username, password, displayName || username),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Registration timed out')), 12000)
            ),
        ]);
        state.currentUser = result;
        state.isLoggedIn = true;
        updateUserDisplay();
        try {
            await initializeApp();
            showApp();
            debugLog('HANG', 'app ready');
        } catch (err) {
            debugError('HANG', 'initializeApp failed after register', err?.message || err);
            throw err;
        }
    } catch (e) {
        debugError('HANG', 'register failed', e?.message || e);
        errorEl.textContent = e.message || 'Registration failed';
        if (registerBtn) {
            registerBtn.disabled = false;
            registerBtn.textContent = defaultLabel;
        }
    }
}

/**
 * Handle logout
 */
async function handleLogout() {
    debugLog('HANG', 'Logout');
    cancelNotificationsFetch('logout');
    await logout();
    state.currentUser = null;
    state.isLoggedIn = false;
    showLoginScreen();
}

/**
 * Initialize app after login
 */
async function initializeApp() {
    debugLog('HANG', 'initializeApp start');
    await loadSettings();
    await loadModels();
    await loadSpeechModels();
    await refreshDictationInputDevices().catch((e) => debugWarn('APP', 'mic list refresh failed', e));
    await createConversation();
    await syncContextTabFromSettings();
    debugLog('HANG', 'initializeApp done');
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Login form
    document.getElementById('login-btn')?.addEventListener('click', handleLogin);
    const showPassword = document.getElementById('login-show-password');
    const loginPassword = document.getElementById('login-password');
    if (showPassword && loginPassword) {
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:login-show-password',message:'show password initialized',data:{found:true,initialType:loginPassword.type},timestamp:Date.now(),runId:'frontend-toggle',hypothesisId:'H_SHOWPASS'})}).catch(()=>{});
        // #endregion
        showPassword.addEventListener('change', () => {
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:login-show-password',message:'show password toggled',data:{checked:showPassword.checked,before:loginPassword.type},timestamp:Date.now(),runId:'frontend-toggle',hypothesisId:'H_SHOWPASS'})}).catch(()=>{});
            // #endregion
            loginPassword.type = showPassword.checked ? 'text' : 'password';
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:login-show-password',message:'show password type set',data:{after:loginPassword.type},timestamp:Date.now(),runId:'frontend-toggle',hypothesisId:'H_SHOWPASS'})}).catch(()=>{});
            // #endregion
        });
    } else {
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:login-show-password',message:'show password missing elements',data:{showPassword:!!showPassword,loginPassword:!!loginPassword},timestamp:Date.now(),runId:'frontend-toggle',hypothesisId:'H_SHOWPASS'})}).catch(()=>{});
        // #endregion
    }

    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:login-form',message:'login form submit listener attached',data:{},timestamp:Date.now(),runId:'frontend-login',hypothesisId:'H_LOGIN'})}).catch(()=>{});
        // #endregion
        loginForm.addEventListener('submit', (event) => {
            event.preventDefault();
            handleLogin(event);
        });
    }

    const loginPasswordInput = document.getElementById('login-password');
    if (loginPasswordInput) {
        loginPasswordInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                handleLogin(event);
            }
        });
    }
    document.getElementById('login-password')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleLogin(e);
    });
    
    // Register form
    document.getElementById('register-btn')?.addEventListener('click', handleRegister);
    
    // Toggle login/register
    document.getElementById('show-register-btn')?.addEventListener('click', () => {
        document.getElementById('login-form').style.display = 'none';
        document.getElementById('register-form').style.display = 'flex';
        document.getElementById('login-error').textContent = '';
    });
    
    document.getElementById('show-login-btn')?.addEventListener('click', () => {
        document.getElementById('login-form').style.display = 'flex';
        document.getElementById('register-form').style.display = 'none';
        document.getElementById('login-error').textContent = '';
    });
    
    // Logout
    document.getElementById('logout-btn')?.addEventListener('click', handleLogout);
    
    // User menu toggle
    const userBtn = document.getElementById('user-btn');
    const userDropdown = document.getElementById('user-dropdown');
    
    if (userBtn && userDropdown) {
        userBtn.addEventListener('click', () => {
            userDropdown.classList.toggle('show');
        });
        
        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!userBtn.contains(e.target) && !userDropdown.contains(e.target)) {
                userDropdown.classList.remove('show');
            }
        });
    }
    
    // New chat button
    document.getElementById('new-chat-btn')?.addEventListener('click', async () => {
        await createConversation();
    });

    const dictateBtn = document.getElementById('dictate-10s-btn');
    if (dictateBtn) {
        const defaultLabel = dictateBtn.textContent;
        /** True while a record-and-type request is in flight (second click cancels mic capture). */
        let dictateSessionActive = false;
        dictateBtn.addEventListener('click', async () => {
            debugLog('HANG', 'Dictate button click', { active: dictateSessionActive });
            if (dictateSessionActive) {
                try {
                    debugLog('DICTATION', 'POST /api/dictation/hotkey/cancel (stop recording)');
                    await api('dictation/hotkey/cancel', { method: 'POST', body: {} });
                    dictateBtn.textContent = 'Stopping…';
                } catch (e) {
                    debugWarn('DICTATION', 'hotkey/cancel failed:', e?.message || e);
                    alert(e.message || 'Could not stop dictation');
                }
                return;
            }
            dictateSessionActive = true;
            dictateBtn.textContent = 'Recording… (click to stop)';
            try {
                debugLog('DICTATION', 'POST /api/dictation/record-and-type starting');
                debugLog('HANG', 'record-and-type request start');
                const result = await api('dictation/record-and-type', {
                    method: 'POST',
                    body: {},
                });
                debugLog('DICTATION', 'POST /api/dictation/record-and-type finished', result);
                debugLog('HANG', 'record-and-type request done', result);
                if (result.cancelled) {
                    dictateBtn.textContent = 'Cancelled';
                } else if (result.skipped_empty) {
                    dictateBtn.textContent = 'No speech detected';
                } else {
                    await refreshDictationLastContext({ resetToLatest: true });
                    dictateBtn.textContent = 'Done';
                }
                setTimeout(() => {
                    dictateBtn.textContent = defaultLabel;
                }, 1500);
            } catch (e) {
                debugWarn('DICTATION', 'record-and-type failed:', e?.message || e);
                debugError('HANG', 'record-and-type request failed', e?.message || e);
                dictateBtn.textContent = defaultLabel;
                alert(e.message || 'Dictation failed');
            } finally {
                debugLog('HANG', 'record-and-type request finished finally');
                dictateSessionActive = false;
            }
        });
    }
}

function setupHangHeartbeat() {
    let beat = 0;
    let lastBeat = performance.now();
    setInterval(() => {
        beat += 1;
        debugLog('HANG', `heartbeat ${beat}`);
        const now = performance.now();
        const lag = now - lastBeat - 5000;
        if (lag > 250) {
            debugWarn('HANG', `event loop lag ${Math.round(lag)}ms`);
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:heartbeat',message:'event loop lag',data:{lagMs:Math.round(lag),visibility:document.visibilityState,apiInFlight:window.__twimApiInFlight||null,activeElement:document.activeElement?.id||document.activeElement?.tagName||null},timestamp:Date.now(),runId:'frontend-hang',hypothesisId:'H_EVENT_LOOP'})}).catch(()=>{});
            // #endregion
            serverLog('warn', '[HANG] event loop lag', {
                lagMs: Math.round(lag),
                visibility: document.visibilityState,
                apiInFlight: window.__twimApiInFlight || null,
                activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
            });
        }
        lastBeat = now;
    }, 5000);

    setInterval(() => {
        debugLog('HANG', 'runtime snapshot', {
            now: new Date().toISOString(),
            visibility: document.visibilityState,
            activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
        });
        if (window.__twimApiInFlightDetails) {
            // #region agent log
            fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:heartbeat',message:'inflight snapshot',data:{details:window.__twimApiInFlightDetails,visibility:document.visibilityState},timestamp:Date.now(),runId:'frontend-hang',hypothesisId:'H_CONNPOOL'})}).catch(()=>{});
            // #endregion
            serverLog('info', '[HANG] inflight snapshot', {
                details: window.__twimApiInFlightDetails,
                visibility: document.visibilityState,
            });
        }
        // #region agent log
        fetch('http://127.0.0.1:7313/ingest/bebe4c4e-4978-4271-b068-86f25a65a1d8',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'55f014'},body:JSON.stringify({sessionId:'55f014',location:'app.js:heartbeat',message:'runtime snapshot',data:{visibility:document.visibilityState,activeElement:document.activeElement?.id||document.activeElement?.tagName||null,apiInFlight:window.__twimApiInFlight||null},timestamp:Date.now(),runId:'frontend-hang',hypothesisId:'H_EVENT_LOOP'})}).catch(()=>{});
        // #endregion
        serverLog('info', '[HANG] runtime snapshot', {
            visibility: document.visibilityState,
            activeElement: document.activeElement?.id || document.activeElement?.tagName || null,
            apiInFlight: window.__twimApiInFlight || null,
        });
    }, 15000);
}

function setupGlobalErrorHandlers() {
    window.addEventListener('error', (event) => {
        debugError('HANG', 'window error', {
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno,
        });
    });
    window.addEventListener('unhandledrejection', (event) => {
        debugError('HANG', 'unhandled rejection', {
            reason: event.reason?.message || event.reason,
        });
    });
    document.addEventListener('visibilitychange', () => {
        debugLog('HANG', `visibility ${document.visibilityState}`);
    });
}

/**
 * Main entry point
 */
async function main() {
    debugLog('APP', 'Initializing ai-frame');
    debugLog('HANG', 'main entry');
    setupHangHeartbeat();
    setupGlobalErrorHandlers();
    
    // Setup UI
    setupEventListeners();
    initSettings();
    initContextTab();
    initChat();
    initNotifications();
    
    // Check authentication
    const auth = await checkAuth();
    
    if (auth.logged_in) {
        debugLog('HANG', 'auth logged in, initialize app');
        state.currentUser = auth;
        state.isLoggedIn = true;
        updateUserDisplay();
        try {
            await initializeApp();
            showApp();
            debugLog('HANG', 'app ready');
        } catch (e) {
            debugError('HANG', 'initializeApp failed', e?.message || e);
            throw e;
        }
    } else {
        // Check if first-time setup (no users)
        const users = await hasUsers();
        if (!users) {
            // Show register form for first user
            document.getElementById('login-form').style.display = 'none';
            document.getElementById('register-form').style.display = 'flex';
        }
        showLoginScreen();
        debugLog('HANG', 'auth logged out, showing login/register');
    }
    
    debugLog('APP', 'Initialization complete');
}

// Start the app
document.addEventListener('DOMContentLoaded', main);
