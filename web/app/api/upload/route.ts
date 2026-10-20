import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, apiUrl } from "@/lib/session";

// Streams a multipart upload straight to POST /api/v1/files. This path is
// deliberately outside the proxy.ts matcher: Next.js buffers (and truncates
// at 10 MB) request bodies on proxy-matched paths.
export async function POST(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Not logged in" }, { status: 401 });
  }
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.startsWith("multipart/form-data") || !request.body) {
    return NextResponse.json({ detail: "Expected multipart/form-data" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl()}/api/v1/files`, {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": contentType },
      body: request.body,
      // required by undici for streamed request bodies
      duplex: "half",
      cache: "no-store",
    } as RequestInit & { duplex: "half" });
  } catch {
    return NextResponse.json({ detail: "SAR API is not reachable" }, { status: 502 });
  }
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
