import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("maps the backend error envelope and keeps the request id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ code: "database_busy", message: "Try again", request_id: "req-123" }),
          { status: 503, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    await expect(api.getJob("one")).rejects.toMatchObject({
      code: "database_busy",
      requestId: "req-123",
      status: 503,
    });
    expect(ApiError).toBeDefined();
  });
});
