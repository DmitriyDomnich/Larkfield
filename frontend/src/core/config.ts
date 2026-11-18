export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
export const documentsOrigin = process.env.NEXT_PUBLIC_DOCUMENTS_ORIGIN ?? "";
export const cognito = {
  region: process.env.NEXT_PUBLIC_COGNITO_REGION ?? "",
  userPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID ?? "",
  appClientId: process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID ?? "",
};
