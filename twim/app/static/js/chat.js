/**
 * Chat functionality - sending messages, streaming responses
 */

import { api } from './api.js';
import { debugLog, debugError } from './debug-flags.js';

let currentConversationId = null;
let isGenerating = false;

const CHAT_DOCK_HEIGHT_KEY = 'twim_chat_input_dock_height';
const CHAT_DOCK_DEFAULT_PX = 112;
const CHAT_DOCK_MIN_PX = 72;

/**
 * Get or create current conversation
 */
export function getCurrentConversationId() {
    return currentConversationId;
}

export function setCurrentConversationId(id) {
    currentConversationId = id;
}

/**
 * Load conversation messages
 */
export async function loadConversation(conversationId) {
    try {
        const conversation = await api(`/api/conversations/${conversationId}`);
        currentConversationId = conversationId;
        renderMessages(conversation.messages);
        debugLog('CHAT', 'Loaded conversation:', conversationId);
        return conversation;
    } catch (e) {
        debugError('CHAT', 'Failed to load conversation:', e);
        return null;
    }
}

/**
 * Create a new conversation
 */
export async function createConversation() {
    try {
        const conversation = await api('/api/conversations', {
            method: 'POST',
            body: { title: 'New Chat' }
        });
        currentConversationId = conversation.id;
        clearMessages();
        debugLog('CHAT', 'Created conversation:', conversation.id);
        return conversation;
    } catch (e) {
        debugError('CHAT', 'Failed to create conversation:', e);
        return null;
    }
}

/**
 * Send a message
 */
export async function sendMessage(message, provider, model) {
    if (isGenerating) return;
    
    const chatInput = document.getElementById('chat-input');
    const messagesContainer = document.getElementById('messages');
    
    if (!message.trim()) return;
    
    isGenerating = true;
    updateSendButton(true);
    
    // Add user message to UI
    addMessageToUI('user', message);
    chatInput.value = '';
    
    // Add placeholder for assistant
    const assistantDiv = addMessageToUI('assistant', '');
    const contentDiv = assistantDiv.querySelector('.message-content');
    
    try {
        debugLog('CHAT', 'Sending message:', { conversationId: currentConversationId, provider, model });

        const response = await fetch('/api/dictation/cleanup-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ text: message })
        });
        
        if (!response.ok) {
            throw new Error('Chat request failed');
        }
        
        const result = await response.json();
        const fullResponse = result.text || '';
        contentDiv.textContent = fullResponse;
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        debugLog('CHAT', 'Response complete');
        
    } catch (e) {
        debugError('CHAT', 'Error:', e);
        contentDiv.textContent = `Error: ${e.message}`;
        contentDiv.classList.add('error');
    } finally {
        isGenerating = false;
        updateSendButton(false);
    }
}

/**
 * Add a message to the UI
 */
/** Append dictation result as a user message in the chat transcript (browser UI only). */
export function appendDictatedTextToChat(text) {
    const t = (text && String(text).trim()) || '';
    if (!t) return;
    addMessageToUI('user', t);
}

const MESSAGE_COPY_ICON_SVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
  <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/>
  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;

async function copyMessageText(text) {
    const value = (text ?? '').toString();
    if (!value.trim()) return;
    try {
        await navigator.clipboard.writeText(value);
    } catch (e) {
        debugError('CHAT', 'Clipboard copy failed:', e);
    }
}

function createMessageCopyButton(contentDiv) {
    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'message-copy-btn';
    copyBtn.title = 'Copy';
    copyBtn.setAttribute('aria-label', 'Copy message');
    copyBtn.innerHTML = MESSAGE_COPY_ICON_SVG;
    copyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        copyMessageText(contentDiv.textContent);
        const prev = copyBtn.title;
        copyBtn.title = 'Copied';
        window.setTimeout(() => {
            copyBtn.title = prev;
        }, 1500);
    });
    return copyBtn;
}

