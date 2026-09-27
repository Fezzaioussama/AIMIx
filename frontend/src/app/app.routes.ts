import { Routes } from '@angular/router';
import { LoginComponent } from './features/auth/login/login.component';
import { RegisterComponent } from './features/auth/register/register.component';
import { ChatComponent } from './features/chat/chat.component';
import { AutoPipelineComponent } from './features/pipelines/auto-pipeline/auto-pipeline.component';
import { PipelineBuilderComponent } from './features/pipelines/pipeline-builder/pipeline-builder.component';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: 'register', component: RegisterComponent },
  { path: 'chat', component: ChatComponent },
  { path: 'pipeline', component: PipelineBuilderComponent },
  { path: 'auto-pipeline', component: AutoPipelineComponent },
  { path: '', redirectTo: '/login', pathMatch: 'full' },
];
