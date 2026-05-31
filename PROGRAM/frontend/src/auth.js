/**
 * Авторизация через httpOnly cookie (выставляется backend на /login и /signup).
 * В localStorage храним только флаг "залогинен" — это нужно для UI-роутинга.
 * Сам токен в JS НЕ хранится, поэтому XSS не может его украсть.
 */
const FLAG = 'floral_auth';

export const authStore = {
  get loggedIn() { return localStorage.getItem(FLAG) === '1'; },
  setLoggedIn(v) {
    if (v) localStorage.setItem(FLAG, '1');
    else localStorage.removeItem(FLAG);
  },
  clear() { localStorage.removeItem(FLAG); },
};
