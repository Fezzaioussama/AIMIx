import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  // Update this URL to match your Python Backend
  private apiUrl = 'http://127.0.0.1:8000/api/login';

  constructor(private http: HttpClient) { }

  login(username: string, password: string): Observable<any> {
    const credentials = { username, password };
    return this.http.post<any>(this.apiUrl, credentials).pipe(
      tap(response => {
        if (response && response.access) {
          localStorage.setItem('access_token', response.access);
          localStorage.setItem('refresh_token', response.refresh);
        }
      })
    );
  }

  register(username: string, password: string): Observable<any> {
    const credentials = { username, password };
    // Assuming the register endpoint is similar pattern. Adjust if needed.
    // If backend doesn't have register endpoint yet, this will 404, but frontend is ready.
    const registerUrl = this.apiUrl.replace('/login', '/register');
    return this.http.post<any>(registerUrl, credentials);
  }
}