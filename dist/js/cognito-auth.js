(function () {
  'use strict';
  const config = window.CAMPUS_RUNTIME_CONFIG || {};
  const enabled = config.authMode === 'cognito';
  const STORAGE_KEY = 'campus-cognito-session-v1';
  let tokenSet = null;
  const encode = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const random = size => {
    const bytes = crypto.getRandomValues(new Uint8Array(size));
    return encode(bytes);
  };
  const readToken = token => {
    try {
      const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      return JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, '=')));
    }
    catch { return null; }
  };
  const save = value => {
    tokenSet = value;
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(STORAGE_KEY);
  };
  const load = () => {
    try { tokenSet = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null'); }
    catch { tokenSet = null; }
  };
  function endpoint(path) {
    const url = new URL(config.domain || '');
    if (url.protocol !== 'https:') throw new Error('Cognito domain must use HTTPS.');
    url.pathname = path;
    url.search = '';
    return url;
  }
  function callbackUri() { return config.redirectUri || `${location.origin}/`; }
  async function exchange(form) {
    const response = await fetch(endpoint('/oauth2/token'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams(form)
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error_description || body.error || 'Cognito token exchange failed.');
    return { ...body, expires_at: Date.now() + Number(body.expires_in || 3600) * 1000 };
  }
  async function initialize() {
    if (!enabled) return;
    load();
    const params = new URLSearchParams(location.search);
    const code = params.get('code');
    if (!code) return;
    const expectedState = sessionStorage.getItem('campus-cognito-state');
    const verifier = sessionStorage.getItem('campus-cognito-verifier');
    const state = params.get('state');
    sessionStorage.removeItem('campus-cognito-state');
    sessionStorage.removeItem('campus-cognito-verifier');
    if (!expectedState || state !== expectedState || !verifier) throw new Error('Cognito sign-in state validation failed.');
    const tokens = await exchange({
      grant_type: 'authorization_code',
      client_id: config.clientId,
      code,
      redirect_uri: callbackUri(),
      code_verifier: verifier
    });
    save(tokens);
    history.replaceState(null, '', location.pathname + location.hash);
  }
  const ready = initialize();
  async function getAccessToken() {
    await ready;
    if (!enabled) return null;
    if (tokenSet?.access_token && tokenSet.expires_at > Date.now() + 30000) return tokenSet.access_token;
    if (tokenSet?.refresh_token) {
      const refreshToken = tokenSet.refresh_token;
      tokenSet = await exchange({
        grant_type: 'refresh_token',
        client_id: config.clientId,
        refresh_token: refreshToken
      });
      tokenSet.refresh_token = refreshToken;
      save(tokenSet);
      return tokenSet.access_token;
    }
    return null;
  }
  async function signIn() {
    await ready;
    if (!enabled) throw new Error('Cognito authentication is not enabled.');
    const verifier = random(32);
    const challenge = encode(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
    const state = random(24);
    sessionStorage.setItem('campus-cognito-verifier', verifier);
    sessionStorage.setItem('campus-cognito-state', state);
    const url = endpoint('/oauth2/authorize');
    Object.entries({
      response_type: 'code',
      client_id: config.clientId,
      redirect_uri: callbackUri(),
      scope: 'openid email profile',
      state,
      code_challenge: challenge,
      code_challenge_method: 'S256'
    }).forEach(([key, value]) => url.searchParams.set(key, value));
    location.assign(url);
  }
  async function signOut() {
    await ready;
    save(null);
    if (!enabled) return;
    const url = endpoint('/logout');
    url.searchParams.set('client_id', config.clientId);
    url.searchParams.set('logout_uri', config.logoutUri || callbackUri());
    location.assign(url);
  }
  function username() {
    const claims = tokenSet?.access_token ? readToken(tokenSet.access_token) : null;
    return claims?.username || claims?.['cognito:username'] || null;
  }
  window.CampusAuth = { enabled, ready, getAccessToken, signIn, signOut, username };
}());
