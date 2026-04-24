import { NextResponse } from "next/server";

const BACKEND_API_URL = process.env.API_URL || "http://stock-api:8000";

export async function GET(): Promise<NextResponse> {
  const response = await fetch(`${BACKEND_API_URL}/health`, {
    cache: "no-store",
  });

  return new NextResponse(response.body, {
    status: response.status,
    headers: response.headers,
  });
}
