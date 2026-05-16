import { Component, OnInit, Inject, PLATFORM_ID, ChangeDetectorRef } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';

interface Workflow {
    id: string;
    name: string;
    active: boolean;
    createdAt: string;
    updatedAt: string;
    nodes?: any[];
    tags?: any[];
}

interface Execution {
    id: string;
    finished: boolean;
    mode: string;
    startedAt: string;
    stoppedAt: string;
    workflowId: string;
    status: string;
    workflowName?: string;
}

@Component({
    selector: 'app-workflows',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './workflows.component.html',
    styleUrls: ['./workflows.component.css']
})
export class WorkflowsComponent implements OnInit {
    workflows: Workflow[] = [];
    executions: Execution[] = [];
    isLoading = true;
    isConnected = false;
    errorMessage = '';
    apiKeyMissing = false;
    apiKeyMessage = '';
    activeTab: 'workflows' | 'executions' = 'workflows';
    selectedWorkflow: Workflow | null = null;

    constructor(
        private http: HttpClient,
        private cdr: ChangeDetectorRef,
        @Inject(PLATFORM_ID) private platformId: Object
    ) { }

    ngOnInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.checkConnection();
        }
    }

    checkConnection(): void {
        this.isLoading = true;
        this.errorMessage = '';
        this.http.get<{ status: string }>('/api/n8n/health').subscribe({
            next: (data) => {
                this.isConnected = data.status === 'connected';
                if (this.isConnected) {
                    this.loadWorkflows();
                    this.loadExecutions();
                } else {
                    this.isLoading = false;
                    this.errorMessage = 'n8n is not running. Start it with: make run-n8n';
                    this.cdr.detectChanges();
                }
            },
            error: () => {
                this.isConnected = false;
                this.isLoading = false;
                this.errorMessage = 'n8n is not running. Start it with: make run-n8n';
                this.cdr.detectChanges();
            }
        });
    }

    loadWorkflows(): void {
        this.http.get<any>('/api/n8n/workflows').subscribe({
            next: (resp) => {
                if (resp.api_key_missing) {
                    this.apiKeyMissing = true;
                    this.apiKeyMessage = resp.message || 'API key not configured';
                    this.workflows = [];
                } else {
                    this.workflows = resp.data || resp || [];
                }
                this.isLoading = false;
                this.cdr.detectChanges();
            },
            error: () => {
                this.workflows = [];
                this.isLoading = false;
                this.cdr.detectChanges();
            }
        });
    }

    loadExecutions(): void {
        this.http.get<any>('/api/n8n/executions').subscribe({
            next: (resp) => {
                this.executions = resp.data || resp || [];
                this.cdr.detectChanges();
            },
            error: () => {
                this.executions = [];
                this.cdr.detectChanges();
            }
        });
    }

    selectWorkflow(wf: Workflow): void {
        if (this.selectedWorkflow?.id === wf.id) {
            this.selectedWorkflow = null;
            this.cdr.detectChanges();
        } else {
            this.http.get<any>(`/api/n8n/workflows/${wf.id}`).subscribe({
                next: (data) => {
                    this.selectedWorkflow = data;
                    this.cdr.detectChanges();
                },
                error: () => {
                    this.selectedWorkflow = wf;
                    this.cdr.detectChanges();
                }
            });
        }
    }

    setTab(tab: 'workflows' | 'executions'): void {
        this.activeTab = tab;
        this.selectedWorkflow = null;
        this.cdr.detectChanges();
    }

    openN8n(): void {
        if (isPlatformBrowser(this.platformId)) {
            window.open('http://localhost:5678', '_blank');
        }
    }

    getStatusClass(status: string): string {
        if (status === 'success') return 'status-success';
        if (status === 'error' || status === 'failed') return 'status-error';
        if (status === 'running' || status === 'waiting') return 'status-running';
        return 'status-unknown';
    }

    getNodeCount(wf: Workflow): number {
        return wf.nodes?.length || 0;
    }

    formatDate(date: string): string {
        if (!date) return '—';
        return new Date(date).toLocaleString();
    }

    getTimeAgo(date: string): string {
        if (!date) return '';
        const seconds = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
        if (seconds < 60) return 'just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        return `${Math.floor(seconds / 86400)}d ago`;
    }
}
