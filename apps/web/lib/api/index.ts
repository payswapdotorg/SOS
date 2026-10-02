/**
 * The single typed client module (law §8). Every API call in the app flows
 * through this barrel — components never call `fetch` directly and never
 * hold API URLs of their own.
 */

export * from "./types";
export { endpoints, withQuery } from "./endpoints";
export { ApiError, isApiErrorEnvelope } from "./errors";
export type { ApiErrorEnvelope } from "./types";
export {
  buildUrl,
  createSosClient,
  getSosClient,
  parseErrorEnvelope,
  resolveRuntime,
  __resetSosClientForTests,
} from "./client";
export type { ClientMode, ClientRuntime, CollectionFilter, EvidenceFilter, SosClient, SosClientConfig } from "./client";
export { DEMO_LABEL, DEMO_WORKSPACE_SLUG, demo } from "@/lib/fixtures/demo";
