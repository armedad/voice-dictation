/**
 * ai-frame - Main Application Entry Point
 */

import { debugLog, debugWarn, serverLog } from './debug-flags.js';
import { api } from './api.js';
import { checkAuth, login, register, logout, hasUsers } from './auth.js';
import { loadSettings, loadModels, loadSpeechModels, initSettings } from './settings.js';
import { initChat, createConversation } from './chat.js';
import { initNotifications, startNotificationPolling, stopNotificationPolling } from './notifications.js';
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
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
    stopNotificationPolling();
}

/**
 * Show main app
 */
function showApp() {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    startNotificationPolling();
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
    
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    
    try {
        const result = await login(username, password);
        state.currentUser = result;
        state.isLoggedIn = true;
        updateUserDisplay();
        await initializeApp();
        showApp();
    } catch (e) {
        errorEl.textContent = e.message || 'Login failed';
    }
}

/**
 * Handle register form
 */
async function handleRegister(e) {
    e.preventDefault();
    
    const username = document.getElementById('register-username').value;
    const displayName = document.getElementById('register-display-name').value;
    const password = document.getElementById('register-password').value;
    const confirmPassword = document.getElementById('register-password-confirm').value;
    const errorEl = document.getElementById('login-error');
    
    if (password !== confirmPassword) {
        errorEl.textContent = 'Passwords do not match';
        return;
    }
    
    try {
        const result = await register(username, password, displayName || username);
        state.currentUser = result;
        state.isLoggedIn = true;
        updateUserDisplay();
        await initializeApp();
        showApp();
    } catch (e) {
        errorEl.textContent = e.message || 'Registration failed';
    }
}

/**
 * Handle logout
 */
async function handleLogout() {
    await logout();
    state.currentUser = null;
    state.isLoggedIn = false;
    showLoginScreen();
}

/**
 * Initialize app after login
 */
async function initializeApp() {
    await loadSettings();
    await loadModels();
    await loadSpeechModels();
    await createConversation();
    await syncContextTabFromSettings();
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Login form
    document.getElementById('login-btn')?.addEventListener('click', handleLogin);
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
            if (dictateSessionActive) {
                try {
                    debugLog('DICTATION', 'POST /api/dictation/hotkey/cancel (stop recording)');
                    await api('dictation/hotkey/cancel', { method: 'POST', body: {} });
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
                const result = await api('dictation/record-and-type', {
                    method: 'POST',
                    body: {},
                });
                debugLog('DICTATION', 'POST /api/dictation/record-and-type finished', result);
                if (result.cancelled) {
                    dictateBtn.textContent = 'Cancelled';
                } else if (result.skipped_empty) {
                    dictateBtn.textContent = 'No speech detected';
                } else {
                    await refreshDictationLastContext();
                    dictateBtn.textContent = 'Done';
                }
                setTimeout(() => {
                    dictateBtn.textContent = defaultLabel;
                }, 1500);
            } catch (e) {
                debugWarn('DICTATION', 'record-and-type failed:', e?.message || e);
                dictateBtn.textContent = defaultLabel;
                alert(e.message || 'Dictation failed');
            } finally {
                dictateSessionActive = false;
            }
        });
    }
}

/**
 * Main entry point
 */
async function main() {
    debugLog('APP', 'Initializing ai-frame');
    
    // Setup UI
    setupEventListeners();
    initSettings();
    initContextTab();
    initChat();
    initNotifications();
    
    // Check authentication
    const auth = await checkAuth();
    
    if (auth.logged_in) {
        state.currentUser = auth;
        state.isLoggedIn = true;
        updateUserDisplay();
        await initializeApp();
        showApp();
    } else {
        // Check if first-time setup (no users)
        const users = await hasUsers();
        if (!users) {
            // Show register form for first user
            document.getElementById('login-form').style.display = 'none';
            document.getElementById('register-form').style.display = 'flex';
        }
        showLoginScreen();
    }
    
    debugLog('APP', 'Initialization complete');
}

// Start the app
document.addEventListener('DOMContentLoaded', main);
