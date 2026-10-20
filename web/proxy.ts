import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

// Endpoints of the FastAPI that work without a bearer token.
const PUBLIC_API = new Set(["/api/v1/health", "/api/v1/token"]);

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const token = request.cookies.get(SESSION_COOKIE)?.value;

  if (pathname.startsWith("/api/v1/")) {
    if (PUBLIC_API.has(pathname)) return NextResponse.next();
    if (!token) {
      return NextResponse.json({ detail: "Not logged in" }, { status: 401 });
    }
    // Next.js buffers request bodies on proxy-matched paths and silently cuts
    // them at 10 MB (proxyClientMaxBodySize). SAR files are larger, so uploads
    // go through the streaming route handler app/api/upload instead.
    if (pathname === "/api/v1/files" && request.method === "POST") {
      return NextResponse.json(
        { detail: "Upload via /api/upload (streams the body to the API)" },
        { status: 405 },
      );
    }
    // The rewrite in next.config.ts forwards these request headers to the
    // FastAPI. Any Authorization header sent by the browser is replaced.
    const headers = new Headers(request.headers);
    headers.set("authorization", `Bearer ${token}`);
    headers.delete("cookie");
    return NextResponse.next({ request: { headers } });
  }

  // Pages: optimistic check only. The API validates the token on every call;
  // an expired token makes the client log out (see lib/api.ts).
  if (!token) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname + search);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/api/v1/:path*", "/files/:path*", "/overview/:path*"],
};
