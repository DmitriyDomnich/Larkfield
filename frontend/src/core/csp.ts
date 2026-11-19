import { apiUrl, cognito, documentsOrigin } from "@/core/config";

// 'unsafe-inline': the static export's inline hydration scripts need it (nonces need a server).
// 'unsafe-eval' only in development, where React uses eval for debugging.
export function getContentSecurityPolicy(isDevelopment: boolean): string {
  const cognitoOrigin = `https://cognito-idp.${cognito.region}.amazonaws.com`;
  const directives = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'unsafe-inline'", ...(isDevelopment ? ["'unsafe-eval'"] : [])],
    "style-src": ["'self'", "'unsafe-inline'"],
    "connect-src": ["'self'", new URL(apiUrl).origin, cognitoOrigin, documentsOrigin],
    "img-src": ["'self'", documentsOrigin],
    "frame-src": ["'self'", documentsOrigin],
    "font-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
  };
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${sources.join(" ")}`)
    .join("; ");
}
