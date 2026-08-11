import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { fixtures } from "./fixtures";

export const handlers = [
  http.get("/api/v1/jobs", () => HttpResponse.json({ items: [fixtures.completeJob], total: 1 })),
  http.get("/api/v1/jobs/:id", () => HttpResponse.json(fixtures.completeJob)),
  http.get("/api/v1/reviews", () => HttpResponse.json(fixtures.reviewQueue)),
  http.post("/api/v1/reviews/:id", () => HttpResponse.json(fixtures.resolvedReview, { status: 201 })),
  http.get("/api/v1/models", () => HttpResponse.json(fixtures.models)),
  http.get("/api/v1/evidence", () => HttpResponse.json(fixtures.publicOnlyEvidence)),
  http.get("/api/v1/system/status", () => HttpResponse.json(fixtures.systemStatus)),
];

export const server = setupServer(...handlers);
