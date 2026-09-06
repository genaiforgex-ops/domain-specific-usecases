import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// The session is an httpOnly cookie, so there is nothing for the client to read
// or store. What these tests pin down instead is that every request opts into
// sending it, and that a 401 dispatches the unauthorized event.

const setSearch = (search: string) => {
  (globalThis as unknown as { window: unknown }).window = {
    location: { search },
    dispatchEvent: dispatchSpy,
  };
};

const dispatchSpy = vi.fn();
let fetchMock: ReturnType<typeof vi.fn>;

const jsonResponse = (body: unknown, status = 200) =>
  ({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  }) as unknown as Response;

beforeEach(() => {
  dispatchSpy.mockReset();
  setSearch("");
  fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  vi.resetModules();
});

describe("api client credentials", () => {
  it("sends credentials on every request so the session cookie travels", async () => {
    const { api } = await import("./client");
    await api.get("/auth/me");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe("include");
  });

  it("does not attach an Authorization header", async () => {
    const { api } = await import("./client");
    await api.get("/auth/me");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers).not.toHaveProperty("Authorization");
  });
});

describe("401 handling", () => {
  it("signals unauthorized on a normal 401", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Not authenticated" }, 401));
    const { api } = await import("./client");

    await expect(api.get("/auth/me")).rejects.toThrow("Not authenticated");
    expect(dispatchSpy).toHaveBeenCalledOnce();
  });
});

describe("empty responses", () => {
  // Every DELETE endpoint returns 204. res.json() on an empty body throws
  // "Unexpected end of JSON input", which surfaced as a failure toast on
  // deletions the server had already carried out.
  const noContent = () =>
    ({
      ok: true,
      status: 204,
      headers: { get: () => null },
      json: async () => {
        throw new SyntaxError("Unexpected end of JSON input");
      },
    }) as unknown as Response;

  it("resolves a 204 instead of failing to parse an empty body", async () => {
    fetchMock.mockResolvedValue(noContent());
    const { api } = await import("./client");

    await expect(api.delete("/forms/templates/abc")).resolves.toBeUndefined();
  });

  it("still parses a normal JSON body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "abc" }));
    const { api } = await import("./client");

    await expect(api.get("/forms/templates/abc")).resolves.toEqual({ id: "abc" });
  });
});

describe("error messages", () => {
  // Over HTTP/2 (the deployed ingress) res.statusText is always "", so any error
  // whose body was not the expected JSON produced a toast with no text at all.
  const http2Error = (status: number, body?: unknown) =>
    ({
      ok: false,
      status,
      statusText: "",
      headers: { get: () => "application/json" },
      json: async () => {
        if (body === undefined) throw new SyntaxError("Unexpected token < in JSON");
        return body;
      },
    }) as unknown as Response;

  it("never throws an empty message when the body is not JSON", async () => {
    fetchMock.mockResolvedValue(http2Error(500));
    const { api } = await import("./client");

    await expect(api.post("/forms/assignments/x/submit")).rejects.toThrow(
      "Something went wrong on the server.",
    );
  });

  it("falls back per status when there is no detail", async () => {
    fetchMock.mockResolvedValue(http2Error(504));
    const { api } = await import("./client");

    await expect(api.get("/anything")).rejects.toThrow("The server took too long");
  });

  it("prefers the server's own detail when it sent one", async () => {
    fetchMock.mockResolvedValue(http2Error(400, { detail: "Missing required fields: Name" }));
    const { api } = await import("./client");

    await expect(api.get("/anything")).rejects.toThrow("Missing required fields: Name");
  });

  it("unpacks a 422 detail array instead of stringifying it to [object Object]", async () => {
    fetchMock.mockResolvedValue(
      http2Error(422, { detail: [{ loc: ["body", "answers"], msg: "field required" }] }),
    );
    const { api } = await import("./client");

    await expect(api.get("/anything")).rejects.toThrow("field required");
  });

  it("does not treat a blank detail as a message", async () => {
    fetchMock.mockResolvedValue(http2Error(403, { detail: "   " }));
    const { api } = await import("./client");

    await expect(api.get("/anything")).rejects.toThrow("You don't have permission");
  });
});
