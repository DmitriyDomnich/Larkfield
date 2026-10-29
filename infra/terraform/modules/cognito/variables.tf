variable "project_name" {
  type = string
}

variable "enable_password_auth" {
  description = "Allow USER_PASSWORD_AUTH, for CLI smoke tests. Keep false outside dev."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "post_confirmation_lambda_arn" {
  type = string
}
