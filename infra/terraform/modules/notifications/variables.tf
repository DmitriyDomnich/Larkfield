variable "project_name" {
  type = string
}

variable "user_pool_id" {
  description = "Cognito user pool the Lambda looks employees' emails up in."
  type        = string
}

variable "user_pool_arn" {
  type = string
}

variable "sender_email" {
  description = "From address of the claim emails; a verified SES identity."
  type        = string
}

variable "recipient_emails" {
  description = "Addresses to verify while the account is in the SES sandbox (demo employees)."
  type        = list(string)
  default     = []
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 10
}

variable "max_receives" {
  description = "Deliveries of one notification before it moves to the dead-letter queue."
  type        = number
  default     = 5
}

variable "iam_path" {
  description = "IAM path of the module's roles and policies; the deploy role manages only this path."
  type        = string
  default     = "/"
}

variable "permissions_boundary_arn" {
  description = "Boundary every role must carry for the deploy role to create it."
  type        = string
  default     = null
}

variable "manage_email_identities" {
  description = "Create the SES identities of sender_email and recipient_emails; false where another environment of the account already does."
  type        = bool
  default     = true
}
