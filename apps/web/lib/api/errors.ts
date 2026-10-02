import type { ApiErrorCode, ApiErrorEnvelope } from "./types";

/**
 * Typed error thrown by the client for any non-2xx response carrying the
 * contract error envelope. Transport-level failures carry code
 * `PROVIDER_UNAVAILABLE` only when the envelope says so — a network failure
 * surfaces as an `ApiError` with `code = null` so it can never masquerade as
 * a resource truth state (contract C.2: transport errors never masquerade).
 */
export class ApiError extends Error {
  readonly code: ApiErrorCode | null;
  readonly details: Record<string, unknown> | null;
  readonly status: number;

  constructor(args: {
    message: string;
    code: ApiErrorCode | null;
    details?: Record<string, unknown> | null;
    status?: number;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.code = args.code;
    this.details = args.details ?? null;
    this.status = args.status ?? 0;
  }

  static fromEnvelope(status: number, envelope: ApiErrorEnvelope): ApiError {
    return new ApiError({
      message: envelope.error.message,
      code: envelope.error.code,
      details: envelope.error.details,
      status,
    });
  }
}

/** Type guard for the wire error envelope shape. */
export function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const outer = value as { error?: unknown };
  if (typeof outer.error !== "object" || outer.error === null) return false;
  const inner = outer.error as { code?: unknown; message?: unknown; details?: unknown };
  return typeof inner.code === "string" && typeof inner.message === "string";
}
