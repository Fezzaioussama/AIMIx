import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  // Update this URL to match your Python Backend
  private apiUrl = 'http://localhost:50000/api/login'; 

  constructor(private http: HttpClient) { }

  login(username: string, password: string): Observable<any> {
    const credentials = { username, password }; // or { email: username, password } depending on backend
    return this.http.post<any>(this.apiUrl, credentials).pipe(
      tap(response => {
        if (response && response.token) {
          localStorage.setItem('auth_token', response.token);
        }
      })
    );
  }
}