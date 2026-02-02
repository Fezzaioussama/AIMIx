import { Component, OnInit, ChangeDetectorRef, Inject, PLATFORM_ID } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Router } from '@angular/router';

interface GeneratedStep {
    order: number;
    prompt: string;
    model: string;
}

interface GeneratedPipeline {
    name: string;
    steps: GeneratedStep[];
}

@Component({
    selector: 'app-auto-pipeline',
    standalone: true,
    imports: [CommonModule, FormsModule, RouterLink, RouterLinkActive],
    templateUrl: './auto-pipeline.component.html',
    styleUrls: ['./auto-pipeline.component.css']
})
export class AutoPipelineComponent implements OnInit {
    description: string = '';
    plannerModel: string = 'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8';

    availableModels: string[] = [];
    generatedPipeline: GeneratedPipeline | null = null;

    isGenerating: boolean = false;
    isSaving: boolean = false;
    errorMessage: string = '';
    successMessage: string = '';

    constructor(
        private http: HttpClient,
        private cdr: ChangeDetectorRef,
        private router: Router,
        @Inject(PLATFORM_ID) private platformId: Object
    ) { }

    ngOnInit(): void {
        // Default available models
        this.availableModels = [
            'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
            'meta-llama/Llama-3-8b-chat-hf',
            'openai/gpt-oss-120b',
            'Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8'
        ];
    }

    getAuthHeaders(): HttpHeaders {
        if (!isPlatformBrowser(this.platformId)) {
            return new HttpHeaders();
        }
        const token = localStorage.getItem('access_token');
        return new HttpHeaders().set('Authorization', `Bearer ${token}`);
    }

    generatePipeline() {
        if (!this.description.trim()) {
            this.errorMessage = 'Please describe your workflow first.';
            return;
        }

        this.isGenerating = true;
        this.errorMessage = '';
        this.successMessage = '';
        this.generatedPipeline = null;

        const payload = {
            description: this.description,
            planner_model: this.plannerModel
        };

        this.http.post<any>('http://127.0.0.1:8000/api/pipelines/generate', payload, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (res) => {
                this.generatedPipeline = res.generated_pipeline;
                if (res.available_models) {
                    this.availableModels = res.available_models;
                }
                this.isGenerating = false;
                this.cdr.detectChanges();
            },
            error: (err) => {
                console.error('Generation error:', err);
                this.errorMessage = err.error?.error || 'Failed to generate pipeline. Please try again.';
                this.isGenerating = false;
                this.cdr.detectChanges();
            }
        });
    }

    updateStepModel(index: number, model: string) {
        if (this.generatedPipeline) {
            this.generatedPipeline.steps[index].model = model;
        }
    }

    savePipeline() {
        if (!this.generatedPipeline) return;

        this.isSaving = true;
        this.errorMessage = '';

        this.http.post<any>('http://127.0.0.1:8000/api/pipelines/', this.generatedPipeline, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (res) => {
                this.successMessage = `Pipeline "${res.name}" saved successfully!`;
                this.isSaving = false;
                this.cdr.detectChanges();
            },
            error: (err) => {
                console.error('Save error:', err);
                this.errorMessage = 'Failed to save pipeline.';
                this.isSaving = false;
                this.cdr.detectChanges();
            }
        });
    }

    saveAndNavigate() {
        if (!this.generatedPipeline) return;

        this.isSaving = true;
        this.errorMessage = '';

        this.http.post<any>('http://127.0.0.1:8000/api/pipelines/', this.generatedPipeline, {
            headers: this.getAuthHeaders()
        }).subscribe({
            next: (res) => {
                this.isSaving = false;
                // Navigate to pipeline builder to run it
                this.router.navigate(['/pipeline']);
            },
            error: (err) => {
                console.error('Save error:', err);
                this.errorMessage = 'Failed to save pipeline.';
                this.isSaving = false;
                this.cdr.detectChanges();
            }
        });
    }

    resetForm() {
        this.description = '';
        this.generatedPipeline = null;
        this.errorMessage = '';
        this.successMessage = '';
    }

    getModelName(fullPath: string): string {
        return fullPath.split('/').pop() || fullPath;
    }
}
