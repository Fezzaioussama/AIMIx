import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { HttpClient, HttpHeaders } from '@angular/common/http';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';

interface Message {
    text: string;
    sender: 'user' | 'ai';
    timestamp: Date;
    safeHtml?: SafeHtml; // Optional safe HTML for markdown
}

@Component({
    selector: 'app-chat',
    standalone: true,
    imports: [CommonModule, FormsModule],
    templateUrl: './chat.component.html',
    styleUrls: ['./chat.component.css']
})
export class ChatComponent implements OnInit {
    messages: Message[] = [];
    userInput: string = '';
    isLoading: boolean = false;
    private apiUrl = 'http://127.0.0.1:8000/api/chat';

    constructor(
        private http: HttpClient,
        private cdr: ChangeDetectorRef,
        private sanitizer: DomSanitizer
    ) {
        this.messages = [
            {
                text: 'Hello! I am your AI assistant. How can I help you today?',
                sender: 'ai',
                timestamp: new Date(),
                safeHtml: this.sanitizer.bypassSecurityTrustHtml('Hello! I am your AI assistant. How can I help you today?')
            }
        ];
    }

    ngOnInit(): void { }

    async sendMessage(): Promise<void> {
        if (!this.userInput.trim() || this.isLoading) return;

        const userMessage: Message = {
            text: this.userInput,
            sender: 'user',
            timestamp: new Date()
        };

        this.messages = [...this.messages, userMessage];
        const prompt = this.userInput;
        this.userInput = '';
        this.isLoading = true;
        this.scrollToBottom();

        // Prepare for AI message
        const aiMessage: Message = {
            text: '',
            sender: 'ai',
            timestamp: new Date(),
            safeHtml: this.sanitizer.bypassSecurityTrustHtml('')
        };
        this.messages = [...this.messages, aiMessage];
        const aiMessageIndex = this.messages.length - 1;

        // Get token from local storage
        const token = localStorage.getItem('access_token');

        try {
            const response = await fetch(this.apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ prompt })
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            if (!response.body) throw new Error('ReadableStream not supported');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';

            this.isLoading = false; // Hide typing indicator once we start receiving tokens

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                fullText += chunk;

                // Update message text and render markdown
                this.messages[aiMessageIndex].text = fullText;
                this.messages[aiMessageIndex].safeHtml = this.renderMarkdown(fullText);

                this.cdr.detectChanges();
                this.scrollToBottom();
            }

        } catch (err) {
            console.error('Chat error detail:', err);
            this.messages[aiMessageIndex].text = 'Sorry, I encountered an error. Please check your connection or API key.';
            this.messages[aiMessageIndex].safeHtml = this.sanitizer.bypassSecurityTrustHtml(this.messages[aiMessageIndex].text);
            this.isLoading = false;
            this.cdr.detectChanges();
        }
    }

    private renderMarkdown(text: string): SafeHtml {
        const html = marked.parse(text) as string;
        return this.sanitizer.bypassSecurityTrustHtml(html);
    }

    private scrollToBottom(): void {
        setTimeout(() => {
            const chatContainer = document.querySelector('.chat-messages');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }, 50);
    }
}
