import { Routes } from '@angular/router';
import { LoginComponent } from './login/login.component';
import { ChatComponent } from './chat/chat.component';
import { PipelineBuilderComponent } from './pipeline-builder/pipeline-builder.component';
import { AutoPipelineComponent } from './auto-pipeline/auto-pipeline.component';
import { RegisterComponent } from './register/register.component';
import { WorkflowsComponent } from './workflows/workflows.component';

export const routes: Routes = [
    { path: 'login', component: LoginComponent },
    { path: 'register', component: RegisterComponent },
    { path: 'chat', component: ChatComponent },
    { path: 'pipeline', component: PipelineBuilderComponent },
    { path: 'auto-pipeline', component: AutoPipelineComponent },
    { path: 'workflows', component: WorkflowsComponent },
    { path: '', redirectTo: '/login', pathMatch: 'full' }
];