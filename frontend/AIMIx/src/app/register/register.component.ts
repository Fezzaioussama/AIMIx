import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
    selector: 'app-register',
    standalone: true,
    imports: [CommonModule, FormsModule],
    templateUrl: './register.component.html',
    styleUrls: ['./register.component.css']
})
export class RegisterComponent {
    username = '';
    password = '';
    confirmPassword = '';
    errorMessage = '';

    constructor(private authService: AuthService, private router: Router) { }

    onSubmit() {
        this.errorMessage = '';

        if (this.password !== this.confirmPassword) {
            this.errorMessage = 'Passwords do not match.';
            return;
        }

        this.authService.register(this.username, this.password).subscribe({
            next: (response: any) => {
                console.log('Registration successful', response);
                // Automatically login or redirect to login
                this.router.navigate(['/login']);
            },
            error: (err: any) => {
                this.errorMessage = 'Registration failed. Please try again.';
                console.error('Registration Error:', err);
            }
        });
    }

    navigateToLogin() {
        this.router.navigate(['/login']);
    }
}
