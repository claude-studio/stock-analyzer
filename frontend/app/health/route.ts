import { NextResponse } from "next/server";

const BACKEND_API_URL = process.env.API_URL || "http://stock-api:8000";
const BACKEND_TIMEOUT_MS = 5_000;

export async function GET(): Promise<NextResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${BACKEND_API_URL}/health`, {
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    const backend = error instanceof DOMException && error.name === "AbortError"
      ? "timeout"
      : "unavailable";
    const status = backend === "timeout" ? 504 : 502;
    return NextResponse.json({ status: "degraded", checks: { backend }, jobs: [] }, { status });
  } finally {
    clearTimeout(timeout);
  }

  return new NextResponse(response.body, {
    status: response.status,
    headers: response.headers,
  });
}
