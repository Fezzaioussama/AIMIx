import { ChangeDetectorRef, Component, HostListener, Inject, OnDestroy, OnInit, PLATFORM_ID } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Router } from '@angular/router';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

type WorkflowFilter = 'all' | 'active' | 'inactive';
type ExecutionFilter = 'all' | 'success' | 'error' | 'running';

interface Toast {
    id: number;
    kind: 'success' | 'error' | 'warning' | 'info';
    message: string;
    leaving?: boolean;
}

interface WorkflowNode {
    name: string;
    type: string;
    parameters?: {
        httpMethod?: string;
        path?: string;
        [key: string]: unknown;
    };
}

interface Workflow {
    id: string;
    name: string;
    active: boolean;
    createdAt: string;
    updatedAt: string;
    activeVersionId?: string | null;
    nodes?: WorkflowNode[];
    tags?: any[];
    triggerCount?: number;
}

interface Execution {
    id: string;
    finished?: boolean;
    mode?: string;
    startedAt?: string;
    stoppedAt?: string;
    workflowId?: string;
    workflowData?: {
        name?: string;
    };
    status?: string;
    data?: unknown;
}

interface WebhookTarget {
    label: string;
    method: string;
    path: string;
    nodeName: string;
}

interface GeneratedWorkflowPlan {
    name: string;
    summary?: string;
    credential_notes?: string[];
    activation_notes?: string[];
}

interface AutoFixIteration {
    iteration: number;
    execution_id: string;
    status: string;
    failing_node: string;
    error_message: string;
    explanation: string;
    patched: boolean;
    new_execution_id: string;
    needs_user_action: string;
}

interface AutoFixReport {
    workflow_id: string;
    iteration_cap: number;
    iterations: AutoFixIteration[];
    final_state: string;
    final_execution_id: string;
    needs_user_action: string;
}

@Component({
    selector: 'app-workflows',
    standalone: true,
    imports: [CommonModule, FormsModule],
    templateUrl: './workflows.component.html',
    styleUrls: ['./workflows.component.css']
})
export class WorkflowsComponent implements OnInit, OnDestroy {
    workflows: Workflow[] = [];
    executions: Execution[] = [];
    isLoading = true;
    isConnected = false;
    errorMessage = '';
    apiKeyMissing = false;
    apiKeyMessage = '';
    actionMessage = '';
    actionError = '';
    activeTab: 'designer' | 'workflows' | 'executions' = 'designer';
    selectedWorkflow: Workflow | null = null;
    selectedExecution: Execution | null = null;
    isLoadingExecution = false;
    workflowActionId: string | null = null;
    executionActionId: string | null = null;

    workflowSearch = '';
    workflowFilter: WorkflowFilter = 'all';
    executionFilter: ExecutionFilter = 'all';
    autoRefreshExecutions = false;
    private autoRefreshTimer: any = null;
    toasts: Toast[] = [];
    private toastSeq = 0;
    copiedId = '';

    n8nEditorUrl = 'http://localhost:5678';
    n8nEditorSafeUrl: SafeResourceUrl;
    editorPath = '';

    selectedWebhookPath = '';
    webhookPayload = '{\n  "message": "Hello from AIMIx"\n}';
    webhookResult = '';
    webhookError = '';
    isTriggeringWebhook = false;

    aiWorkflowPrompt = '';
    isGeneratingWorkflow = false;
    generationMessage = '';
    generationError = '';
    generationWarning = '';
    generatedPlan: GeneratedWorkflowPlan | null = null;
    availableNodeCount = 0;

    autofixActionId: string | null = null;
    autofixReport: AutoFixReport | null = null;
    autofixError = '';

