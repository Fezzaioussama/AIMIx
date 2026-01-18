import { Routes } from '@angular/router';
import { LoginComponent } from './login/login.component';
import { ChatComponent } from './chat/chat.component';
import { PipelineBuilderComponent } from './pipeline-builder/pipeline-builder.component';

export const routes: Routes = [
    { path: 'login', component: LoginComponent },
    { path: 'chat', component: ChatComponent },
    { path: 'pipeline', component: PipelineBuilderComponent },
    { path: '', redirectTo: '/login', pathMatch: 'full' }
];