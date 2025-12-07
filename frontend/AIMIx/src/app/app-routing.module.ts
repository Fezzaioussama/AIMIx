import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './login/login.component'; // <-- Import your component

// Define your application routes
const routes: Routes = [
  // When the path is 'login', use the LoginComponent
  { path: 'login', component: LoginComponent }, 
  
  // You'll need a Home component later for successful login
  // { path: 'home', component: HomeComponent }, 
  
  // Redirect to '/login' if no path is given
  { path: '', redirectTo: '/login', pathMatch: 'full' }, 
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }