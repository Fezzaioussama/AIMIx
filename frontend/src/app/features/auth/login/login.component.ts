import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/auth/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent {
  username = '';
  password = '';
  errorMessage = '';

  constructor(private authService: AuthService, private router: Router) { }

  onSubmit() {
    this.errorMessage = '';

    this.authService.login(this.username, this.password).subscribe({
      next: (response: any) => {
        console.log('Login successful', response);
        this.router.navigate(['/chat']);
      },
      error: (err: any) => {
        this.errorMessage = 'Login failed. Please check your username and password.';
        console.error('Login Error:', err);
      }
    });
  }

  navigateToRegister() {
    this.router.navigate(['/register']);
  }
}
