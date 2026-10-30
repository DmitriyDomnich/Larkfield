locals {
  role_groups = {
    admin    = 1
    reviewer = 2
    employee = 3
  }
}

resource "aws_cognito_user_pool" "main" {
  name           = var.project_name
  user_pool_tier = "LITE" # should be enough

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = var.deletion_protection ? "ACTIVE" : "INACTIVE"

  admin_create_user_config {
    allow_admin_create_user_only = false # self sign-up
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
  }

  # Cognito's built-in sender (limited to ~50 emails/day), can later move this to SES
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  lambda_config {
    post_confirmation = var.post_confirmation_lambda_arn
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project_name}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false # public client: the SPA can't keep a secret
  explicit_auth_flows = concat(
    ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
    var.enable_password_auth ? ["ALLOW_USER_PASSWORD_AUTH"] : [],
  )
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  access_token_validity  = 15
  id_token_validity      = 15
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  read_attributes  = ["email", "email_verified", "name"]
  write_attributes = ["email", "name"]
}

resource "aws_cognito_user_group" "role" {
  for_each = local.role_groups

  name         = each.key
  user_pool_id = aws_cognito_user_pool.main.id
  precedence   = each.value
  description  = "Larkfield ${each.key} role"
}

resource "aws_lambda_permission" "post_confirmation" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.post_confirmation_lambda_arn
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.main.arn
}
