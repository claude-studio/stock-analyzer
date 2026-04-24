import { NextRequest, NextResponse } from "next/server";

const BACKEND_API_URL = process.env.API_URL || "http://stock-api:8000";
const API_KEY = process.env.API_KEY || "";
const ALLOWED_GET_PATTERNS = [
  /^stocks$/,
  /^stocks\/[^/]+\/detail$/,
  /^stocks\/[^/]+\/analysis$/,
  /^stocks\/[^/]+\/prices$/,
  /^stocks\/[^/]+\/technical$/,
  /^stocks\/[^/]+\/news-impact$/,
  /^market\/overview$/,
  /^watchlist$/,
  /^news$/,
  /^news\/\d+$/,
  /^accuracy$/,
];

async function proxyRequest(
  request: NextRequest,
  params: { path?: string[] },
): Promise<NextResponse> {
  const segments = params.path ?? [];
  const path = segments.join("/");
  if (!ALLOWED_GET_PATTERNS.some((pattern) => pattern.test(path))) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const search = request.nextUrl.search;
  const targetUrl = `${BACKEND_API_URL}/api/v1/${path}${search}`;

  const headers = new Headers();
  headers.set("Content-Type", request.headers.get("content-type") || "application/json");
  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }

  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
    cache: "no-store",
  });

  return new NextResponse(response.body, {
    status: response.status,
    headers: response.headers,
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
): Promise<NextResponse> {
  return proxyRequest(request, await context.params);
}
