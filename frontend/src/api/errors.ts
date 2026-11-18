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

function getErrorDetail(error: unknown): string | undefined {
  if (typeof error === "object" && error !== null && "detail" in error) {
    return typeof error.detail === "string" ? error.detail : undefined;
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
