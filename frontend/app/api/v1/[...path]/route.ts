import { NextRequest, NextResponse } from "next/server";

const BACKEND_API_URL = process.env.API_URL || "http://stock-api:8000";
const API_KEY = process.env.API_KEY || "";
const BACKEND_TIMEOUT_MS = 10_000;
const ALLOWED_PATHS_BY_METHOD: Record<string, RegExp[]> = {
  GET: [
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
    /^portfolio\/summary$/,
    /^portfolio\/holdings$/,
    /^screener$/,
    /^alerts\/rules$/,
    /^alerts\/events$/,
  ],
  POST: [
    /^portfolio\/holdings$/,
    /^backtests\/run$/,
    /^alerts\/rules$/,
    /^alerts\/evaluate$/,
  ],
  PATCH: [
    /^portfolio\/holdings\/[^/]+$/,
    /^alerts\/rules\/[^/]+$/,
  ],
  DELETE: [
    /^portfolio\/holdings\/[^/]+$/,
    /^alerts\/rules\/[^/]+$/,
  ],
};

function isAllowedPath(method: string, path: string): boolean {
  return ALLOWED_PATHS_BY_METHOD[method]?.some((pattern) => pattern.test(path)) ?? false;
}

async function proxyRequest(
  request: NextRequest,
  params: { path?: string[] },
): Promise<NextResponse> {
  const segments = params.path ?? [];
  const path = segments.join("/");
  if (!isAllowedPath(request.method, path)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const search = request.nextUrl.search;
  const targetUrl = `${BACKEND_API_URL}/api/v1/${path}${search}`;

  const headers = new Headers();
  headers.set("Content-Type", request.headers.get("content-type") || "application/json");
  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return NextResponse.json({ detail: "Backend request timed out" }, { status: 504 });
    }
    return NextResponse.json({ detail: "Backend request failed" }, { status: 502 });
  } finally {
    clearTimeout(timeout);
  }

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

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
): Promise<NextResponse> {
  return proxyRequest(request, await context.params);
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
): Promise<NextResponse> {
  return proxyRequest(request, await context.params);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
): Promise<NextResponse> {
  return proxyRequest(request, await context.params);
}
