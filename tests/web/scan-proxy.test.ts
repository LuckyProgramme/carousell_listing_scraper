import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { configureEnv, env } from "./fixtures";

const auth = vi.hoisted(() => ({ getClaims: vi.fn() }));
const factory = vi.hoisted(() => vi.fn());
vi.mock("@supabase/ssr", () => ({ createServerClient: factory }));
import { proxy } from "@/proxy";

beforeEach(() => {
  configureEnv();
  factory.mockReturnValue({ auth });
  auth.getClaims.mockResolvedValue({ data: null });
});

describe("scan route and sign-in proxy integration", () => {
  it.each(["POST", "GET"].flatMap((method) => ["/api/scan", "/api/scan/recover"].map((path) => ({ method, path }))))("lets $path $method reach its own handler without auth/redirect", async ({ method, path }) => {
    const response = await proxy(new NextRequest(`${env.FRONTEND_ORIGIN}${path}`, { method }));
    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(response.headers.get("location")).toBeNull();
    expect(factory).not.toHaveBeenCalled();
    expect(auth.getClaims).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(["/", "/api/scan/recover/other"])("preserves the existing sign-in gate for %s", async (path) => {
    const response = await proxy(new NextRequest(`${env.FRONTEND_ORIGIN}${path}`));
    expect(response.headers.get("location")).toBe(`${env.FRONTEND_ORIGIN}/login`);
    expect(auth.getClaims).toHaveBeenCalledOnce();
  });
  it("preserves the redirect from login for an authenticated user", async () => {
    auth.getClaims.mockResolvedValue({ data: { claims: { sub: "user" } } });
    const response = await proxy(new NextRequest(`${env.FRONTEND_ORIGIN}/login`));
    expect(response.headers.get("location")).toBe(`${env.FRONTEND_ORIGIN}/`);
  });
});
