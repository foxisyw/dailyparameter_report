import { next } from '@vercel/functions';

const PASSWORD = 'parameter0728';
const COOKIE_NAME = 'pr_auth';
const SECRET = 'paramreview_hmac_secret_2026';
const COOKIE_MAX_AGE = 30 * 24 * 60 * 60;

async function hmacSign(message) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw', encoder.encode(SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(message));
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('');
}

function loginHTML(error = false) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Parameter Review — Login</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans',sans-serif;background:#fff;color:#111827;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.card{width:100%;max-width:380px;text-align:center}
.brand{font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:500;letter-spacing:2.5px;text-transform:uppercase;color:#111827;margin-bottom:4px}
.sub{font-size:13px;color:#9ca3af;margin-bottom:32px}
.team{font-size:10px;color:#d1d5db;margin-bottom:40px;letter-spacing:0.3px}
form{display:flex;flex-direction:column;gap:12px}
input[type="password"]{font-family:'JetBrains Mono',monospace;font-size:14px;padding:12px 16px;border:1.5px solid #e5e7eb;border-radius:4px;outline:none;text-align:center;letter-spacing:2px;transition:border-color .15s}
input[type="password"]:focus{border-color:#111827}
button{font-family:'DM Sans',sans-serif;font-size:13px;font-weight:600;padding:12px;background:#111827;color:#fff;border:none;border-radius:4px;cursor:pointer;transition:background .15s}
button:hover{background:#374151}
.err{font-size:12px;color:#dc2626;margin-top:4px}
.line{width:40px;height:1.5px;background:#e5e7eb;margin:0 auto 24px}
</style>
</head>
<body>
<div class="card">
<div class="brand">PARAMETER REVIEW</div>
<div class="sub">Daily Automated Audit</div>
<div class="line"></div>
<div class="team">Presented By CoreTrading ParaMgnt Team</div>
<form method="POST" action="/__auth">
<input type="password" name="password" placeholder="Enter password" autofocus required>
${error ? '<div class="err">Incorrect password. Please try again.</div>' : ''}
<button type="submit">Access Report</button>
</form>
</div>
</body>
</html>`;
}

export default async function middleware(request) {
  const url = new URL(request.url);

  // POST /__auth → validate password
  if (url.pathname === '/__auth' && request.method === 'POST') {
    const formData = await request.formData();
    const password = formData.get('password');

    if (password === PASSWORD) {
      const token = await hmacSign(PASSWORD);
      return new Response(null, {
        status: 302,
        headers: {
          Location: '/',
          'Set-Cookie': `${COOKIE_NAME}=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${COOKIE_MAX_AGE}`,
        },
      });
    }

    return new Response(loginHTML(true), {
      status: 401,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }

  // GET /__logout → clear cookie
  if (url.pathname === '/__logout') {
    return new Response(null, {
      status: 302,
      headers: {
        Location: '/',
        'Set-Cookie': `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`,
      },
    });
  }

  // Check auth cookie
  const cookies = request.headers.get('cookie') || '';
  const match = cookies.split(';').map(c => c.trim()).find(c => c.startsWith(`${COOKIE_NAME}=`));

  if (match) {
    const token = match.split('=')[1];
    const valid = await hmacSign(PASSWORD);
    if (token === valid) {
      // Authenticated — pass through
      return next();
    }
  }

  // Not authenticated → login page
  return new Response(loginHTML(false), {
    status: 401,
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
