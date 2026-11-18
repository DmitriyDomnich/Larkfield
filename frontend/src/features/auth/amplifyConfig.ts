import type { ResourcesConfig } from "aws-amplify";

import { cognito } from "@/core/config";

export const amplifyConfig: ResourcesConfig = {
  Auth: {
    Cognito: {
      userPoolId: cognito.userPoolId,
      userPoolClientId: cognito.appClientId,
      loginWith: { email: true },
      signUpVerificationMethod: "code",
      userAttributes: { email: { required: true } },
      passwordFormat: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireNumbers: true,
        requireSpecialCharacters: false,
      },
    },
  },
};
