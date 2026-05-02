/**
 * Chat functionality - sending messages, streaming responses
 */

import { api } from './api.js';
import { debugLog, debugError } from './debug-flags.js';

let currentConversationId = null;
let isGenerating = false;

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
function addMessageToUI(role, content) {
    const messagesContainer = document.getElementById('messages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;
    
    messageDiv.appendChild(contentDiv);
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
}
