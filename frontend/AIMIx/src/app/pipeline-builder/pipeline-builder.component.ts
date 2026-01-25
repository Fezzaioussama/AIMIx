import { Component, OnInit, ChangeDetectorRef, Inject, PLATFORM_ID } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';

interface PipelineStep {
    id?: number;
    order: number;
    prompt: string;
    model: string;
}

interface Pipeline {
    id?: number;
    name: string;
    steps: PipelineStep[];
}

interface RunResult {
    step_order: number;
    model: string;
    input_used: string;
    output: string;
    safeOutput?: SafeHtml;
}

@Component({
    selector: 'app-pipeline-builder',
    standalone: true,
    imports: [CommonModule, FormsModule],
    templateUrl: './pipeline-builder.component.html',
    styleUrls: ['./pipeline-builder.component.css']
})
export class PipelineBuilderComponent implements OnInit {
    pipeline: Pipeline = {
        name: 'New Pipeline',
        steps: [
            { order: 1, prompt: 'Translate this to French: {input}', model: 'meta-llama/Llama-3-8b-chat-hf' }
        ]
    };

    availableModels = [
        'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
        'meta-llama/Llama-3-8b-chat-hf',
        'openai/gpt-oss-120b',
        'Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8'
    ];

    pipelines: Pipeline[] = [];
    selectedPipelineId: number | null = null;

    userInput: string = '';
    isSaving: boolean = false;
    isRunning: boolean = false;
    runResults: RunResult[] = [];
    finalOutput: string = '';
    finalOutputSafe?: SafeHtml;

    constructor(
        private http: HttpClient,
        private cdr: ChangeDetectorRef,
        private sanitizer: DomSanitizer,
        @Inject(PLATFORM_ID) private platformId: Object
    ) { }

    ngOnInit(): void {
        this.loadPipelines();
    }

    loadPipelines() {
        if (!isPlatformBrowser(this.platformId)) return;
        const token = localStorage.getItem('access_token');
        if (!token) return;
        const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
        this.http.get<Pipeline[]>('http://127.0.0.1:8000/api/pipelines/', { headers }).subscribe({
            next: (res) => {
                this.pipelines = res;
                this.cdr.detectChanges();
            },
            error: (err) => console.error('Load error:', err)
        });
    }

    selectPipeline(p: Pipeline) {
        // Deep copy to avoid binding issues
        this.pipeline = JSON.parse(JSON.stringify(p));
        this.selectedPipelineId = p.id || null;
        this.runResults = [];
        this.finalOutput = '';
        this.cdr.detectChanges();
    }

    resetPipeline() {
        this.pipeline = {
            name: 'New Pipeline',
            steps: [
                { order: 1, prompt: '', model: this.availableModels[1] }
            ]
        };
        this.selectedPipelineId = null;
        this.runResults = [];
        this.finalOutput = '';
    }

    addStep() {
        const nextOrder = this.pipeline.steps.length + 1;
        this.pipeline.steps.push({
            order: nextOrder,
            prompt: '',
            model: this.availableModels[1]
        });
    }

    removeStep(index: number) {
        this.pipeline.steps.splice(index, 1);
        // Re-order steps
        this.pipeline.steps.forEach((step, idx) => step.order = idx + 1);
    }

    savePipeline() {
        if (!isPlatformBrowser(this.platformId)) return;
        this.isSaving = true;
        const token = localStorage.getItem('access_token');
        const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);

        this.http.post<any>('http://127.0.0.1:8000/api/pipelines/', this.pipeline, { headers }).subscribe({
            next: (res) => {
                this.pipeline.id = res.id;
                this.isSaving = false;
                alert('Pipeline saved successfully!');
            },
            error: (err) => {
                console.error('Save error:', err);
                this.isSaving = false;
                alert('Failed to save pipeline.');
            }
        });
    }

    runPipeline() {
        if (!this.pipeline.id) {
            alert('Please save the pipeline before running it.');
            return;
        }

        this.isRunning = true;
        this.runResults = [];
        this.finalOutput = '';
        if (!isPlatformBrowser(this.platformId)) return;
        const token = localStorage.getItem('access_token');
        const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);

        this.http.post<any>(`http://127.0.0.1:8000/api/pipelines/${this.pipeline.id}/run`, { input: this.userInput }, { headers }).subscribe({
            next: (res) => {
                this.runResults = res.intermediate_results.map((r: any) => ({
                    ...r,
                    safeOutput: this.sanitizer.bypassSecurityTrustHtml(marked.parse(r.output) as string)
                }));
                this.finalOutput = res.final_output;
                this.finalOutputSafe = this.sanitizer.bypassSecurityTrustHtml(marked.parse(res.final_output) as string);
                this.isRunning = false;
                this.cdr.detectChanges();
            },
            error: (err) => {
                console.error('Run error:', err);
                this.isRunning = false;
                alert('Execution failed. Check your API key and pipeline configuration.');
            }
        });
    }
}
