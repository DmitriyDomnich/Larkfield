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
