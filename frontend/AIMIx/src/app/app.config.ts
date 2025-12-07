import { ApplicationConfig } from '@angular/core';
import { provideRouter } from '@angular/router';
// 1. Import withFetch here
import { provideHttpClient, withFetch } from '@angular/common/http';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    // 2. Add withFetch() inside the parentheses
    provideHttpClient(withFetch()) 
  ]
};