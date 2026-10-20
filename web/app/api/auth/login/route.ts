import { NextResponse } from "next/server";
import { SESSION_COOKIE, apiUrl, cookieSecure } from "@/lib/session";

type TokenResponse = { access_token: string; token_type: string; expires_at: number };

// Exchanges username/password for an API token and keeps it in an httpOnly
// cookie. The token is never part of the JSON returned to the browser.
export async function POST(request: Request) {
  let body: { username?: unknown; password?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  }
  const username = typeof body.username === "string" ? body.username.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!username || !password) {
    return NextResponse.json({ detail: "Username and password are required" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl()}/api/v1/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "SAR API is not reachable" }, { status: 502 });
  }
  if (!upstream.ok) {
    const status = upstream.status === 401 ? 401 : 502;
    const detail = status === 401 ? "Invalid username or password" : "Login failed";
    return NextResponse.json({ detail }, { status });
  }

  const token = (await upstream.json()) as TokenResponse;
  const maxAge = Math.max(0, token.expires_at - Math.floor(Date.now() / 1000));
  const response = NextResponse.json({ username });
  response.cookies.set(SESSION_COOKIE, token.access_token, {
    httpOnly: true,
    secure: cookieSecure(),
    sameSite: "lax",
    path: "/",
    maxAge,
  });
  return response;
}
