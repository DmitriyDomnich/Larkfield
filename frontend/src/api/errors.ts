export const GENERIC_ERROR = "Something went wrong. Please try again in a moment.";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string | undefined,
  ) {
    super(detail ?? `Request failed with status ${status}`);
  }
}

type ApiResult<T> = { data?: T; error?: unknown; response: Response };

export async function unwrap<T>(request: Promise<ApiResult<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) {
    throw new ApiError(response.status, getErrorDetail(error));
  }
  return data as T;
}

// `detail` is a string, or for a request-validation 422 a list of { msg, loc, ... }
function getErrorDetail(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null || !("detail" in error)) return undefined;
  const { detail } = error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const [first] = detail as unknown[];
    if (typeof first === "object" && first !== null && "msg" in first) {
      return typeof first.msg === "string" ? first.msg : undefined;
    }
  }
  return undefined;
}

/** The API's own message for a 4xx, a generic one for a 5xx or a network failure */
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status < 500 && error.detail) {
    return error.detail;
  }
  return GENERIC_ERROR;
}