function addMessageToUI(role, content) {
    const messagesContainer = document.getElementById('messages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;
    
    messageDiv.appendChild(contentDiv);
    messageDiv.appendChild(createMessageCopyButton(contentDiv));
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    return messageDiv;
}

/**
 * Render all messages
 */
function renderMessages(messages) {
    const messagesContainer = document.getElementById('messages');
    messagesContainer.innerHTML = '';
    
    for (const msg of messages) {
        addMessageToUI(msg.role, msg.content);
    }
}

/**
 * Clear messages
 */
function clearMessages() {
    const messagesContainer = document.getElementById('messages');
    messagesContainer.innerHTML = '';
}

/**
 * Update send button state
 */
function updateSendButton(generating) {
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) {
        sendBtn.disabled = generating;
        sendBtn.textContent = generating ? 'Generating...' : 'Send';
    }
}

/**
 * Parse model select value into provider and model
 * Format is "provider:model" where model may contain colons (e.g., "ollama:qwen3.5:9b")
 */
function parseModelValue(value) {
    if (!value || !value.includes(':')) {
        return { provider: null, model: null };
    }
    const colonIndex = value.indexOf(':');
    const provider = value.substring(0, colonIndex);
    const model = value.substring(colonIndex + 1);
    return { provider: provider || null, model: model || null };
}

function clampChatDockHeightPx(h) {
    const cap = Math.min(Math.floor(window.innerHeight * 0.7), 560);
    return Math.max(CHAT_DOCK_MIN_PX, Math.min(cap, Math.round(h)));
}

function initChatInputDockResize() {
    const dock = document.getElementById('chat-input-dock');
    const resizer = document.getElementById('chat-input-resizer');
    if (!dock || !resizer) return;

    let h = CHAT_DOCK_DEFAULT_PX;
    try {
        const raw = localStorage.getItem(CHAT_DOCK_HEIGHT_KEY);
        if (raw) {
            const n = parseInt(raw, 10);
            if (!Number.isNaN(n)) h = clampChatDockHeightPx(n);
        }
    } catch (_e) {
        /* ignore */
    }
    dock.style.setProperty('--chat-input-dock-height', `${h}px`);

    let dragging = false;
    let startY = 0;
    let startH = 0;

    resizer.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        dragging = true;
        startY = e.clientY;
        startH = dock.getBoundingClientRect().height;
        resizer.setPointerCapture(e.pointerId);
        resizer.classList.add('is-dragging');
    });

    resizer.addEventListener('pointermove', (e) => {
        if (!dragging) return;
        /* Handle is on top of dock: drag up → taller dock, drag down → shorter */
        const delta = e.clientY - startY;
        const next = clampChatDockHeightPx(startH - delta);
        dock.style.setProperty('--chat-input-dock-height', `${next}px`);
    });

    const endDrag = (e) => {
        if (!dragging) return;
        dragging = false;
        resizer.classList.remove('is-dragging');
        try {
            resizer.releasePointerCapture(e.pointerId);
        } catch (_err) {
            /* not capturing */
        }
        const rect = dock.getBoundingClientRect();
        try {
            localStorage.setItem(CHAT_DOCK_HEIGHT_KEY, String(Math.round(rect.height)));
        } catch (_e) {
            /* ignore */
        }
    };

    resizer.addEventListener('pointerup', endDrag);
    resizer.addEventListener('pointercancel', endDrag);

    resizer.addEventListener('dblclick', () => {
        dock.style.setProperty('--chat-input-dock-height', `${CHAT_DOCK_DEFAULT_PX}px`);
        try {
            localStorage.setItem(CHAT_DOCK_HEIGHT_KEY, String(CHAT_DOCK_DEFAULT_PX));
        } catch (_e) {
            /* ignore */
        }
    });

    window.addEventListener('resize', () => {
        const cur = dock.getBoundingClientRect().height;
        const c = clampChatDockHeightPx(cur);
        if (c !== cur) {
            dock.style.setProperty('--chat-input-dock-height', `${c}px`);
        }
    });
}

/**
 * Initialize chat event listeners
 */
export function initChat() {
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const modelSelect = document.getElementById('model-select');
    
    if (sendBtn) {
        sendBtn.addEventListener('click', () => {
            const message = chatInput.value;
            const { provider, model } = parseModelValue(modelSelect?.value);
            sendMessage(message, provider, model);
        });
    }
    
    if (chatInput) {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const message = chatInput.value;
                const { provider, model } = parseModelValue(modelSelect?.value);
                sendMessage(message, provider, model);
            }
        });
    }

    initChatInputDockResize();
}