    constructor(
        private http: HttpClient,
        private cdr: ChangeDetectorRef,
        private sanitizer: DomSanitizer,
        private router: Router,
        @Inject(PLATFORM_ID) private platformId: Object
    ) {
        this.n8nEditorSafeUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.n8nEditorUrl);
    }

    ngOnInit(): void {
        if (isPlatformBrowser(this.platformId)) {
            this.loadEditorConfig();
            this.loadNodeCatalog();
            this.checkConnection();
        }
    }

    ngOnDestroy(): void {
        this.stopAutoRefresh();
    }

    @HostListener('document:keydown.escape')
    onEscape(): void {
        if (this.selectedExecution) {
            this.selectedExecution = null;
            this.cdr.detectChanges();
            return;
        }
        if (this.selectedWorkflow) {
            this.selectedWorkflow = null;
            this.cdr.detectChanges();
            return;
        }
        if (this.autofixReport) {
            this.autofixReport = null;
            this.cdr.detectChanges();
        }
    }

    get filteredWorkflows(): Workflow[] {
        const term = this.workflowSearch.trim().toLowerCase();
        return this.workflows.filter((wf) => {
            if (this.workflowFilter === 'active' && !wf.active) return false;
            if (this.workflowFilter === 'inactive' && wf.active) return false;
            if (!term) return true;
            return (wf.name || '').toLowerCase().includes(term)
                || (wf.id || '').toLowerCase().includes(term);
        });
    }

    get filteredExecutions(): Execution[] {
        if (this.executionFilter === 'all') return this.executions;
        return this.executions.filter((exec) => {
            const status = this.getExecutionStatus(exec);
            if (this.executionFilter === 'success') return status === 'success';
            if (this.executionFilter === 'error') {
                return ['error', 'failed', 'crashed'].includes(status);
            }
            if (this.executionFilter === 'running') {
                return ['running', 'waiting', 'new'].includes(status);
            }
            return true;
        });
    }

    get activeWorkflowCount(): number {
        return this.workflows.filter((wf) => wf.active).length;
    }

    get successExecutionCount(): number {
        return this.executions.filter((exec) => this.getExecutionStatus(exec) === 'success').length;
    }

    get failedExecutionCount(): number {
        return this.executions.filter((exec) => ['error', 'failed', 'crashed'].includes(this.getExecutionStatus(exec))).length;
    }

    setWorkflowFilter(filter: WorkflowFilter): void {
        this.workflowFilter = filter;
    }

    setExecutionFilter(filter: ExecutionFilter): void {
        this.executionFilter = filter;
    }

    clearWorkflowSearch(): void {
        this.workflowSearch = '';
    }

    toggleAutoRefresh(): void {
        this.autoRefreshExecutions = !this.autoRefreshExecutions;
        if (this.autoRefreshExecutions) {
            this.startAutoRefresh();
            this.pushToast('info', 'Auto-refresh enabled (every 5s)');
        } else {
            this.stopAutoRefresh();
            this.pushToast('info', 'Auto-refresh disabled');
        }
    }

    private startAutoRefresh(): void {
        this.stopAutoRefresh();
        this.autoRefreshTimer = setInterval(() => {
            if (this.isConnected && !this.apiKeyMissing) {
                this.loadExecutions();
            }
        }, 5000);
    }

    private stopAutoRefresh(): void {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }
    }

    pushToast(kind: Toast['kind'], message: string): void {
        const toast: Toast = { id: ++this.toastSeq, kind, message };
        this.toasts = [...this.toasts, toast];
        this.cdr.detectChanges();
        setTimeout(() => this.dismissToast(toast.id), 4500);
    }

    dismissToast(id: number): void {
        const target = this.toasts.find((t) => t.id === id);
        if (!target) return;
        target.leaving = true;
        this.cdr.detectChanges();
        setTimeout(() => {
            this.toasts = this.toasts.filter((t) => t.id !== id);
            this.cdr.detectChanges();
        }, 220);
    }

    copyToClipboard(value: string, event?: Event): void {
        event?.stopPropagation();
        if (!value || !isPlatformBrowser(this.platformId)) return;
        try {
            navigator.clipboard.writeText(value).then(() => {
                this.copiedId = value;
                this.pushToast('success', 'Copied to clipboard');
                this.cdr.detectChanges();
                setTimeout(() => {
                    if (this.copiedId === value) {
                        this.copiedId = '';
                        this.cdr.detectChanges();
                    }
                }, 1500);
            });
        } catch {
            this.pushToast('error', 'Clipboard not available');
        }
    }

    trackById(_index: number, item: { id: string }): string {
        return item.id;
    }

    trackToastById(_index: number, item: Toast): number {
        return item.id;
    }

    checkConnection(): void {
        if (!this.ensureAuthenticated()) return;
        this.isLoading = true;
        this.errorMessage = '';
        this.actionMessage = '';
        this.actionError = '';
        this.http.get<{ status: string; api_key_configured?: boolean }>('/api/n8n/health').subscribe({
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

    loadEditorConfig(): void {
        this.http.get<{ editor_url?: string }>('/api/n8n/info').subscribe({
            next: (data) => {
                this.n8nEditorUrl = (data.editor_url || this.n8nEditorUrl).replace(/\/$/, '');
                this.setEditorPath(this.editorPath);
                this.cdr.detectChanges();
            },
            error: () => {
                this.setEditorPath(this.editorPath);
            }
        });
    }

    loadWorkflows(): void {
        this.http.get<any>('/api/n8n/workflows', { headers: this.getAuthHeaders() }).subscribe({
            next: (resp) => {
                if (resp.api_key_missing) {
                    this.apiKeyMissing = true;
                    this.apiKeyMessage = resp.message || 'N8N_API_KEY is not configured.';
                    this.workflows = [];
                } else {
                    this.apiKeyMissing = false;
                    this.apiKeyMessage = '';
                    this.workflows = resp.data || resp || [];
                    this.syncSelectedWorkflow();
                }
                this.isLoading = false;
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, 'Unable to load n8n workflows.');
                this.workflows = [];
                this.isLoading = false;
                this.cdr.detectChanges();
            }
        });
    }

    loadNodeCatalog(): void {
        this.http.get<{ count?: number; data?: unknown[] }>('/api/n8n/nodes').subscribe({
            next: (resp) => {
                this.availableNodeCount = resp.count ?? resp.data?.length ?? 0;
                this.cdr.detectChanges();
            },
            error: () => {
                this.availableNodeCount = 0;
            }
        });
    }

    loadExecutions(): void {
        this.http.get<any>('/api/n8n/executions?limit=50', { headers: this.getAuthHeaders() }).subscribe({
            next: (resp) => {
                if (resp.api_key_missing) {
                    this.apiKeyMissing = true;
                    this.apiKeyMessage = resp.message || 'N8N_API_KEY is not configured.';
                    this.executions = [];
                } else {
                    this.executions = resp.data || resp || [];
                }
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, 'Unable to load n8n executions.');
                this.executions = [];
                this.cdr.detectChanges();
            }
        });
    }

    selectWorkflow(wf: Workflow): void {
        this.actionError = '';
        this.actionMessage = '';
        if (this.selectedWorkflow?.id === wf.id) {
            this.selectedWorkflow = null;
            this.selectedWebhookPath = '';
            this.cdr.detectChanges();
            return;
        }

        this.http.get<any>(`/api/n8n/workflows/${encodeURIComponent(wf.id)}`, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (data) => {
                if (data.api_key_missing) {
                    this.apiKeyMissing = true;
                    this.apiKeyMessage = data.message;
                    return;
                }
                this.selectedWorkflow = data;
                this.selectedWebhookPath = this.getWebhookTargets(data)[0]?.path || '';
                this.webhookResult = '';
                this.webhookError = '';
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, 'Unable to load workflow details.');
                this.selectedWorkflow = wf;
                this.selectedWebhookPath = this.getWebhookTargets(wf)[0]?.path || '';
                this.cdr.detectChanges();
            }
        });
    }

    selectExecution(exec: Execution): void {
        if (this.selectedExecution?.id === exec.id) {
            this.selectedExecution = null;
            this.cdr.detectChanges();
            return;
        }

        this.isLoadingExecution = true;
        this.http.get<any>(`/api/n8n/executions/${encodeURIComponent(exec.id)}?includeData=true`, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (data) => {
                this.selectedExecution = data;
                this.isLoadingExecution = false;
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, 'Unable to load execution details.');
                this.selectedExecution = exec;
                this.isLoadingExecution = false;
                this.cdr.detectChanges();
            }
        });
    }

    setTab(tab: 'designer' | 'workflows' | 'executions'): void {
        this.activeTab = tab;
        if (tab !== 'workflows') {
            this.selectedWorkflow = null;
        }
        if (tab !== 'executions') {
            this.selectedExecution = null;
        }
        this.cdr.detectChanges();
    }

    openWorkflowInDesigner(wf: Workflow, event?: Event): void {
        event?.stopPropagation();
        this.setEditorPath(`/workflow/${wf.id}`);
        this.setTab('designer');
    }

    showDesignerHome(): void {
        this.setEditorPath('');
        this.setTab('designer');
    }

    reloadDesigner(): void {
        const currentPath = this.editorPath;
        this.n8nEditorSafeUrl = this.sanitizer.bypassSecurityTrustResourceUrl('about:blank');
        setTimeout(() => {
            this.setEditorPath(currentPath);
            this.cdr.detectChanges();
        });
    }

    activateWorkflow(wf: Workflow, event: Event): void {
        event.stopPropagation();
        this.setWorkflowState(wf, true);
    }

    deactivateWorkflow(wf: Workflow, event: Event): void {
        event.stopPropagation();
        this.setWorkflowState(wf, false);
    }

    runWebhook(): void {
        if (!this.selectedWebhookPath) {
            this.webhookError = 'Select a webhook path first.';
            return;
        }

        let payload: unknown = {};
        const rawPayload = this.webhookPayload.trim();
        if (rawPayload) {
            try {
                payload = JSON.parse(rawPayload);
            } catch {
                this.webhookError = 'Webhook payload must be valid JSON.';
                return;
            }
        }

        this.isTriggeringWebhook = true;
        this.webhookError = '';
        this.webhookResult = '';

        this.http.post<any>(`/api/n8n/webhooks/${this.encodePath(this.selectedWebhookPath)}`, payload, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (resp) => {
                this.webhookResult = this.formatJson(resp);
                this.isTriggeringWebhook = false;
                this.loadExecutions();
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, 'Webhook execution failed.');
                this.webhookError = err.error?.error || err.error?.message || 'Webhook execution failed.';
                this.isTriggeringWebhook = false;
                this.cdr.detectChanges();
            }
        });
    }

    generateWorkflowFromText(): void {
        if (!this.ensureAuthenticated()) return;

        const prompt = this.aiWorkflowPrompt.trim();
        if (prompt.length < 8) {
            this.generationError = 'Describe the workflow in a little more detail.';
            return;
        }

        this.isGeneratingWorkflow = true;
        this.generationError = '';
        this.generationMessage = '';
        this.generationWarning = '';
        this.generatedPlan = null;

        this.http.post<any>('/api/n8n/workflows/generate', { prompt, create: true }, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (resp) => {
                if (resp.api_key_missing) {
                    this.apiKeyMissing = true;
                    this.generationError = resp.message || 'N8N_API_KEY is not configured.';
                    this.isGeneratingWorkflow = false;
                    this.cdr.detectChanges();
                    return;
                }

                const createdWorkflow = resp.created_workflow?.data || resp.created_workflow || {};
                const workflowId = createdWorkflow.id;
                this.generatedPlan = resp.plan || null;
                this.generationWarning = resp.warning || '';
                this.generationMessage = `${createdWorkflow.name || this.generatedPlan?.name || 'Draft workflow'} created.`;
                this.isGeneratingWorkflow = false;
                this.loadWorkflows();

                if (workflowId) {
                    this.setEditorPath(`/workflow/${workflowId}`);
                    this.setTab('designer');
                    this.reloadDesigner();
                }
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, 'Unable to generate workflow.');
                this.generationError = err.error?.error || err.error?.message || 'Unable to generate workflow.';
                this.isGeneratingWorkflow = false;
                this.cdr.detectChanges();
            }
        });
    }

    stopExecution(exec: Execution, event: Event): void {
        event.stopPropagation();
        this.runExecutionAction(exec, 'stop');
    }

    retryExecution(exec: Execution, event: Event): void {
        event.stopPropagation();
        this.runExecutionAction(exec, 'retry', { loadWorkflow: true });
    }

    autofixExecution(exec: Execution, event: Event): void {
        event.stopPropagation();
        if (!this.ensureAuthenticated()) return;
        if (!exec.workflowId) {
            this.autofixError = 'This execution has no associated workflow id.';
            return;
        }
        this.autofixActionId = exec.id;
        this.autofixReport = null;
        this.autofixError = '';
        this.actionMessage = '';
        this.actionError = '';

        this.http.post<AutoFixReport>(
            `/api/n8n/workflows/${encodeURIComponent(exec.workflowId)}/autofix`,
            { execution_id: exec.id },
            { headers: this.getAuthHeaders() }
        ).subscribe({
            next: (report) => {
                this.autofixReport = report;
                this.autofixActionId = null;
                this.actionMessage = this.summarizeAutofix(report);
                this.loadExecutions();
                if (report.final_execution_id) {
                    this.selectExecution({ id: report.final_execution_id } as Execution);
                }
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, 'Auto-fix failed.');
                this.autofixError = err.error?.error || err.error?.message || 'Auto-fix failed.';
                this.autofixActionId = null;
                this.cdr.detectChanges();
            }
        });
    }

    private summarizeAutofix(report: AutoFixReport): string {
        const attempts = report.iterations.length;
        switch (report.final_state) {
            case 'success':
                return `Auto-fix succeeded after ${attempts} attempt(s).`;
            case 'needs_user_action':
                return `Auto-fix paused: ${report.needs_user_action || 'manual step required.'}`;
            case 'no_patch_generated':
                return 'LLM could not produce a concrete patch — open the failing node and inspect.';
            case 'iteration_cap_reached':
                return `Auto-fix used all ${report.iteration_cap} attempts without success.`;
            case 'llm_unavailable':
                return 'Auto-fix could not reach the LLM provider.';
            case 'no_failure_signal':
                return 'No failing node was found in this execution.';
            default:
                return `Auto-fix stopped: ${report.final_state}.`;
        }
    }

    getWebhookTargets(wf: Workflow | null): WebhookTarget[] {
        return (wf?.nodes || [])
            .filter((node) => node.type?.toLowerCase().includes('webhook'))
            .map((node) => {
                const method = String(node.parameters?.httpMethod || 'POST').toUpperCase();
                const path = String(node.parameters?.path || '').replace(/^\/+/, '');
                return {
                    label: `${method} /webhook/${path || '<path>'}`,
                    method,
                    path,
                    nodeName: node.name
                };
            });
    }

    getStatusClass(status?: string): string {
        const normalized = status || 'unknown';
        if (normalized === 'success') return 'status-success';
        if (normalized === 'error' || normalized === 'failed' || normalized === 'crashed') return 'status-error';
        if (normalized === 'running' || normalized === 'waiting' || normalized === 'new') return 'status-running';
        if (normalized === 'canceled') return 'status-canceled';
        return 'status-unknown';
    }

    getExecutionStatus(exec: Execution): string {
        return exec.status || (exec.finished ? 'success' : 'running');
    }

    canStopExecution(exec: Execution): boolean {
        return ['running', 'waiting', 'new'].includes(this.getExecutionStatus(exec));
    }

    canRetryExecution(exec: Execution): boolean {
        return ['error', 'failed', 'crashed', 'canceled'].includes(this.getExecutionStatus(exec));
    }

    getWorkflowName(exec: Execution): string {
        return exec.workflowData?.name
            || this.workflows.find((wf) => wf.id === exec.workflowId)?.name
            || `Workflow ${exec.workflowId || '-'}`;
    }

    getNodeCount(wf: Workflow): number {
        return wf.nodes?.length || 0;
    }

    getNodeTypeLabel(node: WorkflowNode): string {
        return node.type ? node.type.split('.').pop() || node.type : 'unknown';
    }

    formatDate(date?: string): string {
        if (!date) return '-';
        return new Date(date).toLocaleString();
    }

    getTimeAgo(date?: string): string {
        if (!date) return '';
        const seconds = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
        if (seconds < 60) return 'just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        return `${Math.floor(seconds / 86400)}d ago`;
    }

    formatJson(value: unknown): string {
        try {
            return JSON.stringify(value, null, 2);
        } catch {
            return String(value);
        }
    }

    private setWorkflowState(wf: Workflow, active: boolean): void {
        this.workflowActionId = wf.id;
        this.actionError = '';
        this.actionMessage = '';
        const action = active ? 'activate' : 'deactivate';

        this.http.post<any>(`/api/n8n/workflows/${encodeURIComponent(wf.id)}/${action}`, {}, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (resp) => {
                if (resp.api_key_missing) {
                    this.actionError = resp.message || 'N8N_API_KEY is not configured.';
                    this.pushToast('error', this.actionError);
                } else {
                    this.actionMessage = `${wf.name || 'Workflow'} ${active ? 'activated' : 'deactivated'}.`;
                    this.pushToast('success', this.actionMessage);
                    this.loadWorkflows();
                    this.loadExecutions();
                }
                this.workflowActionId = null;
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, `Unable to ${action} workflow.`);
                if (this.actionError) this.pushToast('error', this.actionError);
                this.workflowActionId = null;
                this.cdr.detectChanges();
            }
        });
    }

    private runExecutionAction(exec: Execution, action: 'stop' | 'retry', payload: unknown = {}): void {
        this.executionActionId = exec.id;
        this.actionError = '';
        this.actionMessage = '';

        this.http.post<any>(`/api/n8n/executions/${encodeURIComponent(exec.id)}/${action}`, payload, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (resp) => {
                if (resp.api_key_missing) {
                    this.actionError = resp.message || 'N8N_API_KEY is not configured.';
                    this.pushToast('error', this.actionError);
                } else {
                    this.actionMessage = `Execution #${exec.id} ${action === 'stop' ? 'stopped' : 'retried'}.`;
                    this.pushToast('success', this.actionMessage);
                    this.loadExecutions();
                }
                this.executionActionId = null;
                this.cdr.detectChanges();
            },
            error: (err) => {
                this.handleHttpError(err, `Unable to ${action} execution.`);
                if (this.actionError) this.pushToast('error', this.actionError);
                this.executionActionId = null;
                this.cdr.detectChanges();
            }
        });
    }

    private setEditorPath(path: string): void {
        this.editorPath = path ? (path.startsWith('/') ? path : `/${path}`) : '';
        this.n8nEditorSafeUrl = this.sanitizer.bypassSecurityTrustResourceUrl(
            `${this.n8nEditorUrl}${this.editorPath}`
        );
    }

    private syncSelectedWorkflow(): void {
        if (!this.selectedWorkflow) return;
        const updated = this.workflows.find((wf) => wf.id === this.selectedWorkflow?.id);
        if (updated) {
            this.selectedWorkflow = { ...this.selectedWorkflow, ...updated };
        }
    }

    private getAuthHeaders(): HttpHeaders {
        if (!isPlatformBrowser(this.platformId)) {
            return new HttpHeaders();
        }
        const token = localStorage.getItem('access_token');
        return token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : new HttpHeaders();
    }

    private ensureAuthenticated(): boolean {
        if (!isPlatformBrowser(this.platformId)) return false;
        if (localStorage.getItem('access_token')) return true;
        this.router.navigate(['/login']);
        return false;
    }

    private handleHttpError(err: any, fallback: string): void {
        if (err.status === 401) {
            this.actionError = 'Your AIMIx session is not available in this tab. Log in again, then reopen Workflows.';
            return;
        }
        this.actionError = err.error?.error || err.error?.message || fallback;
    }

    private encodePath(path: string): string {
        return path
            .split('/')
            .filter(Boolean)
            .map((segment) => encodeURIComponent(segment))
            .join('/');
    }
}
