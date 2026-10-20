import { NextResponse } from "next/server";
import { SESSION_COOKIE, cookieSecure } from "@/lib/session";

// The API has no token revocation (stateless HMAC tokens), so logging out
// means dropping the cookie. See PHASE2-API-GAPS.md.
export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: cookieSecure(),
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return response;
}
