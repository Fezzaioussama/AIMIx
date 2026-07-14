import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = '/api/login';

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
    const registerUrl = this.apiUrl.replace('/login', '/register');
    return this.http.post<any>(registerUrl, credentials);
  }
}
